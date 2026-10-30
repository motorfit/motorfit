"""CAD asset, mass moment and complete-scene replay checks."""

import hashlib
import json
from functools import partial

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from motor_identification.identification.mujoco import PendulumReplay  # noqa: E402
from motor_identification.rigs.pendulum import Pendulum  # noqa: E402
from motor_identification.rigs.rs05_bench import bench_xml  # noqa: E402


def test_cad_source_and_all_meshes_match_export_manifest(bench_assets):
    manifest = json.loads((bench_assets / "manifest.json").read_text())
    assert (
        hashlib.sha256(
            (bench_assets / "source/identification_platform_rs05.step").read_bytes()
        ).hexdigest()
        == manifest["step_sha256"]
    )
    for name, info in manifest["meshes"].items():
        mesh = bench_assets / "meshes" / f"{name}.obj"
        assert hashlib.sha256(mesh.read_bytes()).hexdigest() == info["sha256"]
        assert info["triangles"] > 0


@pytest.mark.parametrize("grams", [100, 200, 500])
def test_complete_cad_scene_has_measured_mass_gravity_and_finite_weight_inertia(
    grams, m1_params, bench_logs, bench_assets
):
    params = m1_params
    log = next(log for log in bench_logs if round(log["weight_mass"] * 1000) == grams)
    replay = PendulumReplay(log, params, 0.002, xml_factory=partial(bench_xml, assets=bench_assets))
    model, data = replay.model, replay.data
    assert model.nq == model.nv == model.nu == 1
    assert model.ngeom == 9
    assert model.geom("extrusion_4040").bodyid == model.body("fixed_bench").id
    assert model.body("fixed_bench").mass == 0
    assert model.body("pendulum").mass == pytest.approx(log["mass"] + 0.110 + 0.015)
    # 500 g annulus alone adds 0.5*m*(Ro^2+Ri^2), independent of mesh tessellation.
    radius = 0.0345 if grams == 500 else 0.023
    disc_self = 0.5 * log["weight_mass"] * (radius**2 + 0.00525**2)
    rig = Pendulum(log)
    expected_floor = rig.compute_mass(0, 0) + params.armature + disc_self
    inertia = np.empty(model.nv)
    mujoco.mj_mulM(model, data, inertia, np.ones(model.nv))
    assert expected_floor < inertia[0] < expected_floor + 1e-6
    for q in (-0.5, 0, 0.4):
        data.qpos[0], data.qvel[0] = q, 0
        mujoco.mj_forward(model, data)
        assert -data.qfrc_bias[0] == pytest.approx(
            rig.compute_bias(q + params.q_offset, 0), abs=1.3e-6
        )


@pytest.mark.parametrize("grams", [100, 200, 500])
def test_cad_geometry_preserves_identified_point_model_rollout(
    grams, m1_params, bench_logs, bench_assets
):
    params = m1_params
    log = next(log for log in bench_logs if round(log["weight_mass"] * 1000) == grams)
    baseline = PendulumReplay(log, params, 0.002).rollout()
    scene = PendulumReplay(
        log,
        params,
        0.002,
        xml_factory=partial(bench_xml, assets=bench_assets, fixture_model="identified_point"),
    )
    predicted = scene.rollout()
    np.testing.assert_allclose(predicted, baseline, atol=1e-10, rtol=1e-10)
    np.testing.assert_array_equal(
        predicted[np.array([not e["torque_enable"] for e in log["entries"]]), 3], 0
    )
