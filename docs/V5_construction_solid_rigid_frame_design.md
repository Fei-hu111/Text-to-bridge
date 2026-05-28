# V5 Construction-Solid Continuous Rigid-Frame Workflow

## Motivation

V4 introduced a hollow box girder, but it was still too simplified for a continuous rigid-frame concrete bridge. The reference model under `samples/rigid frame` points to a more construction-oriented solid model: the bridge should use continuum solid elements, have real solid regions near supports, and thicken the box-girder bottom slab near pier regions.

V5 therefore upgrades the rigid-frame model from a generic hollow box into a construction-detail solid model:

- standard span regions remain hollow box-girder sections;
- both girder ends are generated as solid end blocks;
- pier-top/support regions are generated as solid diaphragm blocks;
- bottom slab thickness varies along the bridge;
- bottom slab is thin far from piers and thick near pier/support zones;
- prestress tendon paths remain embedded into the concrete host.

## Workflow

```text
Three-span input / JSON task
  -> semantic rigid-frame task
  -> V3 section and prestress optimization
  -> V5 construction zoning
  -> variable bottom slab thickness rule
  -> C3D8R construction-solid Abaqus script
  -> optional Abaqus/CAE .cae/.inp generation
  -> optional Abaqus/Standard service analysis
```

## Command

Generate and build the V5 model:

```powershell
python main.py --workflow rigid-frame-v5 --spans 90 160 90 --pier-height 60 --workdir runs\rigid_frame_v5_refined_mesh_cae_90_160_90 --max-design-iterations 8 --build-cae
```

The workflow writes:

```text
runs/rigid_frame_v5_refined_mesh_cae_90_160_90/
  rigid_frame_semantic.json
  optimization_history.json
  final_design.json
  optimization_report.md
  rigid_frame_90_160_90_rigid_frame_construction_solid_build.py
  rigid_frame_90_160_90.cae
  rigid_frame_90_160_90.inp
  rigid_frame_v5_report.json
  workflow.log
```

## Solid Element Modelling

V5 uses Abaqus continuum solid elements:

```text
*Element, type=C3D8R
```

The V5 mesh is refined inside each construction block. The script subdivides each box-girder slab, web, diaphragm fill, and pier block in three directions:

- longitudinal direction, controlled by `mesh_controls.longitudinal_size_m`;
- vertical direction, controlled by `mesh_controls.vertical_size_m`;
- transverse direction, controlled by `mesh_controls.transverse_size_m`.

This avoids the earlier beam-like appearance where each slab/web region had only one large element through most of its width or height.

The generated input file also exposes reviewable element sets:

```text
GIRDER_CONCRETE_ELEMENTS
SOLID_DIAPHRAGM_ELEMENTS
PIER_CONCRETE_ELEMENTS
CONCRETE_HOST
```

`SOLID_DIAPHRAGM_ELEMENTS` marks the real solid parts of the girder, including end blocks and pier-top support/diaphragm zones. This makes it possible to review whether the model has actually generated solid construction regions rather than just visual placeholders.

## Construction Zoning

V5 classifies each longitudinal station into one of these zones:

- `left_end_solid`: solid block at the left girder end;
- `right_end_solid`: solid block at the right girder end;
- `pier01_solid`: solid diaphragm/support zone around pier 1;
- `pier02_solid`: solid diaphragm/support zone around pier 2;
- `hollow`: normal hollow box-girder span region.

Default zoning rules:

- end solid length: `max(3.5 m, 0.045 * side_span)`;
- pier solid half length: `max(0.65 * pier_width, 0.020 * main_span)`;
- bottom slab transition length: `max(10.0 m, 0.16 * main_span)`.

The zoning boundaries are inserted into the station list so that mesh blocks and section changes are explicit in the generated Abaqus script.

The solid zone is intentionally kept short. Its purpose is to fill the local box cell, not to create an external protruding block. Adjacent transition stations are inserted at one-third and two-thirds of the transition length so that section depth and bottom slab thickness change gradually.

## Variable Bottom Slab Thickness

The bottom slab thickness is no longer constant. It is calculated at each station using a deterministic distance-based rule:

- base thickness comes from the optimized V3 section;
- thickness increases smoothly near each pier solid zone;
- thickness also increases near end solid zones;
- the final value is capped by a percentage of the local girder depth.

This captures the intended engineering trend:

```text
far from pier/support -> thinner bottom slab
near pier/support     -> thicker bottom slab
inside solid zone     -> full solid diaphragm/block
```

The latest V5 correction removed the previous step-change rule that forced the entire support solid zone to have a sudden minimum bottom slab thickness. The new rule uses a smoothstep transition function, so the solid-zone fill and the hollow-box section share the same outer control lines at their interface.

## Hollow and Solid Section Generation

For `hollow` regions, V5 generates only:

- top slab C3D8R blocks;
- left and right web C3D8R blocks;
- bottom slab C3D8R blocks.

The internal box cell remains empty.

For solid construction regions, V5 does not convert the section into an external rectangle. It first generates the same hollow box section as a normal span, then only fills the internal box-cell void between the webs, top slab, and bottom slab. Wing-slab overhang regions outside the webs remain shaped like the original box girder.

This keeps the real cross-section outline while still adding concrete where the diaphragm/end-block should close the hollow box cell.

## Prestress Compatibility

Prestress tendons remain T3D2 truss elements embedded in the concrete host:

```text
model.EmbeddedRegion(...)
```

Top tendon paths are placed inside the top slab. Bottom tendon paths are placed inside the local bottom slab, so they remain within concrete even when bottom slab thickness varies.

The prestress action is still represented by an equivalent balancing load in this release. A future version should replace it with staged prestress initial stress/strain and tendon loss modelling.

## Verification

Python test suite:

```powershell
python -m unittest discover bridge_fem_agent\tests
```

Result:

```text
Ran 8 tests
OK
```

Abaqus/CAE build:

```text
runs/rigid_frame_v5_refined_mesh_cae_90_160_90/
  rigid_frame_90_160_90.cae
  rigid_frame_90_160_90.inp
```

Abaqus/Standard service analysis:

```powershell
abaqus job=rigid_frame_90_160_90_v5_refined_mesh_check input=rigid_frame_90_160_90.inp interactive
```

The refined-mesh void-fill model completed successfully. Abaqus reported:

```text
NUMBER OF ELEMENTS IS 14834
NUMBER OF NODES IS 27592
```

Basic ODB extraction reported:

```text
max_displacement = 0.2537494025965285
max_stress = 76677904.0
```

The stress value is still the global maximum and may include tendon elements. Concrete-only and tendon-only stress envelopes should be separated in the next extraction upgrade.

## Visualization

### Refined Solid Model

![V5 refined mesh model](<v5 iamges/v5 model.png>)

### Displacement Field

![V5 displacement field](<v5 iamges/v5 deform.png>)

### Stress Field

![V5 stress field](<v5 iamges/v5 stress.png>)

## Current Limitations

- The model is still generated as a structured C3D8R orphan mesh, not a fully partitioned native CAD solid.
- Solid regions are rule-based approximations rather than drawing-extracted diaphragm geometry.
- Bearing blocks, anchor blocks, ducts, staged casting, creep, shrinkage, and prestress losses are not yet modelled.
- Result extraction still needs element-set filtering for concrete and tendon stress envelopes.

## Next Improvements

TODO: Add drawing-derived diaphragm and solid-zone dimensions.

TODO: Add concrete-only and tendon-only ODB result extraction.

TODO: Add staged prestress and construction sequence modelling.
