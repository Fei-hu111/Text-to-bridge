"""Command-line workflow for bridge FEM analysis with Abaqus."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from bridge_fem_agent.config import WorkflowConfig
from bridge_fem_agent.agents.model_production_workflow import ModelProductionWorkflow
from bridge_fem_agent.diagnosis.error_classifier import ErrorClassifier
from bridge_fem_agent.diagnosis.log_parser import LogParser
from bridge_fem_agent.inp.inp_builder import InpBuilder
from bridge_fem_agent.repair.repair_engine import RepairEngine
from bridge_fem_agent.results.dat_extractor import DatExtractor
from bridge_fem_agent.results.odb_extractor import OdbExtractor
from bridge_fem_agent.results.report_writer import ReportWriter
from bridge_fem_agent.runner.abaqus_runner import AbaqusRunner
from bridge_fem_agent.runner.job_monitor import JobMonitor
from bridge_fem_agent.rigid_frame.schema import RigidFrameInput
from bridge_fem_agent.rigid_frame.v7_workflow import RigidFrameV7Workflow
from bridge_fem_agent.rigid_frame.workflow import RigidFrameV3Workflow
from bridge_fem_agent.schemas.bridge_schema import BridgeTask


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bridge FEM Agent Workflow")
    parser.add_argument("--input", type=Path, help="Bridge task JSON file.")
    parser.add_argument("--workdir", required=True, type=Path, help="Run directory for generated files.")
    parser.add_argument("--workflow", choices=["analysis", "model-production", "rigid-frame-v3", "rigid-frame-v4", "rigid-frame-v5", "rigid-frame-v7"], default="analysis", help="Run V1 analysis, V2 model production, V3-V5 rigid-frame generation, or the V7 closed-loop rigid-frame workflow.")
    parser.add_argument("--max-repairs", type=int, default=WorkflowConfig.default_max_repairs)
    parser.add_argument("--dry-run", action="store_true", help="Run workflow without Abaqus installed.")
    parser.add_argument("--abaqus-command", default=WorkflowConfig().abaqus_command)
    parser.add_argument("--samples-dir", type=Path, default=Path("samples"), help="Local reference model directory for V2 agents.")
    parser.add_argument("--build-cae", action="store_true", help="For model-production, call Abaqus/CAE noGUI to generate .cae/.inp.")
    parser.add_argument("--spans", nargs=3, type=float, metavar=("L1", "L2", "L3"), help="Three span lengths for rigid-frame-v3.")
    parser.add_argument("--pier-height", type=float, help="Pier height for rigid-frame-v3.")
    parser.add_argument("--deck-width", type=float, default=12.5, help="Deck width for rigid-frame-v3 when --spans is used.")
    parser.add_argument("--max-design-iterations", type=int, default=8, help="Maximum V3 section/prestress design iterations.")
    parser.add_argument("--model-level", choices=["construction-solid", "hollow-solid", "solid", "beam"], default="hollow-solid", help="Model idealization for rigid-frame-v3/v4/v5.")
    parser.add_argument("--prestress-mode", choices=["thermal_strain", "equivalent_load", "none"], help="Rigid-frame prestress action. Default: thermal_strain.")
    parser.add_argument("--prestress-effective-ratio", type=float, help="Effective prestress force divided by jacking force. Default: 0.65.")
    parser.add_argument("--design-code-profile", choices=["jtg3362-conservative", "en1992-2-conservative"], default="jtg3362-conservative", help="V7 conservative preliminary review profile.")
    parser.add_argument("--v7-max-iterations", type=int, default=2, help="Maximum number of V7 ODB-driven adjustment rounds after the initial candidate.")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args(argv)


def setup_logging(workdir: Path, level: str) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    log_file = workdir / "workflow.log"
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_file, encoding="utf-8")],
        force=True,
    )


def run_workflow(args: argparse.Namespace) -> dict[str, object]:
    workdir = WorkflowConfig.ensure_workdir(args.workdir)
    setup_logging(workdir, args.log_level)
    logger = logging.getLogger(__name__)
    logger.info("Loading bridge task from %s.", args.input)

    if args.input is None:
        raise ValueError("--input is required for analysis workflow.")
    task = BridgeTask.from_json(args.input)
    builder = InpBuilder(node_count=WorkflowConfig().generated_node_count)
    runner = AbaqusRunner(abaqus_command=args.abaqus_command, dry_run=args.dry_run)
    monitor = JobMonitor()
    parser = LogParser()
    classifier = ErrorClassifier()
    repair_engine = RepairEngine()
    dat_extractor = DatExtractor()
    odb_extractor = OdbExtractor(abaqus_command=args.abaqus_command)

    current_inp = builder.write_initial_inp(task, workdir)
    attempts: list[dict[str, object]] = []
    final_artifacts = None
    status = "failed"

    for attempt in range(args.max_repairs + 1):
        job_name = task.project_name
        if attempt > 0:
            job_name = f"{task.project_name}_attempt_{attempt}"

        run_result = runner.run(current_inp, job_name, workdir)
        artifacts = monitor.collect(job_name, workdir)
        monitored_status = monitor.status(artifacts)
        if monitored_status == "success":
            job_status = "success"
        elif monitored_status == "failed" or not run_result.succeeded:
            job_status = "failed"
        else:
            job_status = "unknown"
        findings = parser.parse(artifacts)
        issues = classifier.classify(findings)
        attempt_report: dict[str, object] = {
            "attempt": attempt,
            "input_file": current_inp,
            "job_name": job_name,
            "status": job_status,
            "return_code": run_result.return_code,
            "command": run_result.command,
            "issues": [asdict(issue) for issue in issues],
            "repairs": [],
        }
        attempts.append(attempt_report)
        final_artifacts = artifacts

        if job_status == "success":
            status = "success"
            logger.info("Analysis succeeded on attempt %s.", attempt)
            break

        if attempt >= args.max_repairs:
            logger.warning("Maximum repair attempts reached.")
            break

        repaired_path, actions = repair_engine.repair(current_inp, issues, task.project_name, attempt + 1, workdir)
        attempt_report["repairs"] = [asdict(action) for action in actions]
        if repaired_path is None:
            logger.warning("No repair action available; stopping workflow.")
            break
        current_inp = repaired_path

    results = {}
    odb_info = {}
    if final_artifacts:
        results = asdict(dat_extractor.extract(final_artifacts.files[".dat"]))
        odb_info = odb_extractor.extract(final_artifacts.files[".odb"])
        odb_results = odb_info.get("results") if isinstance(odb_info, dict) else None
        if isinstance(odb_results, dict):
            for key in ("max_displacement", "max_stress", "modal_frequencies"):
                if results.get(key) in (None, []):
                    results[key] = odb_results.get(key)
            if not results.get("support_reactions"):
                results["support_reactions"] = odb_results.get("support_reactions", {})

    report = {
        "project_name": task.project_name,
        "bridge_type": task.bridge_type,
        "analysis_type": task.analysis_type,
        "status": status,
        "dry_run": args.dry_run,
        "workdir": workdir,
        "attempts": attempts,
        "results": results,
        "odb": odb_info,
    }
    ReportWriter().write(report, workdir)
    logger.info("Workflow finished with status '%s'.", status)
    return report


def run_model_production_workflow(args: argparse.Namespace) -> dict[str, object]:
    workdir = WorkflowConfig.ensure_workdir(args.workdir)
    setup_logging(workdir, args.log_level)
    logger = logging.getLogger(__name__)
    logger.info("Starting V2 multi-agent model production from %s.", args.input)
    if args.input is None:
        raise ValueError("--input is required for model-production workflow.")
    workflow = ModelProductionWorkflow(abaqus_command=args.abaqus_command)
    report = workflow.run(args.input, workdir, samples_dir=args.samples_dir, build_cae=args.build_cae)
    logger.info("V2 model production finished with status '%s'.", report["status"])
    return report


def run_rigid_frame_v3_workflow(args: argparse.Namespace) -> dict[str, object]:
    workdir = WorkflowConfig.ensure_workdir(args.workdir)
    setup_logging(workdir, args.log_level)
    logger = logging.getLogger(__name__)
    if args.workflow == "rigid-frame-v5" and args.model_level in {"solid", "hollow-solid"}:
        args.model_level = "construction-solid"
    if args.workflow == "rigid-frame-v4" and args.model_level == "solid":
        args.model_level = "hollow-solid"
    if args.input:
        task = RigidFrameInput.from_json(args.input)
        if args.max_design_iterations or args.prestress_mode or args.prestress_effective_ratio is not None:
            data = task.to_dict()
            data["targets"]["max_iterations"] = args.max_design_iterations
            if args.prestress_mode:
                data["prestress_mode"] = args.prestress_mode
            if args.prestress_effective_ratio is not None:
                data["prestress_effective_ratio"] = args.prestress_effective_ratio
            task = RigidFrameInput.from_dict(data)
    elif args.spans:
        task = RigidFrameInput.from_dict(
            {
                "project_name": f"rigid_frame_{int(args.spans[0])}_{int(args.spans[1])}_{int(args.spans[2])}",
                "spans_m": args.spans,
                "pier_height_m": args.pier_height,
                "deck_width_m": args.deck_width,
                "max_design_iterations": args.max_design_iterations,
                "prestress_mode": args.prestress_mode or "thermal_strain",
                "prestress_effective_ratio": args.prestress_effective_ratio if args.prestress_effective_ratio is not None else 0.65,
            }
        )
    else:
        raise ValueError("rigid-frame workflow requires either --input or --spans L1 L2 L3.")

    version = {"rigid-frame-v5": "V5", "rigid-frame-v4": "V4"}.get(args.workflow, "V3")
    logger.info("Starting %s rigid-frame workflow for spans %s.", version, task.spans_m)
    workflow = RigidFrameV3Workflow(abaqus_command=args.abaqus_command)
    report = workflow.run(task, workdir, build_cae=args.build_cae, model_level=args.model_level)
    logger.info("%s rigid-frame workflow finished with status '%s'.", version, report["status"])
    return report


def run_rigid_frame_v7_workflow(args: argparse.Namespace) -> dict[str, object]:
    workdir = WorkflowConfig.ensure_workdir(args.workdir)
    setup_logging(workdir, args.log_level)
    logger = logging.getLogger(__name__)
    if args.input:
        task = RigidFrameInput.from_json(args.input)
        data = task.to_dict()
        if args.prestress_mode:
            data["prestress_mode"] = args.prestress_mode
        if args.prestress_effective_ratio is not None:
            data["prestress_effective_ratio"] = args.prestress_effective_ratio
        task = RigidFrameInput.from_dict(data)
    elif args.spans:
        task = RigidFrameInput.from_dict(
            {
                "project_name": f"rigid_frame_{int(args.spans[0])}_{int(args.spans[1])}_{int(args.spans[2])}",
                "spans_m": args.spans,
                "pier_height_m": args.pier_height,
                "deck_width_m": args.deck_width,
                "max_design_iterations": args.max_design_iterations,
                "prestress_mode": args.prestress_mode or "thermal_strain",
                "prestress_effective_ratio": args.prestress_effective_ratio if args.prestress_effective_ratio is not None else 0.65,
            }
        )
    else:
        raise ValueError("rigid-frame-v7 workflow requires either --input or --spans L1 L2 L3.")
    logger.info("Starting V7 closed-loop workflow for spans %s.", task.spans_m)
    workflow = RigidFrameV7Workflow(abaqus_command=args.abaqus_command)
    report = workflow.run(
        task,
        workdir,
        max_iterations=args.v7_max_iterations,
        dry_run=args.dry_run,
        profile_name=args.design_code_profile,
    )
    logger.info("V7 rigid-frame workflow finished with status '%s'.", report["status"])
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.workflow == "model-production":
            report = run_model_production_workflow(args)
            return 0 if report["status"] == "pass" else 2
        if args.workflow in {"rigid-frame-v3", "rigid-frame-v4", "rigid-frame-v5"}:
            report = run_rigid_frame_v3_workflow(args)
            return 0 if report["status"] in {"pass", "needs_review"} else 2
        if args.workflow == "rigid-frame-v7":
            report = run_rigid_frame_v7_workflow(args)
            return 0 if report["status"] in {"pass", "pass_with_local_review", "needs_review", "dry_run"} else 2
        report = run_workflow(args)
        return 0 if report["status"] == "success" else 2
    finally:
        logging.shutdown()
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
