# V3 Rigid-Frame Multi-Agent Workflow

## Goal

V3 extends Text to Bridge from simple girder and solid-deck examples to a three-span continuous rigid-frame bridge workflow. It is designed around the local `samples/rigid frame` reference model, which contains a continuous rigid-frame bridge with prestress tendons, main girder, piers, bearings, concrete grades, staged loading concepts, and Abaqus/CAE modelling conventions.

The current implementation remains deterministic and does not call an external LLM API. It creates a reviewable Abaqus/CAE Python script and keeps a full design trace so that each section and prestress adjustment can be audited.

## Reference Model Findings

The sample CAE inspection captured these reusable modelling ideas:

- Separate concrete materials for girder and pier regions, matching C50/C40 style modelling.
- Main bridge components represented by named parts such as main-span, side-span, piers, abutments, steel/plate components, and support regions.
- Gravity, secondary dead load, road load, and human load concepts.
- Pier and support boundary conditions with named support regions.
- Multi-step analysis concepts including post-cast/static loading stages.
- Rich named sets/surfaces that make the model auditable.

V3 converts these ideas into a smaller global model that can be generated quickly and reviewed before moving to a high-fidelity solid or staged-construction model.

## Agent Roles

- **RigidFrameSemanticAgent**: normalizes user input from either JSON or three span lengths.
- **ReferenceInspectionAgent**: documents the observed Abaqus conventions from local rigid-frame samples.
- **SectionDesignAgent**: generates variable-depth girder control dimensions using span-based rules.
- **PrestressLayoutAgent**: places pier-top negative-moment tendons and midspan/side-span positive-moment tendons.
- **ResponseEvaluatorAgent**: estimates service deflection, compression, tension, and reaction balance using deterministic engineering formulas.
- **OptimizationAgent**: increases section depth, web/top/bottom slab dimensions, tendon count, and jacking assumptions until targets pass or the iteration limit is reached.
- **AbaqusBuildAgent**: writes the reviewable Abaqus/CAE Python build script.
- **ReportAgent**: writes JSON and Markdown reports with every design iteration and action.

These are implemented as Python modules under `bridge_fem_agent/rigid_frame/` rather than separate runtime processes. This keeps V3 lightweight while preserving a clean boundary for future multi-agent orchestration.

## Input Parameters

The minimum user input is three span lengths:

```powershell
python main.py --workflow rigid-frame-v3 --spans 90 160 90 --pier-height 60 --workdir runs\rigid_frame_v3_solid_cae --model-level solid
```

JSON input is also supported:

```json
{
  "project_name": "rigid_frame_90_160_90",
  "bridge_type": "continuous_rigid_frame",
  "spans_m": [90.0, 160.0, 90.0],
  "pier_height_m": 60.0,
  "deck_width_m": 12.5,
  "roadway_load_pa": 5000.0,
  "human_load_pa": 2500.0,
  "second_dead_load_pa": 2500.0
}
```

Optional targets include:

- `max_deflection_ratio`, default `600.0`
- `max_compressive_stress_pa`, default `1.8e7`
- `max_tensile_stress_pa`, default `1.8e6`
- `max_iterations`, default `8`

## Design Rules

The first design is produced from simple rigid-frame bridge proportions:

- pier-top girder depth approximately `main_span / 17`
- midspan girder depth approximately `main_span / 50`
- variable girder depth controlled by a parabolic height rule
- single-cell box-girder equivalent area and inertia for response estimation
- pier-top tendon groups for negative moment zones
- bottom tendon groups for midspan and side-span positive moment zones

The optimizer then applies rule-based repairs:

- excessive deflection increases pier depth, midspan depth, bottom slab thickness, and bottom tendon count
- excessive tensile stress increases top/bottom tendon capacity and girder depth
- excessive compressive stress increases concrete area through web, top slab, and depth changes while retaining prestress when tensile stress is also active

## Abaqus Model Output

The default solid Abaqus script creates:

- one monolithic three-span rigid-frame solid part
- C3D8R solid elements for the variable-depth girder and both piers
- a continuous pier-girder connection inside the same solid part
- T3D2 truss wire parts embedded in the concrete host for prestress tendon path review
- C50/C40 concrete and prestress steel material definitions
- left pinned abutment, right roller abutment, and fixed pier-base supports
- gravity, equivalent deck service load, and equivalent prestress balancing load
- static service analysis output requests for stress, displacement, and reaction

The B31 beam model remains available with `--model-level beam` for fast global review. In the solid model, tendon paths are embedded in the concrete host so their deformed shape follows the girder. Global prestress action is still represented by an equivalent balancing load. A later V4 can replace this with calibrated initial stress fields and staged construction.

## Abaqus Verification Snapshot

The default `90 + 160 + 90 m` solid example was generated with Abaqus/CAE noGUI and solved with Abaqus/Standard. The solved ODB summary was:

```text
max_displacement = 0.21310611564888263 m
max_stress = 17881846.0 Pa
```

This is below the default service targets of `L/600` deflection for the 160 m main span and `1.8e7 Pa` maximum stress.

## Output Files

Each run writes only to the selected work directory:

```text
runs/rigid_frame_v3_solid_cae_retry2/
  rigid_frame_semantic.json
  optimization_history.json
  final_design.json
  optimization_report.md
  rigid_frame_90_160_90_rigid_frame_solid_build.py
  rigid_frame_v3_report.json
  workflow.log
```

When `--build-cae` is used, Abaqus/CAE noGUI also writes:

```text
  rigid_frame_90_160_90.cae
  rigid_frame_90_160_90.inp
  rigid_frame_90_160_90_solid_check.odb
  abaqus_cae_build.stdout.txt
  abaqus_cae_build.stderr.txt
```

## Innovation Points

- Turns random three-span input into a complete rigid-frame bridge modelling plan.
- Uses deterministic multi-agent boundaries without requiring an external LLM service.
- Keeps the sample model as a local reference source while avoiding large CAE files in Git.
- Combines variable-section design and prestress layout before Abaqus generation.
- Records every design adjustment in JSON and Markdown for engineering review.
- Generates a reviewable Abaqus/CAE script rather than a black-box binary model.
- Leaves explicit TODO hooks for future LLM-assisted calibration and staged-construction reasoning.
