"""V2 multi-agent workflow for producing reviewable Abaqus models."""

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

from bridge_fem_agent.agents.boundary_agent import BoundaryAgent
from bridge_fem_agent.agents.document_agent import DocumentAgent
from bridge_fem_agent.agents.geometry_agent import GeometryAgent
from bridge_fem_agent.agents.idealization_agent import IdealizationAgent
from bridge_fem_agent.agents.load_agent import LoadAgent
from bridge_fem_agent.agents.material_agent import MaterialAgent
from bridge_fem_agent.agents.mesh_agent import MeshAgent
from bridge_fem_agent.agents.qa_agent import QaAgent
from bridge_fem_agent.agents.reference_agent import ReferenceAgent
from bridge_fem_agent.builders.abaqus_cae_builder import AbaqusCaeScriptBuilder
from bridge_fem_agent.config import WorkflowConfig

LOGGER = logging.getLogger(__name__)


class ModelProductionWorkflow:
    """Coordinate deterministic agents and optionally invoke Abaqus/CAE."""

    def __init__(self, abaqus_command: str = "abaqus") -> None:
        self.abaqus_command = abaqus_command
        self.document_agent = DocumentAgent()
        self.reference_agent = ReferenceAgent()
        self.geometry_agent = GeometryAgent()
        self.idealization_agent = IdealizationAgent()
        self.material_agent = MaterialAgent()
        self.mesh_agent = MeshAgent()
        self.boundary_agent = BoundaryAgent()
        self.load_agent = LoadAgent()
        self.qa_agent = QaAgent()
        self.builder = AbaqusCaeScriptBuilder()

    def run(self, input_path: Path, workdir: Path, samples_dir: Path | None = None, build_cae: bool = False) -> dict[str, Any]:
        workdir = WorkflowConfig.ensure_workdir(workdir)
        state = self.document_agent.load(input_path)
        state = self.reference_agent.analyze(state, samples_dir)
        for agent in (
            self.geometry_agent,
            self.idealization_agent,
            self.material_agent,
            self.mesh_agent,
            self.boundary_agent,
            self.load_agent,
        ):
            state = agent.plan(state)
        state = self.qa_agent.review(state)

        model_plan = {
            "project_name": state.semantic.project_name,
            "bridge_type": state.semantic.bridge_type,
            "analysis_type": state.semantic.analysis_type,
            "semantic_model": state.semantic.to_dict(),
            "reference_patterns": state.reference_patterns,
            **state.model_plan,
        }
        script_path = self.builder.write(model_plan, workdir)
        plan_path = workdir / "model_plan.json"
        qa_json_path = workdir / "qa_report.json"
        qa_md_path = workdir / "qa_report.md"
        plan_path.write_text(json.dumps(model_plan, indent=2, ensure_ascii=False), encoding="utf-8")

        qa_report = {
            "status": "pass" if not any(item.level == "error" for item in state.qa_findings) else "failed",
            "agent_messages": [asdict(item) for item in state.agent_messages],
            "qa_findings": [asdict(item) for item in state.qa_findings],
            "generated_script": str(script_path),
        }
        qa_json_path.write_text(json.dumps(qa_report, indent=2, ensure_ascii=False), encoding="utf-8")
        qa_md_path.write_text(self._qa_markdown(qa_report), encoding="utf-8")

        cae_result = None
        if build_cae:
            cae_result = self._run_abaqus_cae(script_path, workdir)
            if cae_result["status"] != "success":
                qa_report["status"] = "failed"
                qa_report["agent_messages"].append(
                    {"agent": "AbaqusCaeBuilder", "level": "error", "message": "Abaqus/CAE noGUI did not generate both .cae and .inp."}
                )
                qa_json_path.write_text(json.dumps(qa_report, indent=2, ensure_ascii=False), encoding="utf-8")
                qa_md_path.write_text(self._qa_markdown(qa_report), encoding="utf-8")

        report = {
            "status": qa_report["status"],
            "workdir": str(workdir),
            "model_plan": str(plan_path),
            "qa_report_json": str(qa_json_path),
            "qa_report_md": str(qa_md_path),
            "build_script": str(script_path),
            "build_cae": build_cae,
            "cae_result": cae_result,
        }
        (workdir / "model_production_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        LOGGER.info("Model production workflow finished with status '%s'.", report["status"])
        return report

    def _run_abaqus_cae(self, script_path: Path, workdir: Path) -> dict[str, Any]:
        command = self._build_cae_command(script_path)
        completed = self._run_subprocess(command, workdir)
        stdout_path = workdir / "abaqus_cae_build.stdout.txt"
        stderr_path = workdir / "abaqus_cae_build.stderr.txt"
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        stdout = completed.stdout.upper()
        stderr = completed.stderr.upper()
        cae_file = workdir / (script_path.name.replace("_build_model.py", ".cae"))
        inp_file = workdir / (script_path.name.replace("_build_model.py", ".inp"))
        generated = cae_file.exists() and inp_file.exists()
        has_error = "ABAQUS ERROR" in stdout or "TRACEBACK" in stderr or "ERROR:" in stderr
        return {
            "status": "success" if generated and not has_error else "failed",
            "return_code": completed.returncode,
            "command": command,
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "cae_file": str(cae_file),
            "inp_file": str(inp_file),
        }

    def _build_cae_command(self, script_path: Path) -> list[str]:
        split_args = shlex.split(self.abaqus_command, posix=(os.name != "nt"))
        if not split_args:
            split_args = ["abaqus"]
        executable = split_args[0].strip('"')
        resolved = shutil.which(executable) or executable
        return [resolved, *split_args[1:], "cae", f"noGUI={script_path.name}"]

    def _run_subprocess(self, command: list[str], workdir: Path) -> subprocess.CompletedProcess[str]:
        suffix = Path(command[0]).suffix.lower()
        if os.name == "nt" and suffix in {".bat", ".cmd"}:
            return subprocess.run(subprocess.list2cmdline(command), cwd=workdir, capture_output=True, text=True, check=False, shell=True)
        return subprocess.run(command, cwd=workdir, capture_output=True, text=True, check=False)

    def _qa_markdown(self, qa_report: dict[str, Any]) -> str:
        lines = ["# Model Production QA Report", "", f"- Status: `{qa_report['status']}`", f"- Build script: `{qa_report['generated_script']}`", "", "## Agent Messages"]
        for item in qa_report["agent_messages"]:
            lines.append(f"- `{item['agent']}` `{item['level']}` {item['message']}")
        lines.append("")
        lines.append("## QA Findings")
        if not qa_report["qa_findings"]:
            lines.append("- No QA findings.")
        else:
            for item in qa_report["qa_findings"]:
                lines.append(f"- `{item['level']}` {item['message']}")
        return "\n".join(lines) + "\n"
