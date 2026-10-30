"""Native BAM names retain the documented trajectory semantics."""

import math

import pytest

from motorfit.acquisition.trajectories import Trajectory


def test_soccer_sweep_has_its_own_name():
    sweep = Trajectory({"trajectory": "soccer_sweep"})
    assert sweep.duration == 30.0
    assert sweep(2.0) == pytest.approx((math.sin(0.4), True))
    assert sweep(2.0)[0] != pytest.approx(Trajectory({"trajectory": "sin_time_square"})(2.0)[0])


def test_scaled_trajectory_preserves_release():
    scaled = Trajectory({"trajectory": "lift_and_drop", "duration_s": 30, "amplitude": 0.5})
    assert scaled(10) == pytest.approx((-math.pi / 4, False))
