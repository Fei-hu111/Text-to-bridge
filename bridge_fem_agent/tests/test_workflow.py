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

    def test_solid_model_production_generates_entity_analysis_script(self) -> None:
        temp_root = ROOT / "runs" / "_test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            tmp_path = Path(tmp)
            task = {
                "project_name": "three_span_solid_bridge",
                "bridge_type": "continuous_girder",
                "analysis_type": "static",
                "model_level": "solid",
                "spans_m": [30.0, 40.0, 30.0],
                "deck": {"width_m": 8.0},
                "girder": {"count": 1, "height_m": 2.2, "width_m": 8.0, "section_type": "rectangular_solid"},
                "materials": {"concrete": {"elastic_modulus_pa": 3.45e10, "poisson_ratio": 0.2, "density_kg_m3": 2500}},
                "supports": [
                    {"name": "P0", "x_m": 0.0, "type": "pinned"},
                    {"name": "P1", "x_m": 30.0, "type": "roller"},
                    {"name": "P2", "x_m": 70.0, "type": "roller"},
                    {"name": "P3", "x_m": 100.0, "type": "roller"},
                ],
                "mesh": {"target_size_m": 2.0, "element_type": "C3D8R"},
                "loads": [
                    {"type": "gravity", "name": "Gravity"},
                    {"type": "uniform_deck_pressure", "name": "DeckPressure", "value_pa": 5000.0},
                ],
            }
            input_path = tmp_path / "solid.json"
            input_path.write_text(json.dumps(task), encoding="utf-8")
            workdir = tmp_path / "solid_model"

            code = main([
                "--workflow",
                "model-production",
                "--input",
                str(input_path),
                "--workdir",
                str(workdir),
                "--samples-dir",
                str(ROOT / "samples"),
            ])

            self.assertEqual(code, 0)
            script_text = (workdir / "three_span_solid_bridge_build_model.py").read_text(encoding="utf-8")
            self.assertIn("BaseSolidExtrude", script_text)
            self.assertIn("HomogeneousSolidSection", script_text)
            self.assertIn("C3D8R", script_text)
            self.assertIn("model.Pressure", script_text)
            plan = json.loads((workdir / "model_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["idealization"]["selected_model_level"], "solid")

    def test_rigid_frame_v3_generates_optimized_review_model(self) -> None:
        temp_root = ROOT / "runs" / "_test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            workdir = Path(tmp) / "rigid_frame_v3"

            code = main([
                "--workflow",
                "rigid-frame-v3",
                "--spans",
                "90",
                "160",
                "90",
                "--pier-height",
                "60",
                "--workdir",
                str(workdir),
                "--max-design-iterations",
                "8",
                "--model-level",
                "beam",
            ])

            self.assertEqual(code, 0)
            final_design = json.loads((workdir / "final_design.json").read_text(encoding="utf-8"))
            response = final_design["response"]
            self.assertEqual(response["status"], "pass")
            self.assertLessEqual(response["max_deflection_m"], response["deflection_limit_m"])
            self.assertTrue((workdir / "optimization_history.json").exists())
            self.assertTrue((workdir / "optimization_report.md").exists())
            script_text = (workdir / "rigid_frame_90_160_90_rigid_frame_build.py").read_text(encoding="utf-8")
            self.assertIn("RigidFrameBridge", script_text)
            self.assertIn("model.BoxProfile", script_text)
            self.assertIn("Tendon-Pier01-Top", script_text)
            self.assertIn("Load-prestress-equivalent", script_text)
            self.assertIn("B31", script_text)
            self.assertIn("PierSection", script_text)

    def test_rigid_frame_v3_generates_solid_review_model(self) -> None:
        temp_root = ROOT / "runs" / "_test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            workdir = Path(tmp) / "rigid_frame_v3_solid"

            code = main([
                "--workflow",
                "rigid-frame-v3",
                "--spans",
                "90",
                "160",
                "90",
                "--pier-height",
                "60",
                "--workdir",
                str(workdir),
                "--max-design-iterations",
                "8",
                "--model-level",
                "solid",
            ])

            self.assertEqual(code, 0)
            report = json.loads((workdir / "rigid_frame_v3_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["model_level"], "solid")
            script_text = (workdir / "rigid_frame_90_160_90_rigid_frame_solid_build.py").read_text(encoding="utf-8")
            self.assertIn("BaseSolidExtrude", script_text)
            self.assertIn("RigidFrameSolid", script_text)
            self.assertIn("C3D8R", script_text)
            self.assertIn("model.EmbeddedRegion", script_text)
            self.assertIn('.Expansion(table=((plan["prestress_alpha_per_c"],),))', script_text)
            self.assertIn('name="Prestress", previous="Initial"', script_text)
            self.assertIn('name="ServiceLoad", previous="Prestress"', script_text)
            self.assertIn("model.Temperature", script_text)
            self.assertIn("Load-prestress-equivalent", script_text)
            self.assertIn("PIER01_BASE", script_text)

    def test_rigid_frame_v4_generates_hollow_box_solid_script(self) -> None:
        temp_root = ROOT / "runs" / "_test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            workdir = Path(tmp) / "rigid_frame_v4_hollow"

            code = main([
                "--workflow",
                "rigid-frame-v4",
                "--spans",
                "90",
                "160",
                "90",
                "--pier-height",
                "60",
                "--workdir",
                str(workdir),
                "--max-design-iterations",
                "8",
            ])

            self.assertEqual(code, 0)
            report = json.loads((workdir / "rigid_frame_v4_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["model_level"], "hollow-solid")
            self.assertTrue((workdir / "rigid_frame_v3_report.json").exists())
            script_text = (workdir / "rigid_frame_90_160_90_rigid_frame_hollow_box_build.py").read_text(encoding="utf-8")
            self.assertIn("HollowBoxRigidFrame", script_text)
            self.assertIn("GIRDER_CONCRETE_ELEMENTS", script_text)
            self.assertIn("PIER_CONCRETE_ELEMENTS", script_text)
            self.assertIn("C3D8R", script_text)
            self.assertIn("T3D2", script_text)
            self.assertIn("model.EmbeddedRegion", script_text)
            self.assertIn("PRESTRESS_NODES", script_text)
            self.assertIn("model.Temperature", script_text)

    def test_rigid_frame_v5_generates_construction_solid_script(self) -> None:
        temp_root = ROOT / "runs" / "_test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            workdir = Path(tmp) / "rigid_frame_v5_construction"

            code = main([
                "--workflow",
                "rigid-frame-v5",
                "--spans",
                "90",
                "160",
                "90",
                "--pier-height",
                "60",
                "--workdir",
                str(workdir),
                "--max-design-iterations",
                "8",
            ])

            self.assertEqual(code, 0)
            report = json.loads((workdir / "rigid_frame_v5_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["model_level"], "construction-solid")
            script_text = (workdir / "rigid_frame_90_160_90_rigid_frame_construction_solid_build.py").read_text(encoding="utf-8")
            self.assertIn("ConstructionSolidRigidFrame", script_text)
            self.assertIn("SOLID_DIAPHRAGM_ELEMENTS", script_text)
            self.assertIn("left_end_solid", script_text)
            self.assertIn("pier01_solid", script_text)
            self.assertIn("bottom_slab_thickness_m", script_text)
            self.assertIn("Tendon-Continuity-Top", script_text)
            self.assertIn("Tendon-Continuity-Bottom", script_text)
            self.assertIn("mesh_controls", script_text)
            self.assertIn("axis_points", script_text)
            self.assertIn("C3D8R", script_text)
            self.assertIn("model.EmbeddedRegion", script_text)
            self.assertIn("PRESTRESS_NODES", script_text)
            self.assertIn("model.Temperature", script_text)
            self.assertIn('if plan["prestress_mode"] == "equivalent_load":', script_text)
            verification = json.loads((workdir / "prestress_verification.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["prestress_mode"], "thermal_strain")
            self.assertTrue(all(item["stress_reasonable"] for item in verification["tendon_groups"]))
            self.assertTrue(all(item["delta_temperature_c"] < 0.0 for item in verification["tendon_groups"]))

    def test_rigid_frame_v5_supports_legacy_equivalent_prestress_mode(self) -> None:
        temp_root = ROOT / "runs" / "_test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            workdir = Path(tmp) / "rigid_frame_v5_equivalent"
            code = main([
                "--workflow",
                "rigid-frame-v5",
                "--spans",
                "90",
                "160",
                "90",
                "--pier-height",
                "60",
                "--workdir",
                str(workdir),
                "--prestress-mode",
                "equivalent_load",
            ])

            self.assertEqual(code, 0)
            verification = json.loads((workdir / "prestress_verification.json").read_text(encoding="utf-8"))
            self.assertEqual(verification["prestress_mode"], "equivalent_load")


if __name__ == "__main__":
    unittest.main()
