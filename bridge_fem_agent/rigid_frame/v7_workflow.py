"""V7 closed-loop Abaqus workflow for continuous rigid-frame bridges."""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from bridge_fem_agent.config import WorkflowConfig
from bridge_fem_agent.rigid_frame.construction_solid_builder import ConstructionSolidRigidFrameBuilder
from bridge_fem_agent.rigid_frame.design import RigidFrameDesign, RigidFrameDesignFactory, RigidFrameOptimizer
from bridge_fem_agent.rigid_frame.schema import RigidFrameInput
from bridge_fem_agent.rigid_frame.v7_agents import (
    DesignCodeAgent,
    PrestressDiagnosisAgent,
    PrestressOptimizationAgent,
    ReviewGateAgent,
    SolverRepairAgent,
)

LOGGER = logging.getLogger(__name__)


class RigidFrameV7Workflow:
    """Run fast screening, real Abaqus analysis, ODB diagnosis, and adjustment."""

    def __init__(self, abaqus_command: str = "abaqus") -> None:
        self.abaqus_command = abaqus_command
        self.design_factory = RigidFrameDesignFactory()
        self.fast_optimizer = RigidFrameOptimizer()
        self.builder = ConstructionSolidRigidFrameBuilder()
        self.code_agent = DesignCodeAgent()
        self.diagnosis_agent = PrestressDiagnosisAgent()
        self.optimization_agent = PrestressOptimizationAgent()
        self.solver_agent = SolverRepairAgent()
        self.review_gate = ReviewGateAgent()

    def run(
        self,
        task: RigidFrameInput,
        workdir: Path,
        max_iterations: int = 2,
        dry_run: bool = False,
        profile_name: str = "jtg3362-conservative",
    ) -> dict[str, Any]:
        if task.prestress_mode != "thermal_strain":
            raise ValueError("V7 closed-loop verification requires prestress_mode='thermal_strain'.")
        workdir = WorkflowConfig.ensure_workdir(workdir)
        profile = self.code_agent.resolve(profile_name)
        semantic_path = workdir / "rigid_frame_v7_semantic.json"
        screening_path = workdir / "v7_fast_screening_history.json"
        report_json_path = workdir / "rigid_frame_v7_report.json"
        report_md_path = workdir / "rigid_frame_v7_report.md"
        semantic_path.write_text(json.dumps(task.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

        screening = self.fast_optimizer.optimize(task, self.design_factory.create_initial(task))
        screening_path.write_text(json.dumps([item.to_dict() for item in screening], indent=2, ensure_ascii=False), encoding="utf-8")
        current = screening[-1]
        attempts: list[dict[str, Any]] = []
        status = "failed"

        LOGGER.info("Starting V7 closed loop with profile=%s max_iterations=%s.", profile.name, max_iterations)
        for iteration in range(max_iterations + 1):
            candidate = RigidFrameDesign(
                iteration=iteration,
                section=current.section,
                tendon_groups=current.tendon_groups,
                response=current.response,
                actions=current.actions,
            )
            attempt_dir = workdir / f"iteration_{iteration:02d}"
            attempt_dir.mkdir(parents=True, exist_ok=True)
            candidate_path = attempt_dir / "candidate_design.json"
            candidate_path.write_text(json.dumps(candidate.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
            script_path = self.builder.write(task, candidate, attempt_dir)
            attempt: dict[str, Any] = {
                "iteration": iteration,
                "status": "generated",
                "candidate_design": str(candidate_path),
                "build_script": str(script_path),
                "actions": candidate.actions,
            }
            attempts.append(attempt)

            if dry_run:
                attempt["status"] = "dry_run"
                status = "dry_run"
                break

            cae_result = self._run_cae(task, script_path, attempt_dir)
            attempt["cae"] = cae_result
            if cae_result["status"] != "success":
                attempt["status"] = "cae_failed"
                status = "failed"
                break

            job_name = f"{task.project_name}_v7_i{iteration:02d}"
            standard_result = self._run_standard(job_name, Path(cae_result["inp_file"]), attempt_dir)
            attempt["standard"] = standard_result
            solver_review = self.solver_agent.inspect(attempt_dir, job_name)
            attempt["solver_review"] = solver_review
            if solver_review["status"] != "success":
                attempt["status"] = "solver_failed"
                status = "needs_review"
                if solver_review["retriable"] and iteration < max_iterations:
                    current = self.optimization_agent.adjust_for_solver(candidate, solver_review["category"], iteration + 1)
                    LOGGER.warning("Retrying after solver category '%s'.", solver_review["category"])
                    continue
                break

            odb_path = attempt_dir / f"{job_name}.odb"
            result_path = attempt_dir / f"{job_name}_results.json"
            extraction = self._extract_odb(odb_path, result_path, attempt_dir)
            attempt["odb_extraction"] = extraction
            if extraction["status"] != "success":
                attempt["status"] = "odb_extract_failed"
                status = "needs_review"
                break

            odb_results = json.loads(result_path.read_text(encoding="utf-8"))
            diagnosis = self.diagnosis_agent.evaluate(task, profile, odb_results)
            diagnosis_path = attempt_dir / "v7_diagnosis.json"
            diagnosis_path.write_text(json.dumps(diagnosis.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
            gate_status = self.review_gate.review(diagnosis)
            attempt.update(
                {
                    "status": gate_status,
                    "odb": str(odb_path),
                    "odb_results": str(result_path),
                    "diagnosis": str(diagnosis_path),
                    "metrics": diagnosis.metrics,
                    "issues": [issue.to_dict() for issue in diagnosis.issues],
                }
            )
            status = gate_status
            LOGGER.info("V7 iteration %s gate status: %s.", iteration, gate_status)
            if gate_status in {"pass", "pass_with_local_review"}:
                break
            if iteration >= max_iterations:
                status = "needs_review"
                break
            current = self.optimization_agent.adjust(candidate, diagnosis, iteration + 1)

        report = {
            "workflow": "rigid-frame-v7",
            "status": status,
            "dry_run": dry_run,
            "model_level": "construction-solid",
            "prestress_mode": task.prestress_mode,
            "workdir": str(workdir),
            "semantic": str(semantic_path),
            "fast_screening_history": str(screening_path),
            "design_code_profile": profile.to_dict(),
            "attempts": attempts,
            "report_json": str(report_json_path),
            "report_markdown": str(report_md_path),
            "notes": [
                "V7 limits are deterministic preliminary review gates, not a formal design-code compliance certificate.",
                "Local tensile hotspots remain explicit manual-review items for refined diaphragm, support, and anchorage modelling.",
                "TODO: add construction-stage losses, duct friction, anchorage slip, creep, shrinkage, and LLM policy selection.",
            ],
        }
        report_json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        report_md_path.write_text(self._markdown_report(task, report), encoding="utf-8")
        LOGGER.info("V7 closed loop finished with status '%s'.", status)
        return report

    def _run_cae(self, task: RigidFrameInput, script_path: Path, attempt_dir: Path) -> dict[str, Any]:
        command = self._abaqus_command("cae", f"noGUI={script_path.name}")
        completed = self._run_and_record(command, attempt_dir, "abaqus_cae_build")
        cae_file = attempt_dir / f"{task.project_name}.cae"
        inp_file = attempt_dir / f"{task.project_name}.inp"
        has_error = "TRACEBACK" in (completed.stderr or "").upper() or "ABAQUS ERROR" in (completed.stdout or "").upper()
        return {
            "status": "success" if completed.returncode == 0 and cae_file.exists() and inp_file.exists() and not has_error else "failed",
            "return_code": completed.returncode,
            "command": command,
            "cae_file": str(cae_file),
            "inp_file": str(inp_file),
        }

    def _run_standard(self, job_name: str, inp_file: Path, attempt_dir: Path) -> dict[str, Any]:
        command = self._abaqus_command(f"job={job_name}", f"input={inp_file.name}", "interactive")
        completed = self._run_and_record(command, attempt_dir, "abaqus_standard")
        return {"return_code": completed.returncode, "command": command, "job_name": job_name}

    def _extract_odb(self, odb_path: Path, result_path: Path, attempt_dir: Path) -> dict[str, Any]:
        extractor = Path(__file__).resolve().parents[1] / "results" / "abaqus_odb_extract.py"
        command = self._abaqus_command("python", str(extractor), str(odb_path), str(result_path))
        completed = self._run_and_record(command, attempt_dir, "abaqus_odb_extract")
        return {
            "status": "success" if completed.returncode == 0 and result_path.exists() else "failed",
            "return_code": completed.returncode,
            "command": command,
            "result_file": str(result_path),
        }

    def _abaqus_command(self, *args: str) -> list[str]:
        split_args = shlex.split(self.abaqus_command, posix=(os.name != "nt"))
        executable = split_args[0].strip('"') if split_args else "abaqus"
        return [shutil.which(executable) or executable, *split_args[1:], *args]

    def _run_and_record(self, command: list[str], attempt_dir: Path, stem: str) -> subprocess.CompletedProcess[str]:
        LOGGER.info("Running command in %s: %s", attempt_dir, command)
        try:
            suffix = Path(command[0]).suffix.lower()
            if os.name == "nt" and suffix in {".bat", ".cmd"}:
                completed = subprocess.run(subprocess.list2cmdline(command), cwd=attempt_dir, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, shell=True)
            else:
                completed = subprocess.run(command, cwd=attempt_dir, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        except OSError as exc:
            completed = subprocess.CompletedProcess(command, 127, "", str(exc))
        (attempt_dir / f"{stem}.stdout.txt").write_text(completed.stdout or "", encoding="utf-8")
        (attempt_dir / f"{stem}.stderr.txt").write_text(completed.stderr or "", encoding="utf-8")
        return completed

    def _markdown_report(self, task: RigidFrameInput, report: dict[str, Any]) -> str:
        lines = [
            f"# V7 Closed-Loop Rigid-Frame Report: {task.project_name}",
            "",
            f"- Spans: `{task.spans_m}` m",
            f"- Prestress mode: `{task.prestress_mode}`",
            f"- Review profile: `{report['design_code_profile']['name']}`",
            f"- Final status: `{report['status']}`",
            "",
            "## Agent Loop",
            "",
            "`fast screening -> C3D8R/T3D2 generation -> Abaqus solve -> ODB diagnosis -> deterministic adjustment -> review gate`",
            "",
            "## Iterations",
        ]
        for attempt in report["attempts"]:
            lines.append(f"- Iteration `{attempt['iteration']}`: status=`{attempt['status']}`")
            for action in attempt.get("actions", []):
                lines.append(f"  - Action: {action}")
            for issue in attempt.get("issues", []):
                lines.append(f"  - `{issue['severity']}` `{issue['code']}`: {issue['message']}")
        lines.extend(
            [
                "",
                "## Review Boundary",
                "",
                "The V7 profile is a conservative deterministic screening gate. It does not replace formal load-combination, construction-stage, anchorage-zone, durability, fatigue, or code-clause verification.",
                "",
            ]
        )
        return "\n".join(lines)
