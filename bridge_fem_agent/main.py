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
from bridge_fem_agent.schemas.bridge_schema import BridgeTask


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bridge FEM Agent Workflow")
    parser.add_argument("--input", required=True, type=Path, help="Bridge task JSON file.")
    parser.add_argument("--workdir", required=True, type=Path, help="Run directory for generated files.")
    parser.add_argument("--workflow", choices=["analysis", "model-production"], default="analysis", help="Run V1 analysis workflow or V2 multi-agent model production.")
    parser.add_argument("--max-repairs", type=int, default=WorkflowConfig.default_max_repairs)
    parser.add_argument("--dry-run", action="store_true", help="Run workflow without Abaqus installed.")
    parser.add_argument("--abaqus-command", default=WorkflowConfig().abaqus_command)
    parser.add_argument("--samples-dir", type=Path, default=Path("samples"), help="Local reference model directory for V2 agents.")
    parser.add_argument("--build-cae", action="store_true", help="For model-production, call Abaqus/CAE noGUI to generate .cae/.inp.")
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
    workflow = ModelProductionWorkflow(abaqus_command=args.abaqus_command)
    report = workflow.run(args.input, workdir, samples_dir=args.samples_dir, build_cae=args.build_cae)
    logger.info("V2 model production finished with status '%s'.", report["status"])
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.workflow == "model-production":
            report = run_model_production_workflow(args)
            return 0 if report["status"] == "pass" else 2
        report = run_workflow(args)
        return 0 if report["status"] == "success" else 2
    finally:
        logging.shutdown()
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
