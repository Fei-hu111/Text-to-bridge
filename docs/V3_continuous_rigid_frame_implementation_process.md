# V3 Continuous Rigid-Frame Bridge Implementation Process

Date: 2026-05-28  
Project: Text to Bridge  
Platform: Python + Abaqus/CAE + Abaqus/Standard

## 1. Objective

V3 was developed to move the bridge generation workflow from simple girder/solid-deck examples toward a continuous rigid-frame bridge similar to the local reference model under `samples/rigid frame`.

The target was:

- generate a three-span continuous rigid-frame bridge from random span inputs;
- include main girder, piers, supports, service loads, and prestress tendon layout;
- use a solid Abaqus model rather than only beam elements;
- make the model reviewable in Abaqus/CAE;
- keep all design iterations, parameters, generated scripts, `.cae`, `.inp`, logs, and ODB checks under the selected run folder;
- keep the workflow deterministic and ready for future multi-agent/LLM tool integration.

## 2. Reference Model Understanding

The reference folder was:

```text
samples/rigid frame/
  MuShanBridge-nonlinear-basic.cae
  MuShanBridge-nonlinear-basic.jnl
```

The CAE inspection showed that the reference model contains:

- continuous rigid-frame bridge components;
- main girder, side spans, middle span, piers, abutments, and support-related regions;
- C50/C40-style material separation;
- prestress-related steel material;
- gravity, secondary dead load, road load, and pedestrian/human load concepts;
- staged loading concepts;
- many named sets and surfaces used for review and boundary/load assignment.

V3 did not directly copy the CAE file. Instead, it used these modeling ideas to build a deterministic generator.

## 3. V3 Architecture

The V3 implementation is located under:

```text
bridge_fem_agent/rigid_frame/
  schema.py
  design.py
  builder.py
  solid_builder.py
  workflow.py
```

The command-line entry is:

```text
bridge_fem_agent/main.py
```

The example input is:

```text
bridge_fem_agent/examples/rigid_frame_v3_example.json
```

### 3.1 Agent-Like Modules

Although V3 is implemented as normal Python modules, the workflow is divided into agent-like responsibilities:

- Semantic input agent: parses JSON or `--spans L1 L2 L3`.
- Section design agent: creates variable-depth girder parameters.
- Prestress layout agent: creates top and bottom tendon groups.
- Response evaluator agent: estimates deflection and stress.
- Optimization agent: adjusts section and tendon parameters.
- Solid build agent: writes Abaqus/CAE script for solid model generation.
- Report agent: writes JSON and Markdown reports.

This keeps the current version deterministic while leaving a clean boundary for future LLM agent tools.

## 4. Input Parameters

The default V3 example is:

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

Default material and target settings:

```text
Girder concrete: C50-like
Pier concrete: C40-like
Concrete density: 2500 kg/m3
Girder elastic modulus: 3.45e10 Pa
Pier elastic modulus: 3.25e10 Pa
Poisson ratio: 0.2
Prestress steel elastic modulus: 1.95e11 Pa
Prestress jacking stress: 1.395e9 Pa
Deflection limit: L/600
Concrete stress target: 1.8e7 Pa
Maximum design iterations: 8
```

## 5. Design Rules

The initial section design uses span-based rules:

```text
Pier-top girder depth ~= main_span / 17
Midspan girder depth ~= main_span / 50
Variable girder depth = parabolic transition between pier-top and midspan regions
```

For the default 160 m main span, the first design starts near:

```text
Pier-top depth ~= 9.41 m
Midspan depth ~= 3.20 m
```

The optimizer then adjusts:

- pier-top girder depth;
- midspan girder depth;
- web thickness;
- top slab thickness;
- bottom slab thickness;
- tendon group count;
- jacking stress factor when compression control requires it.

## 6. Prestress Tendon Layout

The V3 tendon groups are:

```text
Tendon-Pier01-Top       Negative moment tendon near pier 1
Tendon-Pier02-Top       Negative moment tendon near pier 2
Tendon-Midspan-Bottom   Positive moment tendon in the main span
Tendon-SideSpan-Bottom  Positive moment tendon over side spans
```

In the final embedded solid version:

