"""CAD bench scene with explicit measured-mass rigid-body properties.

The finite model includes the beam, six bolts/washers, weight, shoulder bolt and
nut. Motor rotor appearance is retained, while its inertia belongs to M1.
The compatibility mode preserves the fixture approximation used for fitting.
"""

import json
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import numpy as np

from .pendulum import Pendulum


@lru_cache(maxsize=8)
def load_asset_manifest(folder):
    return json.loads((Path(folder) / "manifest.json").read_text())


def bench_properties(log, assets, fixture_model="finite"):
    manifest = load_asset_manifest(str(Path(assets).resolve()))
    grams = round(log["weight_mass"] * 1000)
    fixture = manifest["fixtures"][str(grams)]
    parts = fixture["components"]
    expected = {
        "beam": log["arm_mass"],
        "weight": log["weight_mass"],
        "shoulder_bolt": log["bolt_mass"],
        "nut": log["nut_mass"],
    }
    for name, mass in expected.items():
        actual = next(p["mass_kg"] for p in parts if p["name"] == name)
        if not np.isclose(actual, mass, rtol=0, atol=1e-12):
            raise ValueError(f"CAD asset mass does not match recording: {name}")
    if not np.isclose(log["length"], 0.2):
        raise ValueError("This CAD assembly places the weight at the 200 mm hole")
    p = fixture["aggregate"]
    mass = p["mass_kg"]
    com, inertia = np.array(p["com_m"]), np.array(p["inertia_com_kg_m2"])
    if fixture_model == "identified_point":
        rig = Pendulum(log)
        com[0] = 0
        com[2] = -(rig.mass * rig.length + rig.arm_mass * rig.arm_com) / mass
        inertia[1, 1] = rig.compute_mass(0, 0) - mass * com[2] ** 2
        # Off-diagonal terms have no effect on the sole hinge DOF.
        inertia = np.diag(np.diag(inertia))
    elif fixture_model != "finite":
        raise ValueError(f"Unknown fixture model: {fixture_model}")
    return mass, com, inertia


def vector(values):
    return " ".join(f"{v:.17g}" for v in values)


def bench_xml(log, params, dt, *, assets, fixture_model="finite"):
    assets = Path(assets).resolve()
    manifest = load_asset_manifest(str(assets))
    mass, com, inertia = bench_properties(log, assets, fixture_model)
    grams = round(log["weight_mass"] * 1000)
    root = ET.Element("mujoco", model=f"rs05_cad_bench_{grams}g_{fixture_model}")
    ET.SubElement(root, "compiler", angle="radian", inertiafromgeom="false")
    opt = ET.SubElement(
        root,
        "option",
        timestep=str(dt),
        gravity="0 0 -9.80665",
        integrator="Euler",
        solver="Newton",
        iterations="100",
        tolerance="1e-12",
    )
    ET.SubElement(opt, "flag", eulerdamp="disable")
    visual = ET.SubElement(root, "visual")
    ET.SubElement(visual, "global", offwidth="1920", offheight="1080")
    ET.SubElement(visual, "quality", shadowsize="2048", offsamples="4")
    ET.SubElement(
        visual,
        "headlight",
        ambient="0.35 0.35 0.35",
        diffuse="0.65 0.65 0.65",
        specular="0.25 0.25 0.25",
    )
    ET.SubElement(root, "statistic", center="0 0 0.27", extent="0.5")
    asset = ET.SubElement(root, "asset")
    for name in manifest["meshes"]:
        ET.SubElement(asset, "mesh", name=name, file=str(assets / "meshes" / f"{name}.obj"))
    world = ET.SubElement(root, "worldbody")
    ET.SubElement(
        world, "light", name="key", pos="-0.3 -0.4 0.9", dir="0.2 0.5 -1", diffuse="0.75 0.75 0.75"
    )
    ET.SubElement(
        world,
        "light",
        name="fill",
        pos="0.5 0.2 0.6",
        dir="-0.7 -0.3 -1",
        castshadow="false",
        diffuse="0.35 0.35 0.35",
    )
    fixed = ET.SubElement(world, "body", name="fixed_bench", pos="0 0 .36")
    # The 40x40 extrusion sits in the supplied bracket's CAD Y/Z [-50,-10] corner.
    # It is fixed, so its display length and slot details do not affect hinge dynamics.
    if "extrusion_4040" in manifest["meshes"]:
        ET.SubElement(
            fixed,
            "geom",
            name="extrusion_4040",
            type="mesh",
            mesh="extrusion_4040",
            rgba=".48 .52 .57 1",
            contype="0",
            conaffinity="0",
        )
    else:
        ET.SubElement(
            fixed,
            "geom",
            name="extrusion_4040",
            type="box",
            pos="0 .03 -.07",
            size=".3 .02 .02",
            rgba=".48 .52 .57 1",
            contype="0",
            conaffinity="0",
        )
    moving = ET.SubElement(world, "body", name="pendulum", pos="0 0 .36")
    ET.SubElement(
        moving,
        "joint",
        name="pivot",
        type="hinge",
        axis="0 -1 0",
        ref=str(-params.q_offset),
        armature=str(params.armature),
        damping=str(params.friction_viscous),
        frictionloss=str(params.friction_base),
        solreffriction=f"-1 {-1 / dt}",
        solimpfriction="0.9999 0.9999 0.001",
    )
    ET.SubElement(
        moving,
        "inertial",
        mass=str(mass),
        pos=vector(com),
        fullinertia=vector(
            [
                inertia[0, 0],
                inertia[1, 1],
                inertia[2, 2],
                inertia[0, 1],
                inertia[0, 2],
                inertia[1, 2],
            ]
        ),
    )
    parts = [
        (fixed, "holding", ".65 .68 .73 1"),
        (fixed, "stator", ".10 .12 .15 1"),
        (moving, "rotor", ".48 .51 .56 1"),
        (moving, "beam", ".76 .80 .85 1"),
        (moving, "root_fasteners", ".24 .27 .31 1"),
        (moving, f"weight_{grams}g", ".78 .49 .18 1"),
        (moving, f"shoulder_bolt_{grams}g", ".13 .15 .18 1"),
        (moving, f"nut_{grams}g", ".60 .64 .69 1"),
    ]
    for body, name, rgba in parts:
        ET.SubElement(
            body,
            "geom",
            name=name,
            type="mesh",
            mesh=name,
            rgba=rgba,
            contype="0",
            conaffinity="0",
            group="1",
        )
    ET.SubElement(
        moving, "site", name="weight_center", pos="0 -.03 -.2", size=".001", rgba="1 .55 .08 0"
    )
    actuator = ET.SubElement(root, "actuator")
    ET.SubElement(actuator, "motor", name="rs05", joint="pivot", gear="1")
    return ET.tostring(root, encoding="unicode")
