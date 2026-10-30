"""Export the supplied STEP and nominal hardware into a self-contained bench asset.

Run with uv run --no-project --python 3.11 --with cadquery==2.8.0.
CAD coordinates are mm; exported meshes/inertias use SI, Z up, shaft along -Y.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import cadquery as cq
import numpy as np
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

ROTATION = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
PIVOT = np.array([0, 40, 0])


def properties(shape, mass):
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, p)
    c = p.CentreOfMass()
    tensor = p.MatrixOfInertia()
    inertia = np.array([[tensor.Value(i + 1, j + 1) for j in range(3)] for i in range(3)])
    return {
        "mass_kg": mass,
        "com_m": ((ROTATION @ (np.array([c.X(), c.Y(), c.Z()]) - PIVOT)) * 0.001).tolist(),
        "inertia_com_kg_m2": (ROTATION @ inertia @ ROTATION.T * mass / p.Mass() * 1e-6).tolist(),
        "volume_mm3": p.Mass(),
    }


def mesh(path, shapes):
    offset, triangles = 0, 0
    with path.open("w") as f:
        f.write("# Supplied STEP / documented nominal hardware; metres, Z up\n")
        for shape in shapes:
            vertices, faces = shape.tessellate(0.15, 0.2)
            v = (np.array([v.toTuple() for v in vertices]) - PIVOT) @ ROTATION.T * 0.001
            for x, y, z in v:
                f.write(f"v {x:.10g} {y:.10g} {z:.10g}\n")
            for a, b, c in faces:
                f.write(f"f {a + offset + 1} {b + offset + 1} {c + offset + 1}\n")
            offset += len(vertices)
            triangles += len(faces)
    return {"vertices": offset, "triangles": triangles}


def cylinder(radius, height, z=0):
    return cq.Solid.makeCylinder(radius, height, cq.Vector(0, 0, z))


def aggregate(parts):
    mass = sum(p["mass_kg"] for p in parts)
    com = sum(p["mass_kg"] * np.array(p["com_m"]) for p in parts) / mass
    inertia = np.zeros((3, 3))
    for p in parts:
        d = np.array(p["com_m"]) - com
        inertia += np.array(p["inertia_com_kg_m2"]) + p["mass_kg"] * (
            np.dot(d, d) * np.eye(3) - np.outer(d, d)
        )
    return {
        "mass_kg": mass,
        "com_m": com.tolist(),
        "inertia_com_kg_m2": inertia.tolist(),
        "pivot_inertia_kg_m2": float(inertia[1, 1] + mass * (com[0] ** 2 + com[2] ** 2)),
        "gravity_moment_kg_m": float(-mass * com[2]),
    }


def extrusion_4040():
    """40 mm envelope and CAD mounting corner; slot detail/600 mm length illustrative."""
    profile = (
        cq.Workplane("YZ", origin=(-300, -30, -30))
        .rect(40, 40)
        .extrude(600)
        .edges("|X")
        .fillet(1)
        .val()
    )
    for y, z, width, height in [(0, 18, 8, 6), (0, -18, 8, 6), (18, 0, 6, 8), (-18, 0, 6, 8)]:
        cut = (
            cq.Workplane("YZ", origin=(-301, -30 + y, -30 + z))
            .rect(width, height)
            .extrude(602)
            .val()
        )
        profile = profile.cut(cut)
    return profile.cut(cq.Solid.makeCylinder(4, 602, cq.Vector(-301, -30, -30), cq.Vector(1, 0, 0)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--step", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "meshes").mkdir()
    (args.output / "source").mkdir()
    shutil.copy2(args.step, args.output / "source" / args.step.name)
    solids = cq.importers.importStep(str(args.step)).val().Solids()
    assert len(solids) == 35, "Unexpected STEP assembly revision"
    # Verified STEP assembly tree: holding=1 solid, rotor=4, stator=29, beam=1.
    groups = {
        "holding": solids[:1],
        "rotor": solids[1:5],
        "stator": solids[5:34],
        "beam": solids[34:],
    }
    manifest = {
        "cadquery_version": cq.__version__,
        "step_source": str(args.step),
        "step_sha256": hashlib.sha256(args.step.read_bytes()).hexdigest(),
        "cad_to_world": {"rotation": ROTATION.tolist(), "pivot_mm": PIVOT.tolist(), "scale": 0.001},
        "shaft_axis": [0, -1, 0],
        "meshes": {},
        "fixtures": {},
        "sources": {
            "cad": "User supplied identification_platform_rs05.step",
            "masses": "User measured masses 2026-10-11; bolt mapping corrected 2026-10-24",
            "weight_dimensions": "User supplied nominal dimensions recorded 2026-10-11: 100g 46x8mm, 200g 46x16.3mm, 500g 69x17.5mm; hole 10-11mm, midpoint 10.5mm used",
            "hardware": "User supplied drawings: M4x20 head7.2x4mm; washer OD8 ID4 thickness0.8mm; shoulder10/M8/(12 or20), head16x7 thread8x13.25mm; M8 nut flats12.9 thickness6.3mm",
            "rotor": "Visual mesh only; motor internal inertia already represented by frozen M1 armature",
            "assembly": "Weights placed against front of beam, nut behind; axial placement has no effect on shaft-axis inertia or gravity",
        },
    }
    for name, shapes in groups.items():
        manifest["meshes"][name] = mesh(args.output / "meshes" / f"{name}.obj", shapes)
    manifest["meshes"]["extrusion_4040"] = mesh(
        args.output / "meshes/extrusion_4040.obj", [extrusion_4040()]
    )
    manifest["sources"]["support"] = (
        "User confirmed 40x40 mm aluminum extrusion on 2026-10-27. Axis CAD X; "
        "envelope CAD Y/Z [-50,-10] mm matches inner bracket faces. "
        "600 mm displayed length, 1 mm corner radius, grooves/bore are illustrative."
    )
    arm = properties(solids[34], 0.110)
    arm["name"] = "beam"
    common, common_shapes = [arm], []
    for i in range(6):
        x, y = 12 * np.cos(i * np.pi / 3), 40 + 12 * np.sin(i * np.pi / 3)
        bolt = cylinder(2, 20, 1.8).fuse(cylinder(3.6, 4, 21.8)).translate((x, y, 0))
        washer = cylinder(4, 0.8, 21).cut(cylinder(2, 0.8, 21)).translate((x, y, 0))
        for name, shape, mass in [
            (f"root_bolt_{i}", bolt, 0.0023),
            (f"root_washer_{i}", washer, 0.0002),
        ]:
            common.append({"name": name, **properties(shape, mass)})
            common_shapes.append(shape)
    manifest["meshes"]["root_fasteners"] = mesh(
        args.output / "meshes/root_fasteners.obj", common_shapes
    )
    for grams, diameter, thick, shoulder, bolt_mass in [
        (100, 46, 8, 12, 0.0205),
        (200, 46, 16.3, 20, 0.0251),
        (500, 69, 17.5, 20, 0.0251),
    ]:
        weight = (
            cylinder(diameter / 2, thick, 21).cut(cylinder(5.25, thick, 21)).translate((0, -160, 0))
        )
        end = 21 + thick
        bolt = (
            cylinder(8, 7, end)
            .fuse(cylinder(5, shoulder, end - shoulder))
            .fuse(cylinder(4, 13.25, end - shoulder - 13.25))
            .translate((0, -160, 0))
        )
        nut = (
            cq.Workplane("XY")
            .polygon(6, 12.9 / np.cos(np.pi / 6))
            .circle(4)
            .extrude(6.3)
            .val()
            .translate((0, -160, 8.7))
        )
        parts = common.copy()
        for name, shape, mass in [
            ("weight", weight, grams / 1000),
            ("shoulder_bolt", bolt, bolt_mass),
            ("nut", nut, 0.0043),
        ]:
            full_name = f"{name}_{grams}g"
            parts.append({"name": name, **properties(shape, mass)})
            manifest["meshes"][full_name] = mesh(
                args.output / "meshes" / f"{full_name}.obj", [shape]
            )
        manifest["fixtures"][str(grams)] = {
            "weight_diameter_m": diameter / 1000,
            "weight_thickness_m": thick / 1000,
            "weight_hole_diameter_m": 0.0105,
            "components": parts,
            "aggregate": aggregate(parts),
        }
    for name, entry in manifest["meshes"].items():
        entry["sha256"] = hashlib.sha256(
            (args.output / "meshes" / f"{name}.obj").read_bytes()
        ).hexdigest()
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({g: f["aggregate"] for g, f in manifest["fixtures"].items()}, indent=2))


if __name__ == "__main__":
    main()