- tendons are represented by T3D2 truss elements;
- tendon paths are placed inside the solid girder at the bridge width centerline;
- tendon elements are embedded into the concrete host solid;
- global prestress action is still represented by an equivalent balancing load.

This means the tendon geometry now follows concrete deformation in the Abaqus deformed-shape view.

## 7. Modeling Evolution

### 7.1 First V3 Beam Model

The first implementation used B31 beam elements:

- variable-depth girder represented by segment-by-segment beam sections;
- piers represented by beam elements;
- tendons represented as reviewable truss paths;
- prestress represented as equivalent upward load.

This version was useful for fast scheme optimization, but it was not sufficient for the user's goal because it was not a solid model.

### 7.2 Solid Rigid-Frame Model

The next version created a solid model:

- one monolithic Abaqus solid part named `RigidFrameSolid`;
- main girder and two piers generated in the same extruded solid body;
- C3D8R solid elements used for the concrete host;
- bridge outline generated in the X-Y plane and extruded across deck width;
- pier regions assigned C40-like material;
- girder region assigned C50-like material.

The monolithic solid approach was selected because it avoids unstable or incomplete tie constraints between separately generated girder and pier parts.

### 7.3 Embedded Tendon Correction

After reviewing the deformed shape, the user found that tendon deformation did not match concrete deformation.

The cause was correct:

- tendons were only visual/review paths;
- tendon path nodes were fixed;
- no real host-embedded constraint existed between tendon and concrete;
- therefore tendons did not follow concrete deflection.

The correction was:

```text
1. Move tendon instances to deck-width centerline.
2. Remove tendon path displacement BCs.
3. Add Abaqus EmbeddedRegion constraints.
4. Confirm generated .inp contains *Embedded Element.
5. Re-run Abaqus/Standard.
```

The final `.inp` contains:

```text
*Embedded Element
```

This indicates that the tendon truss elements are embedded in the concrete solid host.

## 8. Abaqus Build and Run Commands

Generate the final embedded solid model:

```powershell
python main.py --workflow rigid-frame-v3 ^
  --input bridge_fem_agent\examples\rigid_frame_v3_example.json ^
  --workdir runs\rigid_frame_v3_solid_embedded_cae ^
  --model-level solid ^
  --build-cae
```

Run Abaqus/Standard check:

```powershell
abaqus job=rigid_frame_90_160_90_embedded_check input=rigid_frame_90_160_90.inp interactive
```

Extract ODB results:

```powershell
abaqus python ..\..\bridge_fem_agent\results\abaqus_odb_extract.py ^
  rigid_frame_90_160_90_embedded_check.odb ^
  rigid_frame_90_160_90_embedded_check_results.json
```

## 9. Final Output Folder

Final embedded solid model output:

```text
runs/rigid_frame_v3_solid_embedded_cae/
  rigid_frame_90_160_90.cae
  rigid_frame_90_160_90.inp
  rigid_frame_90_160_90_rigid_frame_solid_build.py
  rigid_frame_90_160_90_embedded_check.odb
  rigid_frame_90_160_90_embedded_check.dat
  rigid_frame_90_160_90_embedded_check.msg
  rigid_frame_90_160_90_embedded_check_results.json
  final_design.json
  optimization_history.json
  optimization_report.md
  rigid_frame_v3_report.json
  workflow.log
```

## 10. Error and Adjustment Log

### Error 1: Beam Model Was Not Enough

Problem:

```text
V3 initially generated mostly beam elements.
```

Reason:

```text
The first V3 goal was fast global rigid-frame optimization.
```

Adjustment:

```text
Added solid_builder.py.
Set --model-level solid as the default V3 idealization.
Generated C3D8R solid concrete host.
```

### Error 2: Pier/Girder Section Assignment Issue in Beam Model

Problem:

```text
Abaqus reported missing beam section definitions for pier/girder elements.
```

Reason:

```text
The script used X-Z node/edge lookup, while Abaqus sketch coordinates became X-Y in the 3D wire part.
```

Adjustment:

```text
Changed lookup logic to X-Y coordinates.
Changed gravity and line load direction from comp3 to comp2.
```

### Error 3: CAE File Locked

