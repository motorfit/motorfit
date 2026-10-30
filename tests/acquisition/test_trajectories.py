"""Native BAM names retain the documented trajectory semantics."""

import math

import pytest
from bam.trajectory import trajectories

from motor_identification.acquisition.trajectories import Trajectory


@pytest.mark.parametrize("name", ["sin_time_square", "sin_sin", "lift_and_drop", "up_and_down"])
def test_native_bam_trajectory(name):
    local = Trajectory({"trajectory": name})
    upstream = trajectories[name]
    assert local.duration == upstream.duration == 6.0
    for t in (0.0, 0.5, 1.99, 2.0, 3.0, 5.99):
        assert local(t) == pytest.approx(upstream(t))


def test_soccer_sweep_has_its_own_name():
    sweep = Trajectory({"trajectory": "soccer_sweep"})
    assert sweep.duration == 30.0
    assert sweep(2.0) == pytest.approx((math.sin(0.4), True))
    assert sweep(2.0)[0] != pytest.approx(Trajectory({"trajectory": "sin_time_square"})(2.0)[0])
