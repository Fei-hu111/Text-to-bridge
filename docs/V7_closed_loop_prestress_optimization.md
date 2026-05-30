# V7 Closed-Loop Prestress Optimization

V7 turns the rigid-frame workflow from a one-pass model generator into a
deterministic multi-agent optimization loop. The implementation remains fully
local and does not call any external LLM API.

## Goal

Given a three-span continuous rigid-frame bridge, V7 generates a construction
solid Abaqus model, solves the prestress and service steps, extracts ODB
metrics, diagnoses whether the design is acceptable, and adjusts section or
tendon parameters when the response is outside the configured preliminary
review limits.

## Agent Workflow

```text
span input / JSON task
  -> DesignCodeAgent
  -> fast deterministic section and tendon screening
  -> AbaqusBuildAgent using the V5/V6 construction-solid builder
  -> Abaqus/CAE noGUI generation of .cae and .inp
  -> Abaqus/Standard solve
  -> OdbResultAgent extraction
  -> PrestressDiagnosisAgent
  -> PrestressOptimizationAgent
  -> ReviewGateAgent
```

The workflow has two nested loops:

- Inner solver loop: captures CAE/Standard failures and classifies likely
  causes such as zero pivot, embedded-region problems, convergence failure, or
  inactive temperature regions.
- Outer engineering loop: reads real ODB metrics and adjusts geometry or tendon
  layout through deterministic rules.

## Model Basis

The generated review model keeps the V5/V6 modelling assumptions:

- concrete girder and pier regions use `C3D8R`;
- prestress tendons use embedded `T3D2`;
- tendon prestress is applied through thermal strain, not equivalent balancing
  load;
- the analysis contains a `Prestress` step followed by a `ServiceLoad` step;
- the box girder keeps hollow regions, end solid blocks, pier diaphragm solid
  regions, and variable bottom slab thickness.

## Review Metrics

The default profile is `jtg3362-conservative`. It is a preliminary engineering
screening profile, not a formal design-code certificate.

The V7 gate checks:

- prestress-stage vertical camber;
- service-stage maximum displacement;
- concrete `S11` p95 and p99 in the `Prestress` step;
- concrete `S11` p95 and p99 in the `ServiceLoad` step;
- tensile sampling fraction for broad-compression screening;
- tendon `S11` range;
- local tensile hotspots that require refined diaphragm, support, and anchorage
  review.

The default limits used in the current implementation are:

```text
service displacement limit       = main span / 600
prestress camber limit           = main span / 3500
prestress concrete S11 p95/p99   = 0.50 / 1.50 MPa
service concrete S11 p95/p99     = 1.80 / 4.00 MPa
tensile sampling fraction limit  = 0.35
tendon S11 range                 = 700 to 1400 MPa
local hotspot review threshold   = 10 MPa
```

## Adjustment Rules

When ODB diagnosis returns `needs_adjustment`, the optimization agent applies
targeted rule changes:

- excessive service displacement: increase girder depth, bottom slab thickness,
  and midspan positive-moment tendon count;
- prestress-stage broad concrete tension or excessive camber: reduce tendon
  eccentricity, increase section area, and add balanced continuity tendons;
- service-stage broad concrete tension: add pier-top, midspan, and continuity
  tendon capacity and increase section stiffness;
- tendon overstress: reduce jacking stress;
- tendon understress: increase jacking stress within the deterministic model
  envelope;
- numerical solver failure with a retriable category: apply a conservative
  section increase and reduce eccentricity before retrying.

All actions are written into `rigid_frame_v7_report.json`,
`rigid_frame_v7_report.md`, and the per-iteration attempt records.

## Verified Run

The default `90 + 160 + 90 m` case was solved through Abaqus/CAE and
Abaqus/Standard:

```powershell
python main.py --workflow rigid-frame-v7 --spans 90 160 90 --pier-height 60 --workdir runs\rigid_frame_v7_closed_loop_verified_90_160_90 --v7-max-iterations 2
```

Verification directory:

```text
runs/rigid_frame_v7_closed_loop_verified_90_160_90/
```

The Abaqus status file reported:

```text
THE ANALYSIS HAS COMPLETED SUCCESSFULLY
```

Final gate status:

```text
pass_with_local_review
```

Key ODB metrics:

```text
Prestress camber abs             = 0.0434 m  (limit 0.0457 m)
Service max displacement         = 0.1998 m  (limit 0.2667 m)
Prestress concrete S11 p95/p99   = 0.395 / 0.863 MPa
Service concrete S11 p95/p99     = 1.130 / 2.801 MPa
Prestress tensile fraction       = 0.311
Service tensile fraction         = 0.334
Service tendon S11               = 725.0 to 955.4 MPa
```

The only V7 warning is a local tensile hotspot of about `19.2 MPa`. The global
screening metrics pass, but that hotspot is intentionally kept as a manual
review item because it should be evaluated with a refined support, diaphragm,
and anchorage-zone model.

## Output Files

Each V7 run writes:

```text
rigid_frame_v7_semantic.json
v7_fast_screening_history.json
rigid_frame_v7_report.json
rigid_frame_v7_report.md
iteration_00/
  candidate_design.json
  prestress_verification.json
  *_rigid_frame_construction_solid_build.py
  *.cae
  *.inp
  *.sta / *.msg / *.dat / *.odb
  *_results.json
  v7_diagnosis.json
```

## Current Limits

V7 is a reliable deterministic workflow scaffold, but it is still a preliminary
engineering assistant. The following items remain future work:

- formal load combinations and code-clause checks;
- staged construction, creep, shrinkage, and time-dependent prestress loss;
- duct friction and anchorage slip;
- anchorage-zone and diaphragm local mesh refinement;
- longitudinal tendon family optimization with more realistic duct geometry;
- LLM policy selection for choosing which deterministic tool to call next.
