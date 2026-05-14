"""Write JSON and Markdown workflow reports."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


class ReportWriter:
    """Persist machine-readable and human-readable analysis reports."""

    def write(self, report: dict[str, Any], workdir: Path) -> tuple[Path, Path]:
        json_path = workdir / "report.json"
        md_path = workdir / "report.md"
        json_path.write_text(json.dumps(self._jsonable(report), indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(self._markdown(report), encoding="utf-8")
        return json_path, md_path

    def _markdown(self, report: dict[str, Any]) -> str:
        lines = [
            f"# Bridge FEM Analysis Report: {report['project_name']}",
            "",
            f"- Status: `{report['status']}`",
            f"- Attempts: `{len(report['attempts'])}`",
            f"- Dry run: `{report['dry_run']}`",
            "",
            "## Attempts",
        ]
        for attempt in report["attempts"]:
            lines.extend(
                [
                    f"### Attempt {attempt['attempt']}",
                    f"- Input: `{attempt['input_file']}`",
                    f"- Job: `{attempt['job_name']}`",
                    f"- Status: `{attempt['status']}`",
                    f"- Return code: `{attempt['return_code']}`",
                ]
            )
            if attempt.get("issues"):
                lines.append("- Issues:")
                lines.extend(f"  - `{issue['category']}` {issue['message']}" for issue in attempt["issues"])
            if attempt.get("repairs"):
                lines.append("- Repairs:")
                lines.extend(f"  - `{action['category']}` {action['description']}" for action in attempt["repairs"])

        results = report.get("results", {})
        lines.extend(["", "## Results"])
        lines.append(f"- Maximum displacement: `{results.get('max_displacement')}`")
        lines.append(f"- Maximum stress: `{results.get('max_stress')}`")
        lines.append(f"- Support reactions: `{results.get('support_reactions')}`")
        lines.append(f"- Modal frequencies: `{results.get('modal_frequencies')}`")
        return "\n".join(lines) + "\n"

    def _jsonable(self, value: Any) -> Any:
        if is_dataclass(value):
            return self._jsonable(asdict(value))
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {key: self._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        return value
