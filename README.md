# Text to Bridge

Text to Bridge is a Python + Abaqus workflow for automated bridge finite element model production, analysis execution, diagnosis, rule-based repair, result extraction, and reporting.

The project currently contains two complementary workflows:

- **V1 Analysis Workflow**: reads a structured bridge JSON file, generates an Abaqus `.inp`, runs Abaqus, diagnoses errors, applies deterministic repairs, extracts results, and writes reports.
- **V2 Multi-Agent Model Production Workflow**: uses deterministic agents to transform a bridge semantic model into a reviewable Abaqus/CAE Python script, then optionally builds `.cae` and `.inp` files through Abaqus/CAE noGUI.

The system is designed as a future LLM-agent toolchain, but the current implementation is intentionally deterministic and does not call external LLM APIs.

## Repository Structure

```text
bridge_fem_agent/
  main.py
  config.py

  schemas/
    bridge_schema.py

  semantic/
    bridge_model.py

  agents/
    document_agent.py
    reference_agent.py
    geometry_agent.py
    idealization_agent.py
    material_agent.py
    mesh_agent.py
    boundary_agent.py
    load_agent.py
    qa_agent.py
    model_production_workflow.py

  builders/
    abaqus_cae_builder.py

  inp/
    inp_builder.py
    inp_parser.py
    inp_editor.py

  runner/
    abaqus_runner.py
    job_monitor.py

  diagnosis/
    log_parser.py
    error_classifier.py

  repair/
    repair_rules.py
    repair_engine.py

  results/
    dat_extractor.py
    odb_extractor.py
    abaqus_odb_extract.py
    report_writer.py

  examples/
    simple_girder_bridge.json
    three_span_agent_bridge.json
    three_span_solid_bridge.json

  tests/
    test_workflow.py
```

Large Abaqus outputs and reference samples are intentionally ignored by Git:

```text
runs/
samples/
*.cae
*.odb
*.dat
*.msg
*.sta
```

This keeps the repository lightweight while allowing local Abaqus verification.

## Requirements

- Python 3.10+ recommended
- Abaqus 2022 or compatible Abaqus installation for real model generation and analysis
- No third-party Python package is required for the core workflow

The code also runs in dry-run mode on machines without Abaqus.

## V1: Analysis Workflow

The V1 workflow generates a simple beam-based `.inp` model and can run Abaqus/Standard.

Dry run:

```powershell
python main.py --input bridge_fem_agent\examples\simple_girder_bridge.json --workdir runs\simple_girder_bridge --max-repairs 3 --dry-run
```

Real Abaqus run:

```powershell
python main.py --input bridge_fem_agent\examples\simple_girder_bridge.json --workdir runs\simple_girder_bridge --max-repairs 3
```

Custom Abaqus command:

```powershell
python main.py --input bridge_fem_agent\examples\simple_girder_bridge.json --workdir runs\simple_girder_bridge --abaqus-command "abaqus" --max-repairs 3
```

V1 outputs:

```text
runs/simple_girder_bridge/
  simple_girder_bridge_attempt_0.inp
  simple_girder_bridge.log
  simple_girder_bridge.msg
  simple_girder_bridge.dat
  simple_girder_bridge.sta
  simple_girder_bridge.odb
  report.json
  report.md
  workflow.log
```

## V2: Multi-Agent Abaqus Model Production

V2 introduces a multi-agent production pipeline:

```text
Structured JSON / drawing-derived data
  -> Bridge Semantic Model
  -> Deterministic model-production agents
  -> Reviewable Abaqus/CAE Python script
  -> Optional .cae / .inp generation
  -> Optional Abaqus/Standard verification
```

The V2 agents are:

- **DocumentAgent**: reads structured JSON and creates the bridge semantic model.
- **ReferenceAgent**: scans local `samples/**/*.jnl` files and summarizes reference Abaqus modelling patterns.
- **GeometryAgent**: creates bridge stations, span breakpoints, and geometry planning data.
- **IdealizationAgent**: selects beam or solid finite element idealization.
- **MaterialAgent**: prepares material and section definitions.
- **MeshAgent**: selects mesh size, element type, and mandatory breakpoints.
- **BoundaryAgent**: maps engineering support types to Abaqus boundary conditions.
- **LoadAgent**: maps gravity, deck pressure, and point loads to Abaqus load definitions.
- **QaAgent**: checks the model plan before Abaqus generation.
- **AbaqusCaeScriptBuilder**: emits the Abaqus/CAE Python build script.

### Beam Model Production

Generate only reviewable model assets:

```powershell
python main.py --workflow model-production --input bridge_fem_agent\examples\three_span_agent_bridge.json --workdir runs\three_span_agent_bridge_v2 --samples-dir samples
```

Generate assets and build `.cae/.inp` with Abaqus/CAE:

```powershell
python main.py --workflow model-production --input bridge_fem_agent\examples\three_span_agent_bridge.json --workdir runs\three_span_agent_bridge_v2_cae --samples-dir samples --build-cae
```

The beam model uses:

- Abaqus/CAE `BaseWire`
- B31 beam elements
- Rectangular beam section
- Gravity
- Beam line load converted from deck pressure
- Static Abaqus/Standard step

### Solid Model Production

Generate a solid bridge model:

```powershell
python main.py --workflow model-production --input bridge_fem_agent\examples\three_span_solid_bridge.json --workdir runs\three_span_solid_bridge_v2_cae --samples-dir samples --build-cae
```

The solid model follows the style observed in the local sample journals:

- `BaseSolidExtrude`
- `HomogeneousSolidSection`
- C3D8R solid elements
- `seedPart`
- `generateMesh`
- support section partitioning
- bottom support node sets
- gravity load
- deck pressure or equivalent top-node vertical load fallback
- static Abaqus/Standard step

## Verified Local Results

The V2 beam model was generated and solved successfully with Abaqus/Standard.

The V2 solid model was also generated and solved successfully:

```text
THE ANALYSIS HAS COMPLETED SUCCESSFULLY
```

Solid model verification directory:

```text
runs/three_span_solid_bridge_v2_cae_retry2
```

Extracted solid ODB summary:

```text
max_displacement = 1.3075553125059352
max_stress = 1051906.5
```

## Testing

Run the standard-library test suite:

```powershell
python -m unittest discover bridge_fem_agent\tests
```

Current coverage includes:

- V1 dry-run analysis workflow
- deterministic `.inp` repair without overwriting prior attempts
- V2 beam model-production script generation
- V2 solid model-production script generation

## Design Principles

- Keep generated Abaqus artifacts under the selected `--workdir`.
- Never overwrite prior `.inp` attempts.
- Keep all repair actions auditable.
- Prefer deterministic rule-based repair before any future LLM reasoning.
- Use a semantic bridge model as the boundary between drawing/text understanding and Abaqus generation.
- Make Abaqus model production reviewable through generated Python scripts and QA reports.

## Future Work

- Add drawing/PDF/CAD extraction agents.
- Add shell and mixed beam-shell-solid model idealizations.
- Add connector-based bearing and support modelling.
- Add vehicle, temperature, wind, seismic, and load-combination agents.
- Improve ODB extraction for solid support reaction aggregation.
- Add result reasonableness checks such as total reaction versus total applied load.

