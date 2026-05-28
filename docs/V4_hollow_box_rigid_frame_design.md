# V4 Hollow-Box Continuous Rigid-Frame Workflow

## Goal

V4 extends the V3 continuous rigid-frame bridge workflow from a solid rectangular girder into a hollow box-girder representation inspired by the local `samples/rigid frame` reference model. The key modelling change is that the concrete girder now contains a true internal void: the generated Abaqus model is assembled from top slab, bottom slab, and web solid blocks instead of filling the entire cross-section.

The workflow is still deterministic and rule-based. It does not call any external LLM API. The design loop adjusts variable section dimensions and prestress tendon groups before writing a reviewable Abaqus/CAE noGUI script.

## Engineering Workflow

```text
Random three-span input or JSON task
  -> rigid-frame semantic task
  -> variable-depth hollow box section rules
  -> prestress tendon layout rules
  -> deterministic deflection/stress estimate
  -> section and tendon adjustment loop
  -> hollow-box C3D8R orphan-mesh Abaqus script
  -> optional Abaqus/CAE .cae/.inp generation
  -> optional Abaqus/Standard service analysis
```

## Main V4 Improvements

- Adds `rigid-frame-v4` as a command-line workflow.
- Adds `hollow-solid` as the default rigid-frame model level.
- Generates a hollow single-cell box girder using C3D8R solid elements.
- Creates the girder from top slab, two webs, and bottom slab regions, leaving the central void empty.
- Keeps girder and pier concrete in one host part so the pier-girder rigid-frame connection remains continuous.
- Generates T3D2 prestress tendon paths and embeds them in the concrete host using `model.EmbeddedRegion`.
- Uses a variable-depth section rule along the bridge length.
- Uses a rule-based optimizer to control estimated deflection, tensile stress, and compressive stress.
- Writes all design history and generated Abaqus script files into the selected work directory.

## Command

Generate V4 review assets without calling Abaqus:

```powershell
python main.py --workflow rigid-frame-v4 --spans 90 160 90 --pier-height 60 --workdir runs\rigid_frame_v4_hollow_review_90_160_90 --max-design-iterations 8
```

Generate `.cae` and `.inp` with Abaqus/CAE:

```powershell
python main.py --workflow rigid-frame-v4 --spans 90 160 90 --pier-height 60 --workdir runs\rigid_frame_v4_hollow_90_160_90 --max-design-iterations 8 --build-cae
```

## Output Files

```text
runs/rigid_frame_v4_hollow_review_90_160_90/
  rigid_frame_semantic.json
  optimization_history.json
  final_design.json
  optimization_report.md
  rigid_frame_90_160_90_rigid_frame_hollow_box_build.py
  rigid_frame_v4_report.json
  rigid_frame_v3_report.json
  workflow.log
```

When `--build-cae` succeeds, Abaqus/CAE also writes:

```text
  rigid_frame_90_160_90.cae
  rigid_frame_90_160_90.inp
```

## Hollow Box Section Parameters

The first V4 version derives hollow-box dimensions from the optimized V3 section:

- `deck_width_m`: global bridge deck width.
- `height_m`: variable girder depth at each control station.
- `bottom_box_width_m`: bottom box width, currently at least 48 percent of deck width.
- `top_slab_thickness_m`: optimized top slab thickness with a local depth cap.
- `bottom_slab_thickness_m`: optimized bottom slab thickness with a local depth cap.
- `web_thickness_m`: optimized web thickness with a box-width cap.

The generated cross-section is decomposed into:

- top slab blocks across the full deck width;
- left and right web blocks;
- bottom slab blocks around the box bottom;
- an internal central void between webs and slabs.

## Mesh and Connectivity Strategy

V4 uses an Abaqus orphan mesh to avoid relying on complex partition operations during early automation. The generated script creates:

- concrete nodes and C3D8R elements directly;
- girder element set `GIRDER_CONCRETE_ELEMENTS`;
- pier element set `PIER_CONCRETE_ELEMENTS`;
- host assembly set `CONCRETE_HOST`;
- top deck node set `DECK_TOP_NODES`;
- abutment and pier-base support node sets.

