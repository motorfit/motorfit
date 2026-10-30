# RS05 fixture measurements

The [RS05 study](rs05.md) uses a pendulum arm with interchangeable tip weights.
The modeled tip mass includes every fastener that moves with the weight. These
measurements describe that assembly; use your own values for another bench.

## Masses and dimensions

| Component | Measured value |
|---|---:|
| Pivot-to-tip radius | 0.2 m |
| Arm mass | 0.110 kg |
| Arm center of mass from pivot | 0.0900802 m |
| Arm inertia about pivot | 0.00140732 kg·m² |
| Hub inertia about pivot | 0.00000216 kg·m² |
| M8 nut mass | 4.3 g |

The 100 g weight uses a 20.5 g shoulder bolt. The 200 g and 500 g weights use a
25.1 g bolt. The 1,000 g fixture is documented, but was not part of the formal
111-record experiment.

| Weight label | Bolt + nut | Total tip mass |
|---|---:|---:|
| 100 g | 24.8 g | 124.8 g |
| 200 g | 29.4 g | 229.4 g |
| 500 g | 29.4 g | 529.4 g |
| 1,000 g | 29.4 g | 1,029.4 g |

The corresponding files are
`configs/fixtures/pendulum_<weight>g_200mm.toml`. They store masses in kilograms,
including `weight_mass`, `bolt_mass`, `nut_mass` and the total `mass`.
The loader checks that the components sum to the total.

## Fixture used for identification

The fitting model places the complete tip assembly at a single point at radius
`L = 0.2 m`. It uses

$$
J_f=mL^2+J_a+J_h,\qquad
G_\mathrm{horizontal}=9.80665\,(mL+m_a c_a).
$$

| Weight label | Fixture pivot inertia (kg·m²) | Horizontal gravity torque (N·m) |
|---|---:|---:|
| 100 g | 0.00640148 | 0.341946 |
| 200 g | 0.01058548 | 0.547101 |
| 500 g | 0.02258548 | 1.135500 |
| 1,000 g | 0.04258548 | 2.116165 |

Fixture inertia includes the arm and hub but excludes the fitted motor `armature`.
The full-precision source values remain in the TOML files.

## Fixture used for CAD replay

The `finite` CAD fixture includes the individual components' own inertias. The
`identified_point` option preserves the inertia assumed during fitting while
showing the CAD geometry. Comparing these two choices isolates the consequence
of the point-load approximation.

The full research archive stores geometry and the mass-property manifest in
`data/rs05/assets/bench/`. Those files are not included in the small offline example.
Historical corrections to pilot metadata are retained in the archive; the formal
v3 payloads and their hashes remain unchanged.
