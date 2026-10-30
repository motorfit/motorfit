# Data formats

There are two input paths. **Fitting** uses a directory of processed recording
JSON files. **Packaged replay** uses a manifest that also identifies a fixed model
and saved reference predictions. A manifest is unnecessary for the ordinary
record–fit–evaluate workflow.

## A native recording

`motorfit record --out RUN` creates:

```text
RUN/
  raw.json
  samples.jsonl
  frames.jsonl
```

`raw.json` contains metadata followed by an `entries` array. Key metadata includes:

| Field | Meaning |
|---|---|
| `motor`, `motor_spec` | Model identity and the full profile snapshot |
| `config` | Resolved setup, fixture, device and recording settings |
| `mass`, `length`, `arm_mass`, … | Fixture quantities used by the model |
| `kp`, `kd` | Requested controller gains |
| `kp_encoded`, `kd_encoded` | Gains actually represented in command fields |
| `goal_speed`, `feedforward_torque` | Encoded values for the velocity and torque targets |
| `trajectory`, `trajectory_parameters` | Motion name, amplitude, duration and time scaling |
| `coordinate` | Physical-zero convention and encoder offset |
| `completed`, `error`, `cleanup_error` | Run outcome; the cleanup field is present when cleanup failed |

Each sample includes:

| Field | Unit / interpretation |
|---|---|
| `timestamp` | Seconds since the first received feedback sample |
| `position` | Encoder position minus software zero, in rad |
| `speed` | Feedback angular velocity, in rad/s |
| `load` | Firmware-reported nominal torque, in N·m |
| `goal_position` | Encoded position target minus software zero, in rad |
| `torque_enable` | Enabled state derived from the feedback mode |
| `input_volts` | Configured supply voltage |
| `temperature`, `faults`, `mode` | Feedback status; normalized mode is 0 disabled or 2 enabled |
| `command_monotonic_time`, `monotonic_time` | Host command and feedback-reception times |
| `bus_timestamp`, `transaction_id` | Adapter timestamp and local transaction counter |

Damiao also saves its original `status_code` and `rotor_temperature`.
`load` is neither the transmitted torque command nor an independent shaft-torque
measurement. The fitter reconstructs the controller law from recorded targets and
gains; it does not use `load` as an applied-torque sensor.

`samples.jsonl` is flushed during acquisition. `frames.jsonl` records both directions,
CAN IDs, flags and payloads, including frames that were discarded for matching.
Host reception time is not a motor-side sensor timestamp. The local transaction
counter is not a sequence number transmitted by either motor protocol.

## Processed recordings

`process` retains the metadata, adds `dt`, and replaces `entries` with samples on a
uniform grid from zero up to, but excluding, the last raw timestamp. Numeric fields
are linearly interpolated; `torque_enable` is then thresholded at 0.5.

Use processed position and commands for fitting. Use raw samples and frames when
examining exact event order, fault/status values or communication timing.

`fit` and `plot` read top-level `*.json` files from `--logdir`; they do not recurse
into subdirectories. Keep metadata summaries outside those directories.

## Fitted models

A model file contains:

```text
model                    M1–M6 family, such as "m1"
actuator                 Saved model-profile name, such as "rs05"
motor_spec               Full motor definition used for the fit
<parameter names>        Numeric fitted or fixed values
identification           Training score; optional internal gain-validation score
```

The complete parameter meanings are in [Parameters](parameters.md). Older frozen
models can omit the `identification` object. The model loader checks that
`actuator` matches `motor_spec.name`.

## Portable datasets

`demo`, `verify` and `replay` use a schema-1 manifest. The bundled
[`tests/fixtures/offline/manifest.json`](https://github.com/motorfit/motorfit/blob/main/tests/fixtures/offline/manifest.json)
is a complete example that can be copied with its surrounding directory.

| Manifest field | Contents |
|---|---|
| `schema_version` | `1` |
| `motor_uid` | Identity shared by the curated raw and processed logs |
| `model_path`, `model_sha256` | Relative model path and its SHA-256 |
| `records` | One object per recording |
| `split_counts` | Number of records assigned to each split |
| `formal_raw_samples` | Sum of the raw sample counts |

Each record names `id`, `split`, `raw_path`, `raw_sha256`, `processed_path`, `sha256`,
`reference_path` and `reference_sha256`. The reference `.npz` must contain a
`prediction` array. The current reports also use `mass_g`, `repeat`, `trajectory`,
`kp` and `kd`. Optional `record_path` and `source_sha256` index original capture
files for the historical RS05 audits.

All paths resolve relative to the manifest. Raw and processed logs must contain
matching `motor_uid` and `split` values. The current native recorder does not add
these curation fields or create BAM reference arrays automatically; preparing a
portable dataset is an explicit packaging step. Work on curated copies and compute
hashes after their contents are final.

```bash
uv run --no-sync motorfit verify --dataset tests/fixtures/offline/manifest.json
```

`verify` checks files, hashes, identity, split counts and the raw sample total. It
checks dataset consistency, not model accuracy. Do not change a hash merely to
make an unexpected mismatch pass.
