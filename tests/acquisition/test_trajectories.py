"""Native BAM names retain the documented trajectory semantics."""

import math

import pytest

from motorfit.acquisition.trajectories import Trajectory


def test_scaled_trajectory_preserves_release():
    scaled = Trajectory({"trajectory": "lift_and_drop", "duration_s": 30, "amplitude": 0.5})
    assert scaled(10) == pytest.approx((-math.pi / 4, False))
