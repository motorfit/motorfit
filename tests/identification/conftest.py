import pytest


@pytest.fixture
def bench_assets():
    import os
    from pathlib import Path

    default = Path(__file__).resolve().parents[2] / "data/rs05/assets/bench"
    assets = Path(os.environ.get("MOTORFIT_RS05_ASSETS", default)).resolve()
    if not (assets / "manifest.json").is_file():
        pytest.skip("RS05 CAD archive absent; provide data/rs05/assets/bench or MOTORFIT_RS05_ASSETS")
    return assets


@pytest.fixture
def bench_logs():
    import math
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    logs = []
    for grams in (100, 200, 500):
        log = tomllib.loads((root / f"configs/fixtures/pendulum_{grams}g_200mm.toml").read_text())
        log.update(kp=20, kd=0.8, dt=0.01)
        log["entries"] = [
            dict(
                position=0.1, speed=0, goal_position=0.3 * math.sin(k * 0.04), torque_enable=k < 150
            )
            for k in range(200)
        ]
        logs.append(log)
    return logs


@pytest.fixture
def m1_params():
    pytest.importorskip("mujoco")
    from motor_identification.identification.mujoco import M1Parameters

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
