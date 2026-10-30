# Offline fixture

This self-contained sample is shared by the [quickstart](../../../docs/getting-started/quickstart.md)
and `tests/test_offline.py`. It contains one complete recording for each of the
100/200/500 g loads from the [RS05 study](../../../docs/case-studies/rs05.md):

- `raw/`: the three original BAM-format recordings and their metadata.
- `processed/`: the corresponding resampled inputs.
- `model.json`: the selected, frozen M1 parameters.
- `reference/`: saved BAM trajectories used to detect regressions.
- `manifest.json`: relative paths, original split labels and input SHA-256 hashes.

The directory can be copied intact. It contains every dataset input needed by
`motorfit demo`; it is not the complete model-selection or final-test dataset.

From the repository root, use a new output directory:

```bash
uv run --frozen motorfit demo \
  --dataset tests/fixtures/offline/manifest.json --output outputs/demo
```

New fits and outputs belong under `data/<study>/` or `outputs/`. Keep the fixture's
recordings and model unchanged when demonstrating processing or fitting.
