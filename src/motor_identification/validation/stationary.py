"""Audit existing pre-run stationary snapshots without importing device code."""

import json
import struct

import numpy as np

from .feedback import capture_match, csv_write, frame_data, save, sha


def audit_stationary(dataset, root):
    manifest = dataset.rows
    inputs = {}
    rows = []
    for record in manifest:
        source = dataset.root / "snapshots" / f"{record['mass_g']}g" / f"pre-{record['index']:02d}"
        names = [
            "result.json",
            "frames.json",
            "statuses.json",
            "positions.json",
            "independent.canlog",
        ]
        for name in names:
            inputs[str(source / name)] = sha(source / name)
        result = json.loads((source / "result.json").read_text())
        assert result["error"] is None and result["uid"] == "542b38001c443916"
        original = json.loads((source / "frames.json").read_text())
        frames = [
            dict(
                direction=f["direction"], arbitration_id_hex=f"{f['id']:08x}", data_hex=f["payload"]
            )
            for f in original
        ]
        frame_count = capture_match(frames, source / "independent.canlog")
        tx = [frame_data(f)[0] >> 24 for f in frames if f["direction"] == "tx"]
        assert set(tx) == {2, 17}
        status_frames = [
            f for f in frames if f["direction"] == "rx" and frame_data(f)[0] >> 24 == 2
        ]
        states = json.loads((source / "statuses.json").read_text())
        assert len(states) == len(status_frames) == 301
        words = np.asarray([frame_data(f)[1] for f in status_frames])
        for j, key, limit in [
            (0, "position_rad", 12.57),
            (1, "velocity_rad_s", 50),
            (2, "torque_nm", 5.5),
        ]:
            decoded = words[:, j].astype(float) / 65535 * (2 * limit) - limit
            assert np.max(np.abs(decoded - np.asarray([s[key] for s in states]))) < 1e-12
        assert all(s["mode"] == 0 and s["faults"] == 0 for s in states)
        assert np.all(words[:, 2] == 32767)
        parameters = result["parameters"]
        for name, item in parameters.items():
            assert "error" not in item, (source, name)
            index = int(item["index"], 16)
            matching = [
                f
                for f in frames
                if f["direction"] == "rx"
                and frame_data(f)[0] >> 24 == 17
                and int.from_bytes(bytes.fromhex(f["data_hex"])[:2], "little") == index
            ]
            payload = bytes.fromhex(matching[0]["data_hex"])
            fmt = "<I" if name in {"run_mode", "canTimeout", "zero_sta"} else "<f"
            assert struct.unpack(fmt, payload[4:])[0] == item["value"], (name, source)
        q = np.asarray([s["position_rad"] for s in states])
        v = np.asarray([s["velocity_rad_s"] for s in states])
        positions = json.loads((source / "positions.json").read_text())
        rows.append(
            dict(
                id=record["id"],
                mass_g=record["mass_g"],
                source=str(source),
                frames=frame_count,
                samples=len(states),
                q_range_mrad=float(np.ptp(q) * 1000),
                q_word_span=int(np.ptp(words[:, 0])),
                v_rms=float(np.sqrt(np.mean(v * v))),
                v_min=float(v.min()),
                v_max=float(v.max()),
                mechpos_range_mrad=float(np.ptp([s["position_rad"] for s in positions]) * 1000),
                cur_kp=parameters["cur_kp"]["value"],
                cur_ki=parameters["cur_ki"]["value"],
                cur_filt_gain=parameters["cur_filt_gain"]["value"],
                iqf=parameters["iqf"]["value"],
                spd_filt_gain_recorded="spd_filt_gain" in parameters,
                all_modes_reset_and_faults_zero=True,
                independent_capture_matches=True,
            )
        )
    firmware = dataset.root / "provenance/firmware-read.json"
    inputs[str(firmware)] = sha(firmware)
    save(root / "configuration/firmware-read-existing.json", json.loads(firmware.read_text()))
    save(root / "configuration/input-sha256.json", inputs)
    csv_write(root / "analysis/stationary-snapshots.csv", rows)
    save(
        root / "analysis/stationary-summary.json",
        dict(
            records=len(rows),
            samples=sum(r["samples"] for r in rows),
            frames=sum(r["frames"] for r in rows),
            q_range_mrad=[
                min(r["q_range_mrad"] for r in rows),
                max(r["q_range_mrad"] for r in rows),
            ],
            q_word_span=[min(r["q_word_span"] for r in rows), max(r["q_word_span"] for r in rows)],
            v_rms_range=[min(r["v_rms"] for r in rows), max(r["v_rms"] for r in rows)],
            cur_filt_gain_values=sorted({r["cur_filt_gain"] for r in rows}),
            cur_kp_values=sorted({r["cur_kp"] for r in rows}),
            cur_ki_values=sorted({r["cur_ki"] for r in rows}),
            iqf_values=sorted({r["iqf"] for r in rows}),
            spd_filt_gain_read_count=sum(r["spd_filt_gain_recorded"] for r in rows),
            representative=next(
                r for r in rows if r["id"] == "200g_35_v3_200g_r03_lift_and_drop_kp20_kd0.8"
            ),
        ),
    )
    print(f"Verified {len(rows)} stationary snapshots; {len(inputs)} total input files")