Problem:

```text
Abaqus could not overwrite rigid_frame_90_160_90.cae.
```

Reason:

```text
The CAE file was open or locked by another Abaqus process.
```

Adjustment:

```text
Used a new run folder instead of overwriting the locked CAE.
```

### Error 4: Windows Subprocess Decode Failure

Problem:

```text
UnicodeDecodeError while reading Abaqus subprocess stderr.
```

Reason:

```text
Abaqus returned non-UTF/GBK-mixed output on Windows.
```

Adjustment:

```text
Changed subprocess capture to encoding="utf-8", errors="replace".
Allowed empty stdout/stderr fallback.
```

### Error 5: Tendon Did Not Follow Concrete Deformation

Problem:

```text
Tendon path and concrete deflection did not match in the deformed view.
```

Reason:

```text
The tendons were not constrained to the concrete host.
They were review geometry and their nodes were fixed.
```

Adjustment:

```text
Removed tendon path displacement BC.
Moved tendon instances into the solid section at z = deck_width / 2.
Added model.EmbeddedRegion.
Verified *Embedded Element in the .inp file.
```

## 11. Final Verification Results

The final embedded solid model was solved successfully:

```text
Abaqus JOB rigid_frame_90_160_90_embedded_check COMPLETED
0 ERROR MESSAGES
0 numerical warnings
```

Extracted ODB summary:

```json
{
  "max_displacement": 0.2132945424954412,
  "max_stress": 74328184.0,
  "support_reactions": {},
  "modal_frequencies": []
}
```

Important note:

```text
After embedding tendon elements, max_stress includes steel tendon stress and concrete stress together.
Therefore this value should not be interpreted as concrete-only maximum stress.
Future result extraction should separate concrete element sets and tendon element sets.
```

The earlier concrete-dominant solid check before embedded tendon stress mixing was:

```text
max_displacement ~= 0.2131 m
max_concrete-dominant stress ~= 17.88 MPa
```

For a 160 m main span:

```text
L/600 limit = 160 / 600 = 0.2667 m
final displacement = 0.2133 m
```

The deflection is within the target range.

## 12. Testing

The standard Python test suite was run:

```powershell
python -m unittest discover bridge_fem_agent\tests
```

Result:

```text
Ran 6 tests
OK
```

The tests cover:

- V1 dry-run analysis workflow;
- deterministic `.inp` repair workflow;
- V2 beam model production;
- V2 solid model production;
- V3 beam rigid-frame generation;
- V3 solid rigid-frame generation with embedded tendon constraint text.

## 13. Current Limitations

The current V3 model is a practical first solid rigid-frame generator, but it is not yet a full construction-stage prestressed concrete bridge analysis.

Current simplifications:

- prestress effect is represented by equivalent balancing load;
- tendon initial stress is not yet applied as a true prestress field;
- no construction-stage cantilever casting sequence;
- no time-dependent creep/shrinkage/relaxation;
- no real bearing/contact components;
- no drawing recognition yet;
- result extraction does not yet separate concrete and tendon stress envelopes.

## 14. Recommended V4 Work

Recommended next steps:

- add true prestress initial stress or equivalent temperature/initial strain in tendon elements;
- add element-set-based ODB extraction for concrete stress, tendon stress, displacement, and support reactions separately;
- add staged construction steps;
- add bearing/contact/connector components;
- add section hollowing for real box-girder geometry instead of a simplified solid outline;
- add local mesh refinement around pier-girder junctions;
- calibrate design rules using the reference CAE model response;
- connect drawing/text extraction agents to feed span, pier height, section control points, and tendon coordinates automatically.

## 15. Conclusion

V3 now supports a solid continuous rigid-frame bridge model based on three-span input. The final implementation generates a monolithic C3D8R concrete host, C40/C50 material regions, embedded T3D2 prestress tendon paths, support conditions, service loads, equivalent prestress balancing action, Abaqus/CAE scripts, Abaqus input files, and ODB verification results.

The most important correction was replacing fixed visual tendon paths with embedded tendon constraints. This solved the deformation mismatch observed in the Abaqus deformed-shape plot and made the tendon path follow the concrete host deformation.

