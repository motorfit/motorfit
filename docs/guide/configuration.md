# Set up the bench

Before recording, describe the mounted motor, the pendulum and the connection.
MotorFit reads these settings from TOML files. The same setup file is used by
`read`, `inspect`, `zero` and `record`.

You need a supported motor, a rigidly mounted pendulum, measured fixture properties,
and a Linux machine with a SocketCAN interface. Use the
[Quickstart installation steps](../getting-started/quickstart.md#1-install-motorfit)
to prepare the software.

## 1. Create a local configuration

The example below starts from RS05 templates:

```bash
mkdir -p configs/local
cp configs/setups/rs05_pendulum.toml configs/local/bench.toml
cp configs/fixtures/pendulum_100g_200mm.toml configs/local/bench-fixture.toml
cp configs/acquisition/bam_6s.toml configs/local/bench-motion.toml
```

For Damiao, copy `configs/setups/dm4310_pendulum.toml` as the setup and
`configs/acquisition/damiao_example.toml` as the motion file instead.

Edit the first four entries in `configs/local/bench.toml`:

```toml
motor = "../motors/robstride/rs05.toml"
fixture = "bench-fixture.toml"
acquisition = "bench-motion.toml"
coordinate_file = "bench-zero.toml"
```

For DM4310, the motor path is `../motors/damiao/4310.toml`.
Select other profiles from [Motors](../reference/motors.md).
All four paths resolve **relative to the setup file**. Files in `configs/local/`
are ignored by Git, so device-specific settings and zero offsets stay local.

The copied numbers describe example equipment. Replace them with your measured
fixture and chosen settings before using `record`.

## 2. Set the connection and supply

Edit these sections of the setup:

| Field | Meaning |
|---|---|
| `device.channel` | SocketCAN interface name, such as `can0` |
| `device.motor_id` | Address configured in the motor |
| `device.host_id` | RobStride host address; the RS05 template uses 255 |
| `device.feedback_id` | Damiao reply CAN ID; the DM4310 template uses 17 |
| `device.timeout_s` | Maximum wait for a matching reply, in seconds |
| `device.watchdog_ms` | Drive communication watchdog requested before recording |
| `supply.voltage` | Supply setting in volts, saved as recording metadata |

The RS05 template uses motor address 127; DM4310 uses motor address 1. These are
example addresses, not values detected from your device. Supply voltage is
configured metadata, not a continuously measured channel.

Keep the coordinate convention `downward-positive-encoder`. Physical angle zero
means the pendulum points down; positive angle follows the encoder's positive
direction. The [next guide](acquisition.md#3-save-the-downward-zero) creates the
zero file from an actual measurement.

## 3. Measure the fixture

Edit `configs/local/bench-fixture.toml`. Use SI units throughout:

| Field | Unit | Measurement |
|---|---|---|
| `mass` | kg | Total tip assembly: weight, bolt, nut and other tip attachments |
| `length` | m | Distance from the pivot to the tip assembly's modeled point mass |
| `arm_mass` | kg | Moving arm mass, excluding the tip assembly |
| `arm_com` | m | Arm center of mass measured from the pivot |
| `arm_inertia` | kg·m² | Arm inertia **about the pivot** |
| `hub_inertia` | kg·m² | Additional rotating hub inertia about the pivot |

The model uses

$$
J_\mathrm{fixture}=mL^2+J_\mathrm{arm}+J_\mathrm{hub},\qquad
\tau_g=-9.80665\,(mL+m_a c_a)\sin(q+q_0).
$$

The tip assembly is treated as a point mass. Its own inertia is not included in
`mass × length²`. The [RS05 fixture](../case-studies/rs05-fixture.md) shows a measured
example and explains the separate CAD replay model.

If the file includes `weight_mass`, `bolt_mass` and `nut_mass`, their sum must equal
`mass`. Update all four fields when changing weights, or remove the three-component
breakdown and provide the measured total. If `arm_com` and `arm_inertia` are omitted,
the code assumes a uniform rod (`L/2` and `arm_mass × L²/3`). Supply measured values
when that approximation is unsuitable.

## 4. Choose the motion settings

Edit `configs/local/bench-motion.toml`:

| Field | Meaning |
|---|---|
| `trajectory` | A name from [Trajectories](../reference/trajectories.md) |
| `duration_s` | Total run duration, in seconds |
| `amplitude` | Multiplier on the trajectory's target angle |
| `hz` | Requested host command rate |
| `kp`, `kd` | Fixed position and velocity gains for this run |
| `telemetry_hz` | Keep at `0`; device inspection is performed separately |
| `sweep_k` | Frequency-growth coefficient, used only by `soccer_sweep` |

Choose gains and motion limits for the actual load and available travel. In
particular, `amplitude = 1` does not mean one radian for every trajectory: a
`lift_and_drop` target reaches `−π/2` at that scale.

A model profile specifies how commands are encoded. Its maximum torque is not a
recommended continuous operating torque or a measured limit for your assembly.

## 5. Check the composed setup without a motor

```bash
uv run --no-sync python - <<'PY'
from pprint import pprint
from motorfit.config import load_setup
pprint(load_setup("configs/local/bench.toml"))
PY
```

This reads files without opening CAN. Check the selected model, fixture values,
recording settings and zero-file path. An absent `zero_rad` is expected until you
calibrate the coordinate. Successful loading checks file composition; it does not
verify hardware addresses or approve the mechanical setup.

Continue with [Record motion](acquisition.md).
