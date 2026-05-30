# V6 Real Prestress Thermal-Strain Design

## Objective

V6 replaces the default equivalent upward prestress load with bonded tendon
prestress transferred through embedded `T3D2` elements. Concrete remains
`C3D8R`. Tendons remain reviewable geometric paths and are constrained with
`EmbeddedRegion`.

The implemented approximation is suitable for deterministic model production
and early service-stage checks. It does not yet represent duct friction,
anchorage slip, sequential tensioning, creep, shrinkage, or time-dependent
prestress loss.

## Prestress Modes

The rigid-frame schema adds:

```text
prestress_mode = "thermal_strain"
prestress_effective_ratio = 0.65
```

Supported modes:

- `thermal_strain`: default V6 behaviour. Apply tendon temperature reduction.
- `equivalent_load`: legacy compatibility mode. Apply the old upward load.
- `none`: preserve tendon geometry without applying prestress action.

The default `0.65` ratio keeps the requested tendon stress close to the lower
bound of the normal service range. This was selected after the first V6
thermal-strain verification showed excessive initial deformation when using
`0.90`.

## Thermal-Strain Calculation

For every tendon group:

```text
Ap = area_each_m2 * count
Pe = total_force_n * prestress_effective_ratio
sigma_pe = Pe / Ap
delta_T = -sigma_pe / (Ep * alpha_p)
alpha_p = 1.2e-5 / C
```

The prestress steel material receives:

```python
model.materials["PRESTRESS_STEEL"].Expansion(table=((1.2e-5,),))
```

The temperature field is applied in the dedicated `Prestress` step. Gravity
and deck service loads are applied in the following `ServiceLoad` step.

## Abaqus Region Detail

The first implementation used:

```python
regionToolset.Region(elements=tendon_instance.elements[:])
```

CAE wrote temporary node sets for `*TEMPERATURE`, but Abaqus/Standard rejected
them as inactive model sets. V6 therefore creates explicit tendon node sets:

```python
assembly.Set(
    nodes=tendon_instance.nodes[:],
    name=abaqus_name(tendon["name"] + "_PRESTRESS_NODES"),
)
```

Temperature is applied to those named node sets. Tendon element sets are still
kept for review, and `EmbeddedRegion` still uses the `T3D2` elements.

## Verification Run

The verified local V6 model uses spans:

```text
90 + 160 + 90 m
```

Current optimized run directory:

```text
runs/rigid_frame_v6_prestress_balanced8_cae_90_160_90
```

The generated `.inp` contains:

- `*Expansion` for `PRESTRESS_STEEL`;
- `*Step, name=Prestress`;
- four named `*_PRESTRESS_NODES` sets;
- four `*Temperature` fields;
- `*Step, name=ServiceLoad`;
- no default `Load-prestress-equivalent`.

The Abaqus/Standard job completed successfully. The theoretical effective
tendon stress was `906.750 MPa`. ODB extraction reported:

```text
Prestress tendon S11           = 766.4 to 955.0 MPa
Prestress vertical U2 range    = -0.0434 to +0.0404 m
Prestress concrete S11 p95/p99 = 0.395 / 0.863 MPa
Service max |U|                = 0.1998 m
Service concrete S11 p95/p99   = 1.130 / 2.801 MPa
```

The optimized layout no longer uses one full-length bottom tendon group.
Instead, positive-moment tendons are split into left side-span, main-span, and
right side-span groups. Paired continuity tendons are added near the top and
bottom slabs to increase axial compression without adding large prestress
bending. This reduces broad concrete tensile stress while keeping tendon stress
within the intended service range.

Local maximum concrete tensile stresses remain higher than the percentile
values because the current global model has simplified embedded tendon
transfer, supports, and no local anchorage zone. These peaks should be treated
as local-model triggers rather than as full-section decompression failure.

## Auditable Outputs

Each rigid-frame run now writes:

```text
prestress_verification.json
```

The file records tendon-by-tendon `Pe`, `Ap`, `sigma_pe`, `delta_T`, the
effective ratio, and a `900-1400 MPa` reasonableness check.

The ODB extractor now also writes final-frame summaries for every analysis
step, including vertical displacement range, tendon `S11`, concrete `S11`, and
concrete principal stress ranges.

## Next Engineering Steps

- Add friction and wobble loss along tendon paths.
- Add anchorage-slip loss and construction-stage tensioning order.
- Separate concrete stress envelopes from tendon stress envelopes.
- Add tendon-group-specific effective ratios derived from design metadata.
- Add automated checks for concrete `-P/A +/- Pe/W` stress trends.
