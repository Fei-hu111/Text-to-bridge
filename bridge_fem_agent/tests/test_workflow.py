"""Smoke tests for the first bridge FEM workflow.

The tests use only Python's standard library so they can run without installing
pytest or other packages on C/D drives.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge_fem_agent.main import main
from bridge_fem_agent.diagnosis.error_classifier import DiagnosticIssue
from bridge_fem_agent.repair.repair_engine import RepairEngine


class WorkflowSmokeTest(unittest.TestCase):
    def test_dry_run_workflow(self) -> None:
        temp_root = ROOT / "runs" / "_test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            tmp_path = Path(tmp)
            task = {
                "project_name": "simple_girder_bridge",
                "bridge_type": "simply_supported_girder",
                "analysis_type": "static",
                "geometry": {"span_m": 30.0, "deck_width_m": 10.0, "girder_count": 4},
                "materials": {"concrete": {"elastic_modulus_pa": 3.45e10, "poisson_ratio": 0.2, "density_kg_m3": 2500}},
                "loads": {"gravity": True, "uniform_deck_load_pa": 5000},
                "boundary_conditions": {"left_support": "pinned", "right_support": "roller"},
            }
            input_path = tmp_path / "bridge.json"
            input_path.write_text(json.dumps(task), encoding="utf-8")
            workdir = tmp_path / "run"

            code = main(["--input", str(input_path), "--workdir", str(workdir), "--max-repairs", "3", "--dry-run"])

            self.assertEqual(code, 0)
            self.assertTrue((workdir / "simple_girder_bridge_attempt_0.inp").exists())
            self.assertTrue((workdir / "report.json").exists())
            report = json.loads((workdir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "success")
            self.assertEqual(report["results"]["max_displacement"], 0.00125)

    def test_repair_writes_new_attempt_without_overwriting_original(self) -> None:
        temp_root = ROOT / "runs" / "_test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            workdir = Path(tmp)
            original = workdir / "broken_attempt_0.inp"
            original_text = "\n".join(
                [
                    "*Heading",
                    "*Part, name=BRIDGE_GIRDER",
                    "*Node",
                    "1, 0., 0., 0.",
                    "2, 10., 0., 0.",
                    "*Element, type=B31, elset=EALL",
                    "1, 1, 2",
                    "*Beam Section, elset=EALL, material=CONCRETE, section=RECT",
                    "1., 1.",
                    "0., 0., -1.",
                    "*End Part",
                    "",
                ]
            )
            original.write_text(original_text, encoding="utf-8")
            issues = [
                DiagnosticIssue("undefined_material", "error", "material is undefined", "broken.msg"),
                DiagnosticIssue("step_definition_error", "error", "step definition is missing", "broken.msg"),
            ]

            repaired_path, actions = RepairEngine().repair(original, issues, "broken", 1, workdir)

            self.assertEqual(original.read_text(encoding="utf-8"), original_text)
            self.assertEqual(repaired_path, workdir / "broken_attempt_1.inp")
            self.assertTrue(repaired_path.exists())
            repaired_text = repaired_path.read_text(encoding="utf-8")
            self.assertIn("*Material, name=CONCRETE", repaired_text)
            self.assertIn("*Step, name=STATIC_STEP", repaired_text)
            self.assertGreaterEqual(len(actions), 2)

    def test_model_production_generates_reviewable_abaqus_script(self) -> None:
        temp_root = ROOT / "runs" / "_test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            tmp_path = Path(tmp)
            task = {
                "project_name": "three_span_agent_bridge",
                "bridge_type": "continuous_girder",
                "analysis_type": "static",
                "spans_m": [30.0, 40.0, 30.0],
                "deck": {"width_m": 12.0},
                "girder": {"count": 1, "height_m": 2.2, "width_m": 8.0},
                "materials": {"concrete": {"elastic_modulus_pa": 3.45e10, "poisson_ratio": 0.2, "density_kg_m3": 2500}},
                "supports": [
                    {"name": "P0", "x_m": 0.0, "type": "pinned"},
                    {"name": "P1", "x_m": 30.0, "type": "roller"},
                    {"name": "P2", "x_m": 70.0, "type": "roller"},
                    {"name": "P3", "x_m": 100.0, "type": "roller"},
                ],
                "loads": [
                    {"type": "gravity", "name": "Gravity"},
                    {"type": "uniform_deck_pressure", "name": "DeckUniformLoad", "value_pa": 5000.0},
                ],
            }
            input_path = tmp_path / "three_span.json"
            input_path.write_text(json.dumps(task), encoding="utf-8")
            samples_dir = tmp_path / "samples"
            samples_dir.mkdir()
            (samples_dir / "sample.jnl").write_text("BaseWire()\nBeamSection()\nseedPart()\ngenerateMesh()\nGravity()\n", encoding="utf-8")
            workdir = tmp_path / "model"

            code = main([
                "--workflow",
                "model-production",
                "--input",
                str(input_path),
                "--workdir",
                str(workdir),
                "--samples-dir",
                str(samples_dir),
            ])

            self.assertEqual(code, 0)
            script_path = workdir / "three_span_agent_bridge_build_model.py"
            self.assertTrue(script_path.exists())
            script_text = script_path.read_text(encoding="utf-8")
            self.assertIn("model.RectangularProfile", script_text)
            self.assertIn("model.LineLoad", script_text)
            self.assertTrue((workdir / "model_plan.json").exists())
            qa = json.loads((workdir / "qa_report.json").read_text(encoding="utf-8"))
            self.assertEqual(qa["status"], "pass")


if __name__ == "__main__":
    unittest.main()
