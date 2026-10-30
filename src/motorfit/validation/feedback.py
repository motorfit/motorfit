"""Read existing RS05 files only; write derived audit evidence under --root.

No acquisition modules are imported and no CAN interfaces are accessed.
"""

import argparse
import csv
import hashlib
import json
import re
import struct
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import median_filter

REP = "200g_35_v3_200g_r03_lift_and_drop_kp20_kd0.8"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            data,
            indent=2,
            allow_nan=False,
            default=lambda value: value.item() if isinstance(value, np.generic) else str(value),
        )
        + "\n"
    )


def csv_read(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def csv_write(path, rows):
    with path.open("w") as f:
        writer = csv.DictWriter(f, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def decode(words, limit):
    # Explicit float32 intermediates reproduce the frozen official C++ routine.
    lo, hi = np.float32(-limit), np.float32(limit)
    return ((hi - lo) * np.asarray(words, dtype=np.float32) / np.float32(65535) + lo).astype(float)


def frame_data(frame):
    ident = int(frame["arbitration_id_hex"], 16)
    words = struct.unpack(">4H", bytes.fromhex(frame["data_hex"]))
    return ident, words


def capture_match(frames, path):
    bus = {"tx": [], "rx": []}
    for line in path.read_text().splitlines():
        m = re.fullmatch(r"\((\d+)\.(\d+)\) can0 ([0-9A-Fa-f]+)#([0-9A-Fa-f]{16})", line)
        assert m, line
        seconds, fraction, ident, payload = m.groups()
        ident = int(ident, 16)
        direction = "rx" if ident & 0xFFFF == 0x7FFD else "tx"
        ns = int(seconds) * 10**9 + int(fraction.ljust(9, "0"))
        bus[direction].append((ident, payload.lower(), ns))
    for direction in bus:
        own = [f for f in frames if f["direction"] == direction]
        assert len(own) == len(bus[direction])
        for frame, (ident, payload, ns) in zip(own, bus[direction]):
            assert int(frame["arbitration_id_hex"], 16) == ident
            assert frame["data_hex"].lower() == payload
            frame["bus_ns"] = ns
    return sum(map(len, bus.values()))


def velocity_bins(t, q, v, begin, end, width=0.1):
    rows = []
    for a in np.arange(begin, end - width / 2, width):
        b = a + width
        inner = t[(t > a) & (t < b)]
        ts = np.r_[a, inner, b]
        mean_v = np.trapezoid(np.interp(ts, t, v), ts) / width
        qdot = (np.interp(b, t, q) - np.interp(a, t, q)) / width
        rows.append((a, b, qdot, mean_v))
    return np.asarray(rows)


def analyze_record(row, root, inputs, dataset):
    record = dataset.record_dir(row)
    processed = dataset.resolve(row["processed_path"])
    assert sha(processed) == row["sha256"]
    inputs[str(processed)] = sha(processed)
    raw_path = dataset.resolve(row["raw_path"])
    raw = json.loads(raw_path.read_text())
    inputs[str(raw_path)] = sha(raw_path)
    for name, info in raw["source_files"].items():
        source = record / name
        assert sha(source) == info["sha256"], str(source)
        inputs[str(source)] = info["sha256"]
    frames = csv_read(record / "frames.csv")
    bus_count = capture_match(frames, record / "independent.canlog")
    samples = csv_read(record / "samples.csv")
    result = json.loads((record / "result.json").read_text())
    data = json.loads(processed.read_text())
    ns = np.array([int(s["host_monotonic_ns"]) for s in samples], dtype=np.int64)
    t = (ns - ns[0]) / 1e9
    rx_map = {int(f["host_monotonic_ns"]): f for f in frames if f["direction"] == "rx"}
    sample_rx = [rx_map[n] for n in ns]
    words = np.asarray([frame_data(f)[1] for f in sample_rx])
    ids = np.asarray([frame_data(f)[0] for f in sample_rx])
    assert np.all(ids >> 24 == 2)
    assert np.all((ids >> 16) & 63 == 0)
    q = decode(words[:, 0], 12.57) - result["fixed_zero_rad"]
    v = decode(words[:, 1], 50)
    torque = decode(words[:, 2], 5.5)
    active = np.asarray([int(s["torque_enable"]) for s in samples])
    assert np.array_equal((ids >> 22) & 3, active * 2)
    for key, decoded in [
        ("position_rad", q + result["fixed_zero_rad"]),
        ("velocity_rad_s", v),
        ("torque_nm", torque),
    ]:
        assert np.array_equal(np.array([float(s[key]) for s in samples]), decoded), (row["id"], key)
    raw_entries = raw["entries"]
    for key, values in [
        ("timestamp", t),
        ("position", q),
        ("speed", v),
        ("load", torque),
        ("torque_enable", active),
    ]:
        assert np.array_equal(np.array([e[key] for e in raw_entries]), values), (row["id"], key)
    pt = np.asarray([e["timestamp"] for e in data["entries"]])
    errors = {}
    for key, values in [("position", q), ("speed", v), ("load", torque)]:
        actual = np.asarray([e[key] for e in data["entries"]])
        errors[key] = float(np.max(np.abs(actual - np.interp(pt, t, values))))
        assert errors[key] < 1e-12, (row["id"], key, errors[key])
    pa = np.array([e["torque_enable"] for e in data["entries"]])
    assert np.array_equal(pa, np.interp(pt, t, active) > 0.5)
    check = dict(
        id=row["id"],
        mass_g=row["mass_g"],
        samples=len(samples),
        frames=bus_count,
        decoded_sample_matches=True,
        independent_direction_sequences_match=True,
        source_hashes_match=True,
        resampling_max_error=max(errors.values()),
        final_iq_a=result["final_iq_a"],
    )
    if row["trajectory"] != "lift_and_drop":
        return check, None, [], []
    idx = int(np.flatnonzero(active == 0)[0])
    assert idx == 600 and np.all(active[idx:] == 0)
    stop = [
        f
        for f in frames
        if f["direction"] == "tx"
        and frame_data(f)[0] >> 24 == 4
        and ns[idx - 1] < int(f["host_monotonic_ns"]) < ns[idx]
    ]
    assert len(stop) == 1 and stop[0]["data_hex"] == "0000000000000000"
    stop = stop[0]
    stop_ns = int(stop["host_monotonic_ns"])
    transition = [f for f in frames if stop_ns <= int(f["host_monotonic_ns"]) < ns[idx]]
    ack = [f for f in transition if f["direction"] == "rx"]
    assert len(ack) == 2 and all((frame_data(f)[0] >> 22) & 3 == 0 for f in ack)
    writes = [f for f in transition if f["direction"] == "tx" and frame_data(f)[0] >> 24 == 18]
    assert len(writes) == 1 and writes[0]["data_hex"] == "0570000000000000"
    after = [
        f
        for f in frames
        if f["direction"] == "tx" and stop_ns < int(f["host_monotonic_ns"]) <= ns[-1]
    ]
    kinds = [frame_data(f)[0] >> 24 for f in after]
    assert kinds.count(2) == len(samples) - idx and set(kinds) == {2, 18}
    assert np.all(words[idx:, 2] == 32767)
    bus0 = sample_rx[0]["bus_ns"]
    bus_t = np.asarray([(f["bus_ns"] - bus0) / 1e9 for f in sample_rx])
    tstop = (stop_ns - ns[0]) / 1e9
    events = []
    for f in frames:
        host_t = (int(f["host_monotonic_ns"]) - ns[0]) / 1e9
        if tstop - 0.02 <= host_t <= tstop + 0.075:
            ident, w = frame_data(f)
            feedback = f["direction"] == "rx" and ident >> 24 == 2
            events.append(
                dict(
                    id=row["id"],
                    host_time_s=float(host_t),
                    bus_time_s=(f["bus_ns"] - bus0) / 1e9,
                    direction=f["direction"],
                    phase=f["phase"],
                    kind=ident >> 24,
                    arbitration_id_hex=f["arbitration_id_hex"],
                    payload_hex=f["data_hex"],
                    mode=(ident >> 22) & 3 if feedback else "",
                    q_rad=float(decode(w[0], 12.57) - result["fixed_zero_rad"]) if feedback else "",
                    v_rad_s=float(decode(w[1], 50)) if feedback else "",
                    torque_nm=float(decode(w[2], 5.5)) if feedback else "",
                )
            )
    med = median_filter(q, size=5, mode="nearest")
    peak_window = np.flatnonzero((t >= 6.1) & (t <= 7.8))
    peak_idx = int(peak_window[np.argmax(med[peak_window])])
    late = (t >= 18) & (t <= 20)
    stopq = float(np.median(q[late]))
    raw_recoil = float(med[peak_idx] - stopq)
    p_q = np.asarray([e["position"] for e in data["entries"]])
    p_med = median_filter(p_q, size=5, mode="nearest")
    p_recoil = float(
        np.max(p_med[(pt >= 6.1) & (pt <= 7.8)]) - np.median(p_q[(pt >= 18) & (pt <= 20)])
    )
    parameter_rx = [f for f in frames if f["direction"] == "rx" and frame_data(f)[0] >> 24 == 17]
    iq = [f for f in parameter_rx if f["data_hex"].startswith("1a700000")]
    assert len(iq) == 1
    iq_time = (int(iq[0]["host_monotonic_ns"]) - ns[0]) / 1e9
    iq_value = struct.unpack("<f", bytes.fromhex(iq[0]["data_hex"])[4:])[0]
    bins = []
    for phase, a, b in [
        ("active", 2.0, 5.9),
        ("free_swing", 6.05, 6.35),
        ("recoil", 6.4, 7.0),
        ("late", 18.0, 19.9),
    ]:
        for start, end, qdot, mean_v in velocity_bins(t, q, v, a, b):
            bins.append(
                dict(
                    id=row["id"],
                    mass_g=row["mass_g"],
                    phase=phase,
                    start_s=float(start),
                    end_s=float(end),
                    q_interval_velocity=float(qdot),
                    mean_reported_velocity=float(mean_v),
                    difference=float(mean_v - qdot),
                )
            )
    late_integral = float(np.trapezoid(v[late], t[late]))
    summary = dict(
        id=row["id"],
        mass_g=row["mass_g"],
        repeat=row["repeat"],
        kp=row["kp"],
        kd=row["kd"],
        stop_host_s=float(tstop),
        stop_bus_s=(stop["bus_ns"] - bus0) / 1e9,
        stop_ack1_host_ms=(int(ack[0]["host_monotonic_ns"]) - stop_ns) / 1e6,
        stop_ack1_bus_ms=(ack[0]["bus_ns"] - stop["bus_ns"]) / 1e6,
        stop_ack2_bus_ms=(ack[1]["bus_ns"] - stop["bus_ns"]) / 1e6,
        ack1_torque_nm=float(decode(frame_data(ack[0])[1][2], 5.5)),
        ack2_torque_nm=float(decode(frame_data(ack[1])[1][2], 5.5)),
        first_poll_host_s=float(t[idx]),
        first_poll_bus_s=float(bus_t[idx]),
        first_poll_speed=float(v[idx]),
        first_poll_interval_ms=float((t[idx + 1] - t[idx]) * 1000),
        sample_gap_ms=float((t[idx] - t[idx - 1]) * 1000),
        processed_first_disabled_s=float(pt[np.flatnonzero(~pa)[0]]),
        processed_disable_minus_stop_ms=float((pt[np.flatnonzero(~pa)[0]] - tstop) * 1000),
        post_stop_control_or_enable_count=sum(k in (1, 3) for k in kinds),
        released_samples=len(samples) - idx,
        released_torque_word_min=int(words[idx:, 2].min()),
        released_torque_word_max=int(words[idx:, 2].max()),
        released_mode_faults_all_zero=True,
        in_motion_iq_reads=sum(ns[0] <= int(f["host_monotonic_ns"]) <= ns[-1] for f in iq),
        final_iq_time_s=float(iq_time),
        final_iq_a=iq_value,
        raw_median5_peak_s=float(t[peak_idx]),
        peak_minus_stop_command_s=float(t[peak_idx] - tstop),
        raw_recoil_mrad=raw_recoil * 1000,
        raw_peak_to_stop_counts=float(
            np.max(median_filter(words[:, 0], size=5)[peak_window]) - np.median(words[late, 0])
        ),
        raw_unfiltered_recoil_mrad=float((np.max(q[peak_window]) - stopq) * 1000),
        processed_recoil_mrad=p_recoil * 1000,
        late_q_range_mrad=float(np.ptp(q[late]) * 1000),
        late_v_min=float(np.min(v[late])),
        late_v_max=float(np.max(v[late])),
        late_v_rms=float(np.sqrt(np.mean(v[late] ** 2))),
        late_v_median=float(np.median(v[late])),
        late_integrated_v_mrad=late_integral * 1000,
        late_q_net_mrad=float((q[late][-1] - q[late][0]) * 1000),
        raw_stop_q_mrad=stopq * 1000,
    )
    np.savez_compressed(
        root / "analysis" / "raw-probes" / f"{row['id']}.npz",
        t=t,
        bus_t=bus_t,
        q=q,
        v=v,
        torque=torque,
        words=words,
        active=active,
        median5_q=med,
        processed_t=pt,
        processed_q=p_q,
        processed_active=pa,
    )
    return check, summary, events, bins


def plots(root, summaries, events):
    out = root / "analysis"
    d = np.load(out / "raw-probes" / f"{REP}.npz")
    rep = next(r for r in summaries if r["id"] == REP)
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 10})
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True, layout="constrained")
    for ax, key, scale, label in zip(
        axes,
        ["q", "v", "torque"],
        [1000, 1, 1],
        ["Position (mrad)", "Speed (rad/s)", "Nominal torque (Nm)"],
    ):
        mask = (d["t"] > 5.97) & (d["t"] < 6.081)
        ax.plot(
            d["t"][mask],
            d[key][mask] * scale,
            "o",
            ms=4,
            label="Raw sampled feedback",
            color="#237b83",
        )
        for n, e in enumerate(
            [
                e
                for e in events
                if e["id"] == REP and e["direction"] == "rx" and e["phase"] == "cleanup"
            ]
        ):
            field = {"q": "q_rad", "v": "v_rad_s", "torque": "torque_nm"}[key]
            ax.scatter(
                e["host_time_s"],
                e[field] * scale,
                marker="x",
                color="#bd5d2a",
                s=70,
                label="STOP / mode-write replies" if n == 0 else None,
            )
        ax.axvline(rep["stop_host_s"], color="#444444", ls="--", label="STOP command")
        ax.axvline(
            rep["processed_first_disabled_s"],
            color="#8b6aaf",
            ls=":",
            label="Processed enable flag becomes false",
        )
        ax.set(ylabel=label, xlim=(5.975, 6.08))
        ax.axvspan(d["t"][599], d["t"][600], alpha=0.06, color="#777777")
        ax.grid(alpha=0.2)
    axes[0].legend(fontsize=8, loc="upper left")
    axes[-1].set_xlabel("Host receive time since first sample (s)")
    fig.suptitle("200 g, repeat 3, kp=20: the release transition has a 35 ms sample gap")
    fig.savefig(out / "disable-transition.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
    for ax in axes[0]:
        ax.plot(d["t"], d["q"] * 1000, color="#9cbcc0", label="Raw decoded CAN position")
        ax.plot(
            d["t"], d["median5_q"] * 1000, color="#216a78", lw=1.7, label="Median of 5 raw samples"
        )
        ax.plot(
            d["processed_t"],
            d["processed_q"] * 1000,
            color="#d37a35",
            ls="--",
            lw=1,
            label="Processed position",
        )
        ax.set(ylabel="Position (mrad)", xlabel="Time (s)")
    axes[0, 0].set(
        xlim=(6.3, 6.8), ylim=(16, 26), title="The retreat is already present on the CAN bus"
    )
    axes[0, 1].set(
        xlim=(18, 20), ylim=(20.9, 22), title="Late position changes within one CAN count"
    )
    axes[0, 0].legend(fontsize=8)
    axes[1, 0].plot(d["t"], d["v"], color="#28687d", lw=0.9)
    axes[1, 0].set(
        xlim=(18, 20),
        ylim=(-0.14, 0.14),
        xlabel="Time (s)",
        ylabel="Reported speed (rad/s)",
        title="Late speed is not a clean position derivative",
    )
    small_loads = [r for r in summaries if r["mass_g"] < 500]
    x = np.arange(len(small_loads))
    axes[1, 1].bar(
        x,
        [r["raw_recoil_mrad"] for r in small_loads],
        color=[{100: "#327b8d", 200: "#d07831"}[r["mass_g"]] for r in small_loads],
    )
    axes[1, 1].set(
        xticks=[4, 13],
        xticklabels=["100 g", "200 g"],
        ylabel="Raw peak-to-stop retreat (mrad)",
        title="Small retreat: all 18 records at 100 g and 200 g",
    )
    for ax in axes.ravel():
        ax.grid(alpha=0.15)
    fig.savefig(out / "feedback-and-retreat.png", dpi=180)
    plt.close(fig)


def main(argv=None):
    from motorfit.dataset import Dataset

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    dataset = Dataset(args.dataset)
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    (root / "analysis/raw-probes").mkdir(parents=True)
    checks, summaries, events, bins, inputs = [], [], [], [], {}
    for row in dataset.rows:
        check, summary, ev, vb = analyze_record(row, root, inputs, dataset)
        checks.append(check)
        if summary:
            summaries.append(summary)
        events.extend(ev)
        bins.extend(vb)
    for name, values in [
        ("all-record-audit", checks),
        ("release-summary", summaries),
        ("transition-frames", events),
        ("velocity-intervals", bins),
    ]:
        if values:
            csv_write(root / "analysis" / (name + ".csv"), values)
    result = {
        "records": len(checks),
        "samples": sum(r["samples"] for r in checks),
        "release_records": len(summaries),
        "all_source_hashes_match": True,
        "maximum_resampling_error": max(r["resampling_max_error"] for r in checks),
    }
    save(root / "summary.json", result)
    if any(r["id"] == REP for r in summaries):
        plots(root, summaries, events)
    if (dataset.root / "snapshots").exists():
        from .stationary import audit_stationary

        audit_stationary(dataset, root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
