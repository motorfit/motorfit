"""Release feature metrics with explicit unchanged windows and filtering."""

import numpy as np
from scipy.ndimage import median_filter


def scores(pred, measured, t, release):
    error = pred[:, 0] - measured[:, 0]
    result = {
        "position_mae_rad": float(np.mean(abs(error))),
        "position_rmse_rad": float(np.sqrt(np.mean(error**2))),
    }
    if release:
        window = (t >= 6.1) & (t < 7.8)
        late = (t >= 18) & (t < 20)
        q, y = (
            median_filter(measured[:, 0], size=5, mode="nearest"),
            median_filter(pred[:, 0], size=5, mode="nearest"),
        )
        pm, pp = float(q[window].max()), float(y[window].max())
        sm, sp = float(np.median(measured[late, 0])), float(np.median(pred[late, 0]))
        region = (t >= 6) & (t < 8)
        result.update(
            peak_measured_rad=pm,
            peak_predicted_rad=pp,
            stop_measured_rad=sm,
            stop_predicted_rad=sp,
            peak_error_rad=pp - pm,
            stop_error_rad=sp - sm,
            recoil_measured_rad=pm - sm,
            recoil_predicted_rad=pp - sp,
            recoil_error_rad=(pp - sp) - (pm - sm),
            release_mae_rad=float(np.mean(abs(error[region]))),
            peak_unfiltered_measured_rad=float(measured[region, 0].max()),
            peak_unfiltered_predicted_rad=float(pred[region, 0].max()),
            peak_time_measured_s=float(t[np.flatnonzero(window)[np.argmax(q[window])]]),
            peak_time_predicted_s=float(t[np.flatnonzero(window)[np.argmax(y[window])]]),
        )
    return result
