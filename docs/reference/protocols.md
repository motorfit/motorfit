# Protocols

MotorFit's native adapters are implemented in Python using python-can. The references below describe manufacturer protocols, register layouts and control modes.

- [RobStride product information](https://github.com/RobStride/Product_Information/tree/667444b6d1f9fabe01b87765ee73abd29d54e71b): model manuals for extended-CAN command and feedback encoding. Profiles link to the corresponding model manual. Alternate CANopen and MIT firmware layouts require their own adapters.
- [Damiao control examples](https://github.com/dmBots/motor-control-routine/tree/ae6c1031056908d3d8059f003bd015a9d6b21894): MIT command packing, feedback fields and register access. Profile ranges are templates; the driver checks PMAX, VMAX and TMAX against the connected device before enabling.

Protocol links describe family-level framing and registers; they do not certify every shipped template range for every firmware revision. Match the template to the mounted device. Each recorded motor specification is saved with its data and fitted model. Protocol templates specify an experimental operating envelope; they do not invent model-specific ratings or calibrated constants. Current verification uses golden packet checks, simulated device responses, failure cases and the actual BAM process/fit/evaluate/plot chain. New physical motors have not been exercised.