The variable-depth girder is generated with hexahedral elements whose left and right faces can have different vertical coordinates. This keeps neighboring variable-depth segments connected at shared station coordinates instead of producing disconnected stepped blocks.

## Prestress Modelling

Prestress tendons are represented by T3D2 truss elements for path review. The tendon instances are embedded into the concrete host so the tendon displacement follows the concrete deformation. This addresses the V3 issue where displayed tendon deformation could visually separate from concrete if the embed constraint was missing or not applied to the correct host.

The global prestress effect is still represented by an equivalent balancing load in this release. A future version should replace this simplified action with calibrated initial stress or initial strain, staged construction, and concrete-only/tendon-only result extraction.

## Optimization Logic

The optimizer evaluates each design with a deterministic engineering estimate:

- maximum service deflection;
- deflection ratio against the target, default `L/600`;
- maximum compressive stress;
- maximum tensile stress;
- reaction-balance reasonableness marker.

If the design does not pass, rule-based adjustments are applied:

- excessive deflection increases pier-top depth, midspan depth, bottom slab thickness, and bottom tendon count;
- excessive tensile stress increases top and bottom tendon capacity and girder depth;
- excessive compressive stress increases concrete area through depth, web thickness, and top slab thickness, with slight jacking reduction only when tension demand is low.

Every iteration is saved to `optimization_history.json` and summarized in `optimization_report.md`.

## Current Validation

Python-level validation passed:

```powershell
python -m unittest discover bridge_fem_agent\tests
```

Result:

```text
Ran 7 tests
OK
```

The V4 review directory was generated successfully:

```text
runs/rigid_frame_v4_hollow_review_90_160_90
```

The Abaqus/CAE build was also verified:

```text
runs/rigid_frame_v4_hollow_cae_retry3_90_160_90/
  rigid_frame_90_160_90.cae
  rigid_frame_90_160_90.inp
```

Abaqus/Standard service analysis completed successfully:

```powershell
abaqus job=rigid_frame_90_160_90_v4_check input=rigid_frame_90_160_90.inp interactive
```

The run directory contains:

```text
  rigid_frame_90_160_90_v4_check.dat
  rigid_frame_90_160_90_v4_check.msg
  rigid_frame_90_160_90_v4_check.odb
  rigid_frame_90_160_90_v4_check.sta
  rigid_frame_90_160_90_v4_results.json
```

The DAT file reports that the analysis completed, with one non-fatal warning. Basic ODB extraction reported:

```text
max_displacement = 0.2560715425483322
max_stress = 110774688.0
```

The current `max_stress` is a global field maximum and can include tendon elements. Concrete-only and tendon-only stress extraction should be separated in the next result-processing step.

## Visualization

### V4 Hollow-Box Model

![V4 hollow-box model](<v4 images/v4 model.png>)

### V4 Deformation Field

![V4 hollow-box deformation](<v4 images/v4 deform.png>)

### V4 Stress Field

![V4 hollow-box stress field](<v4 images/v4 stress.png>)

## Known Limits

- The hollow section is a structured single-cell box, not yet a full drawing-derived multi-cell box.
- Prestress is embedded for deformation compatibility, but prestress force is still applied as an equivalent balancing load.
- Construction stages, tendon anchorage blocks, ducts, friction loss, shrinkage, creep, and temperature are not yet modelled.
- ODB extraction should be extended to separate concrete stresses from tendon stresses.
- The generated C3D8R mesh is intentionally coarse and reviewable; final production models should add mesh-quality checks and local refinement.

## Future Agent Hooks

TODO: Add a drawing extraction agent that reads bridge cross-section drawings and maps slab/web dimensions to the hollow-box section controls.

TODO: Add a prestress calibration agent that converts tendon layout into Abaqus initial stress/strain and staged tensioning.

TODO: Add a verification agent that compares Abaqus ODB results against the deterministic estimate and feeds back section/tendon adjustments.
