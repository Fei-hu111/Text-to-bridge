"""V3 workflow orchestration for continuous rigid-frame bridge design."""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from bridge_fem_agent.config import WorkflowConfig
from bridge_fem_agent.rigid_frame.builder import RigidFrameAbaqusBuilder
from bridge_fem_agent.rigid_frame.design import RigidFrameDesignFactory, RigidFrameOptimizer
from bridge_fem_agent.rigid_frame.hollow_box_builder import HollowBoxRigidFrameBuilder
from bridge_fem_agent.rigid_frame.schema import RigidFrameInput
from bridge_fem_agent.rigid_frame.solid_builder import RigidFrameSolidAbaqusBuilder

LOGGER = logging.getLogger(__name__)


class RigidFrameV3Workflow:
    """Run semantic generation, rule optimization, and model script production."""

    def __init__(self, abaqus_command: str = "abaqus") -> None:
        self.abaqus_command = abaqus_command
        self.design_factory = RigidFrameDesignFactory()
        self.optimizer = RigidFrameOptimizer()
        self.builder = RigidFrameAbaqusBuilder()
        self.solid_builder = RigidFrameSolidAbaqusBuilder()
        self.hollow_box_builder = HollowBoxRigidFrameBuilder()

    def run(self, task: RigidFrameInput, workdir: Path, build_cae: bool = False, model_level: str = "solid") -> dict[str, Any]:
        workdir = WorkflowConfig.ensure_workdir(workdir)
        initial = self.design_factory.create_initial(task)
        history = self.optimizer.optimize(task, initial)
        final_design = history[-1]

        semantic_path = workdir / "rigid_frame_semantic.json"
        history_path = workdir / "optimization_history.json"
        final_path = workdir / "final_design.json"
        report_path = workdir / "optimization_report.md"
        semantic_path.write_text(json.dumps(task.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        history_path.write_text(json.dumps([design.to_dict() for design in history], indent=2, ensure_ascii=False), encoding="utf-8")
        final_path.write_text(json.dumps(final_design.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

        if model_level == "beam":
            script_path = self.builder.write(task, final_design, workdir)
        elif model_level == "hollow-solid":
            script_path = self.hollow_box_builder.write(task, final_design, workdir)
        else:
            script_path = self.solid_builder.write(task, final_design, workdir)
        report_path.write_text(self._markdown_report(task, history, script_path, model_level), encoding="utf-8")

        cae_result = None
        if build_cae:
            cae_result = self._run_abaqus_cae(script_path, workdir)

        status = "pass" if final_design.response and final_design.response.status == "pass" else "needs_review"
        if cae_result and cae_result["status"] != "success":
            status = "failed"

        report_filename = "rigid_frame_v4_report.json" if model_level == "hollow-solid" else "rigid_frame_v3_report.json"
        report = {
            "status": status,
            "model_level": model_level,
            "workdir": str(workdir),
            "semantic": str(semantic_path),
            "optimization_history": str(history_path),
            "final_design": str(final_path),
            "optimization_report": str(report_path),
            "build_script": str(script_path),
            "cae_result": cae_result,
            "report": str(workdir / report_filename),
        }
        (workdir / report_filename).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if report_filename != "rigid_frame_v3_report.json":
            (workdir / "rigid_frame_v3_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        LOGGER.info("Rigid-frame workflow finished with status '%s'.", status)
        return report

    def _run_abaqus_cae(self, script_path: Path, workdir: Path) -> dict[str, Any]:
        command = self._build_cae_command(script_path)
        completed = self._run_subprocess(command, workdir)
        stdout_path = workdir / "abaqus_cae_build.stdout.txt"
        stderr_path = workdir / "abaqus_cae_build.stderr.txt"
        stdout_text = completed.stdout or ""
        stderr_text = completed.stderr or ""
        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")
        cae_file = self._expected_model_file(script_path, workdir, ".cae")
        inp_file = self._expected_model_file(script_path, workdir, ".inp")
        stderr = stderr_text.upper()
        stdout = stdout_text.upper()
        has_error = "ABAQUS ERROR" in stdout or "TRACEBACK" in stderr or "ERROR:" in stderr
        return {
            "status": "success" if cae_file.exists() and inp_file.exists() and not has_error else "failed",
            "return_code": completed.returncode,
            "command": command,
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "cae_file": str(cae_file),
            "inp_file": str(inp_file),
        }

    def _build_cae_command(self, script_path: Path) -> list[str]:
        split_args = shlex.split(self.abaqus_command, posix=(os.name != "nt"))
        executable = split_args[0].strip('"') if split_args else "abaqus"
        resolved = shutil.which(executable) or executable
        return [resolved, *split_args[1:], "cae", f"noGUI={script_path.name}"]

    def _expected_model_file(self, script_path: Path, workdir: Path, suffix: str) -> Path:
        stem = script_path.name
        for marker in ("_rigid_frame_hollow_box_build.py", "_rigid_frame_solid_build.py", "_rigid_frame_build.py"):
            if stem.endswith(marker):
                return workdir / stem.replace(marker, suffix)
        return workdir / f"{script_path.stem}{suffix}"

    def _run_subprocess(self, command: list[str], workdir: Path) -> subprocess.CompletedProcess[str]:
        suffix = Path(command[0]).suffix.lower()
        if os.name == "nt" and suffix in {".bat", ".cmd"}:
            return subprocess.run(subprocess.list2cmdline(command), cwd=workdir, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, shell=True)
        return subprocess.run(command, cwd=workdir, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)

    def _markdown_report(self, task: RigidFrameInput, history: list[Any], script_path: Path, model_level: str) -> str:
        final = history[-1]
        response = final.response
        version = "V4 Hollow-Box" if model_level == "hollow-solid" else "V3"
        lines = [
            f"# {version} Rigid-Frame Design Report: {task.project_name}",
            "",
            f"- Spans: `{task.spans_m}` m",
            f"- Pier height: `{task.resolved_pier_height_m:.3f}` m",
            f"- Deck width: `{task.deck_width_m:.3f}` m",
            f"- Model level: `{model_level}`",
            f"- Iterations: `{len(history)}`",
            f"- Build script: `{script_path}`",
            "",
            "## Final Section",
            f"- Pier-top girder depth: `{final.section.pier_height_m:.3f}` m",
            f"- Midspan girder depth: `{final.section.midspan_height_m:.3f}` m",
            f"- Web thickness: `{final.section.web_thickness_m:.3f}` m",
            f"- Bottom slab thickness: `{final.section.bottom_slab_thickness_m:.3f}` m",
            "",
            "## Final Prestress Tendon Groups",
        ]
        for group in final.tendon_groups:
            lines.append(f"- `{group.name}` role=`{group.role}` count=`{group.count}` eccentricity=`{group.eccentricity_m:.3f}` m")
        lines.extend(["", "## Estimated Response"])
        if response:
            lines.extend(
                [
                    f"- Status: `{response.status}`",
                    f"- Max deflection: `{response.max_deflection_m:.6f}` m",
                    f"- Deflection limit: `{response.deflection_limit_m:.6f}` m",
                    f"- Deflection ratio: `L/{response.deflection_ratio:.1f}`",
                    f"- Max compressive stress: `{response.max_compressive_stress_pa:.3e}` Pa",
                    f"- Max tensile stress: `{response.max_tensile_stress_pa:.3e}` Pa",
                ]
            )
        lines.extend(["", "## Optimization History"])
        for design in history:
            resp = design.response
            if resp:
                lines.append(f"- Iteration `{design.iteration}`: status=`{resp.status}`, deflection=`{resp.max_deflection_m:.6f}` m, tensile=`{resp.max_tensile_stress_pa:.3e}` Pa, compressive=`{resp.max_compressive_stress_pa:.3e}` Pa")
        return "\n".join(lines) + "\n"
