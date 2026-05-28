# V3 Additional Continuous Rigid-Frame Span Validation

Date: 2026-05-28

This document records two additional V3 solid continuous rigid-frame bridge cases generated after the default `90 + 160 + 90 m` example.

Both cases use:

- monolithic solid girder-pier concrete host;
- C3D8R solid elements for concrete;
- T3D2 prestress tendon paths;
- Abaqus `*Embedded Element` constraints between tendons and concrete;
- equivalent service deck load;
- equivalent prestress balancing load;
- Abaqus/Standard static service check.

## Case 1: 80 + 140 + 80 m

Run folder:

```text
runs/rigid_frame_v3_solid_80_140_80_embedded/
```

Generation command:

```powershell
python main.py --workflow rigid-frame-v3 --spans 80 140 80 --workdir runs\rigid_frame_v3_solid_80_140_80_embedded --model-level solid --build-cae
```

Analysis command:

```powershell
abaqus job=rigid_frame_80_140_80_embedded_check input=rigid_frame_80_140_80.inp interactive
```

Verification:

```text
Abaqus JOB rigid_frame_80_140_80_embedded_check COMPLETED
0 ERROR MESSAGES
0 analysis numerical warnings
```

ODB summary:

```json
{
  "max_displacement": 0.21889511659799382,
  "max_stress": 76523576.0,
  "support_reactions": {},
  "modal_frequencies": []
}
```

Deflection check:

```text
Main span = 140 m
L/600 limit = 0.233333 m
Computed max displacement = 0.218895 m
Status = pass
```

## Case 2: 110 + 180 + 110 m

Run folder:

```text
runs/rigid_frame_v3_solid_110_180_110_embedded/
```

Generation command:

```powershell
python main.py --workflow rigid-frame-v3 --spans 110 180 110 --workdir runs\rigid_frame_v3_solid_110_180_110_embedded --model-level solid --build-cae
```

Analysis command:

```powershell
abaqus job=rigid_frame_110_180_110_embedded_check input=rigid_frame_110_180_110.inp interactive
```

Verification:

```text
Abaqus JOB rigid_frame_110_180_110_embedded_check COMPLETED
0 ERROR MESSAGES
0 analysis numerical warnings
```

ODB summary:

```json
{
  "max_displacement": 0.23129270214870667,
  "max_stress": 79867952.0,
  "support_reactions": {},
  "modal_frequencies": []
}
```

Deflection check:

```text
Main span = 180 m
L/600 limit = 0.300000 m
Computed max displacement = 0.231293 m
Status = pass
```

## Model Validity Notes

Both generated `.inp` files contain:

```text
*Element, type=C3D8R
*Element, type=T3D2
*Embedded Element
```

This confirms that the generated models are solid concrete host models with embedded tendon truss paths.

The extracted `max_stress` values include stresses from both concrete solid elements and embedded tendon truss elements. Therefore, these stress values should not be interpreted as concrete-only maximum stress. A future result extractor should report:

- concrete max principal/von Mises stress by concrete element set;
- tendon axial stress by tendon element set;
- global max displacement;
- support reaction totals by support set.

## Conclusion

The V3 framework successfully generated and solved two additional continuous rigid-frame solid bridge cases with different span combinations. Both cases completed Abaqus/Standard analysis without errors or numerical warnings, and both satisfy the L/600 deflection target.

