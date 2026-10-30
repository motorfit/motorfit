# RS05 fixture

This page records the measured assembly used in the [RS05 reference study](rs05.md). For a new fixture, supply its own measured geometry and masses as described in [bring your own motor](../guide/configuration.md).

## Weight and fastener masses

The 100 g weight uses a 20.5 g shoulder bolt. The 200/500 g weights use a 25.1 g shoulder bolt. Each M8 nut weighs 4.3 g. The 1000 g configuration is a documented fixture option; the formal dataset contains only 100/200/500 g experiments.

| Weight g | Bolt g | Nut g | Total tip mass g | Fixture pivot inertia kg·m² | Horizontal gravity torque N·m |
|---:|---:|---:|---:|---:|---:|
| 100 | 20.5 | 4.3 | 124.8 | 0.0064014785763 | 0.341946337927 |
| 200 | 25.1 | 4.3 | 229.4 | 0.0105854785763 | 0.547101455927 |
| 500 | 25.1 | 4.3 | 529.4 | 0.0225854785763 | 1.135500455927 |
| 1000 | 25.1 | 4.3 | 1029.4 | 0.0425854785763 | 2.116165455927 |

Tip mass includes the weight, shoulder bolt and nut. The arm mass is 110 g, its center of mass is 0.0900802043205295 m from the pivot, and its pivot inertia is 0.0014073185763008957 kg·m². Hub inertia is 0.00000216 kg·m². The table includes arm and hub inertia, and excludes the motor inertia identified by BAM.

## Identification fixture

The identification model places the tip assembly at a 0.2 m radius:

```text
J_fixture = m_tip × length² + J_arm + J_hub
G_horizontal = 9.80665 × (m_tip × length + m_arm × arm_com)
```

The four `configs/fixtures/pendulum_<weight>g_200mm.toml` files store `weight_mass`, `bolt_mass`, `nut_mass` and their total `mass`, in kilograms. `load_fixture()` checks that the component sum matches the total.

## CAD replay

The `finite` replay fixture includes each component's own inertia. The `identified_point` control preserves the inertia used for identification while displaying the CAD assembly. The separate experiment archive stores the source geometry and mass-property manifest under `data/rs05/assets/bench/`.

Earlier pilot metadata corrections remain in the research archive. The delivered formal v3 payloads, hashes and frozen model preserve their original values.
