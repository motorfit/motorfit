# RS05 results and remaining errors

The selected M1 model predicts most of the recorded tracking motion with small
position error. The release experiment exposes behavior that this model does not
fully explain. Both observations are necessary when deciding where to use it.

## Accuracy on the final-test split

The later MuJoCo/MJWarp 3.17 comparison contains 36 final-test recordings. Position
MAE is calculated per recording and then averaged across those recordings:

| Prediction | Mean MAE | Comparison conditions |
|---|---:|---|
| Frozen BAM M1 | 2.035 mrad | Saved analytical reference |
| MuJoCo CPU | 2.220 mrad | Archived full solver options, original friction settings |
| mjlab / MJWarp | 2.220 mrad | Matching 3.17 GPU comparison |
| MuJoCo CPU | 2.251 mrad | Default-friction comparison |
| mjlab / MJWarp | 2.251 mrad | Matching default-friction GPU comparison |

For the original-friction CPU case, the worst final-test record has about
**5.389 mrad** position MAE: the 200 g lift-and-release run. An average of
2.220 mrad therefore does not mean every trajectory stays within that error.

These figures come from the full archive's `results/replay/mjlab317/*/metrics.json`.
Each folder's `protocol.json` records the model hash, timestep, package versions
and solver settings. The three-record quickstart is a smaller subset and has
different aggregate statistics.

## Agreement between engines

The matching CPU/GPU results support consistency of the tested M1 implementation
and solver settings. Newton also provides an integration path through
`SolverMuJoCo`; this does not constitute an independent Featherstone comparison.

The later 3.17 study includes the required NoSlip settings. Limitations found in
an earlier MJWarp environment should not be attributed to that later run. Results
from different environments remain separate in the archive.

## What happens after release

In the representative 200 g release, the measured arm retreats by about
**2.714 mrad** under the study's specified processed-signal metric. Frozen M1
predicts no such retreat and has a stopping error near **7.116 mrad**.

Changing the modeled disable event to the raw STOP-send time reduces that stopping
error to about **7.068 mrad**. It improves early release alignment, but leaves the
missing retreat and most of the stopping bias unexplained. Timing alone is therefore
insufficient for this case.

The evidence is stored under `results/release-alignment/` and
`results/comparisons/`. STOP-send and reply times are observed communication events;
they do not directly identify when phase current vanished.

## Follow-up model investigations

Dahl/LuGre friction, elastic and sensor/filter candidates improved some tracking
metrics, but did not jointly explain release recoil and stopping across the tested
loads. They were not promoted to replace the formal M1 model. These later analyses
are diagnostic work using observed residuals, rather than a new untouched-test
model-selection result.

The 500 g peak-to-stop motion includes a much larger backswing. It should not be
interpreted as the same small-retreat regime measured in the 200 g case. Compare
results only when signal processing, event definitions and measurement windows
match. The generic replay tool's release-window submetrics use the historical RS05
windows: 2–6 s active, 6–8 s release, and 8 s onward rest. New trajectories need
metrics aligned to their own actual events.

## Scope of the result

The parameters apply to RS05 UID `542b38001c443916`, the measured fixture and the
recorded operating conditions. Other motors, changed mounting, different firmware
and robot contact tasks need independent evaluation.

CAN torque is a nominal firmware value, and static register inspection does not
supply a time-resolved current measurement during motion. The study identifies an
effective mechanical model; it does not separately measure electrical constants
or establish a physical explanation for every residual.

Use the [evaluation guide](../guide/validation.md) to apply the same distinction
between tracking accuracy, implementation consistency and unexplained mechanics
to a new motor.
