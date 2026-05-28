# V2 Multi-Agent Abaqus Model Production

This document describes the second-stage workflow in Text to Bridge: deterministic multi-agent production of reviewable Abaqus bridge finite element models.

## Goal

V2 extends the V1 `.inp` analysis workflow into a more general model-production workflow. The goal is to support bridge model creation from structured design information, and later from drawings and text.

The workflow does not directly convert drawings into Abaqus files. Instead, it uses an auditable intermediate representation:

```text
drawings / text / structured JSON
  -> Bridge Semantic Model
  -> Multi-agent Model Plan
  -> Abaqus/CAE Python Script
  -> .cae / .inp
  -> Optional Abaqus/Standard Verification
```

This separation is important because drawing recognition may be uncertain, while Abaqus model generation must be deterministic and reviewable.

## Agent Responsibilities

### DocumentAgent

Reads the input JSON file and creates a `BridgeSemanticModel`.

Future versions can add PDF, CAD, OCR, or drawing-table extraction before this stage.

### ReferenceAgent

Scans local reference journals under:

```text
samples/**/*.jnl
```

It counts patterns such as:

- `BaseWire`
- `BeamSection`
- `BaseSolidExtrude`
- `HomogeneousSolidSection`
- `ConnectorSection`
- `seedPart`
- `seedEdgeByNumber`
- `generateMesh`
- `Gravity`
- `Pressure`
- `StaticStep`

The agent does not copy the sample models. It uses them as local modelling-style references.

### GeometryAgent

Creates longitudinal bridge stations, span breakpoints, support stations, and modelling coordinates.

The current coordinate convention is:

```text
X = bridge longitudinal direction
Y = bridge transverse direction
Z = vertical direction
```

### IdealizationAgent

Selects the finite element idealization.

Current supported values:

- `beam`
- `solid`

Beam models use B31 elements. Solid models use C3D8R elements by default.

### MaterialAgent

Prepares material definitions and section data.

For the current examples, concrete is defined with:

- density
- elastic modulus
- Poisson's ratio

### MeshAgent

Selects element type and target mesh size.

For beam models, the mesh is applied along the bridge axis. For solid models, `seedPart` and `generateMesh` are used in the Abaqus/CAE script.

### BoundaryAgent

Maps engineering support names to Abaqus boundary conditions.

Current support types:

- `fixed`
- `pinned`
- `roller`
- `roller_x`
- `roller_y`
- `vertical`

For solid models, support constraints are applied to bottom support node sets.

### LoadAgent

Maps load semantics into Abaqus load definitions.

Current load types:

- gravity
- uniform deck pressure
- concentrated force

For beam models, deck pressure is converted into a beam line load. For solid models, the workflow first tries to create a top surface pressure. If Abaqus/CAE cannot create a stable surface after solid partitioning, it falls back to an equivalent top-node vertical force distribution.

### QaAgent

Performs pre-generation QA checks:

- bridge length is positive
- supports exist
- end supports are present
- materials exist
- loads exist
- mesh size is valid

The QA output is written to:

```text
qa_report.json
qa_report.md
```

### AbaqusCaeScriptBuilder

Creates a reviewable Abaqus/CAE Python build script:

```text
<project_name>_build_model.py
```

When `--build-cae` is used, the workflow calls:

```text
abaqus cae noGUI=<project_name>_build_model.py
```

The generated files include:

```text
<project_name>.cae
<project_name>.inp
```

## Beam Model Workflow

Command:

```powershell
python main.py --workflow model-production --input bridge_fem_agent\examples\three_span_agent_bridge.json --workdir runs\three_span_agent_bridge_v2_cae --samples-dir samples --build-cae
```

Beam model features:

- Abaqus `BaseWire`
- B31 beam elements
- rectangular beam section
- support sets at bridge stations
- gravity load
- line load from deck pressure
- static analysis step

Verified Abaqus/Standard status:

```text
THE ANALYSIS HAS COMPLETED SUCCESSFULLY
```

## Solid Model Workflow

Command:

```powershell
python main.py --workflow model-production --input bridge_fem_agent\examples\three_span_solid_bridge.json --workdir runs\three_span_solid_bridge_v2_cae --samples-dir samples --build-cae
```

Solid model features:

- Abaqus `BaseSolidExtrude`
- rectangular solid girder
- partitioning at support stations
- `HomogeneousSolidSection`
- C3D8R solid elements
- `seedPart`
- `generateMesh`
- bottom support node sets
- gravity load
- deck pressure or equivalent top-node load fallback
- static analysis step

Verified local solid model directory:

```text
E:\Desktop\Text to bridge\runs\three_span_solid_bridge_v2_cae_retry2
```

Generated files:

```text
three_span_solid_bridge.cae
three_span_solid_bridge.inp
three_span_solid_bridge_check.odb
three_span_solid_bridge_check_odb_results.json
```

Verified Abaqus/Standard status:

```text
THE ANALYSIS HAS COMPLETED SUCCESSFULLY
```

Extracted ODB summary:

```text
max_displacement = 1.3075553125059352
max_stress = 1051906.5
```

## Solid Model Visualization

### Figure 1. Model and Loads

![Solid model and loads](docs/images/v2_model_load.png)

### Figure 2. Mesh Model

![Solid mesh model](docs/images/v2_mesh.png)

### Figure 3. Stress Field

![Solid stress field](docs/images/v2_stress.png)

### Figure 4. Displacement Field

![Solid displacement field](docs/images/v2_displacement.png)

### Figure 5. Reaction Force Field

![Solid reaction force field](docs/images/v2_reaction.png)

## Current Limitations

- Drawing/PDF/CAD recognition is not implemented yet.
- The solid model is currently a simplified rectangular solid girder.
- The pressure load may fall back to equivalent nodal force if Abaqus/CAE surface creation fails.
- Solid support reaction extraction needs a dedicated node-set aggregation improvement.
- Connector bearings and detailed track-slab modelling are future work.

## Next Steps

Recommended next development steps:

1. Add a `DrawingAgent` for PDF/CAD geometry extraction.
2. Add a `SectionAgent` for box girder, slab, arch, pylon, and cable section parsing.
3. Add shell and mixed modelling paths.
4. Add connector-based support and bearing modelling.
5. Add load-combination and vehicle-load agents.
6. Add automated reaction balance checks after analysis.
