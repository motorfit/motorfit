import pytest


@pytest.fixture
def m1_params():
    pytest.importorskip("mujoco")
    from motorfit.identification.mujoco import M1Parameters

    return M1Parameters(
        1.1639233433530467,
        0.00023631471353394536,
        -0.001214251462938909,
        0.006293081495280065,
        0.04300222579284436,
        0.002987922558477437,
        -5.5,
        5.5,
    )


@pytest.fixture
def pendulum_log():
    return dict(
        mass=0.1248,
        arm_mass=0.11,
        length=0.2,
        arm_com=0.0900802043205295,
        arm_inertia=0.0014073185763008957,
        hub_inertia=0.00000216,
        kp=30,
        kd=0.8,
        dt=0.01,
        entries=[dict(position=0.1, speed=0, goal_position=0.1, torque_enable=True)] * 20,
    )
