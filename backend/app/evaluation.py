"""Score the pipeline against hand-labelled ground truth (what a human saw in the video).

Ground-truth CSV (one row per interval, times in video seconds):
    start_sec,end_sec,table,state,guests
    0,95,T01,FREE,0
    95,1500,T01,OCCUPIED,3
    1500,1620,T01,NEEDS_CLEANING,0
`guests` is optional. Intervals not listed are simply not scored.
"""
from __future__ import annotations

import csv
from collections import defaultdict

STATES = ["FREE", "OCCUPIED", "NEEDS_CLEANING"]


def load_truth(path: str) -> list[dict]:
    rows = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            r = {k.strip().lower(): (v or "").strip() for k, v in r.items()}
            st = r["state"].upper().replace(" ", "_")
            if st not in STATES:
                raise ValueError(f"unknown state '{r['state']}' (use {', '.join(STATES)})")
            rows.append({"t0": float(r["start_sec"]), "t1": float(r["end_sec"]), "table": r["table"].upper(),
                         "state": st, "guests": int(r["guests"]) if r.get("guests") else None})
    return rows


def evaluate(samples: list[tuple[float, dict]], truth: list[dict], grace: float = 10.0) -> dict:
    """samples: [(video_t, {table: (state, guests)})]. Frames within `grace` s of a truth boundary are ignored
    because the state machine deliberately confirms changes after a few seconds."""
    conf = {a: defaultdict(int) for a in STATES}
    guest_err: list[int] = []
    per_table: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_table: dict[str, list[dict]] = defaultdict(list)
    for r in truth:
        by_table[r["table"]].append(r)
    for t, snap in samples:
        for tid, (state, guests) in snap.items():
            for r in by_table.get(tid, []):
                if r["t0"] + grace <= t <= r["t1"] - grace:
                    conf[r["state"]][state] += 1
                    per_table[tid][0] += state == r["state"]
                    per_table[tid][1] += 1
                    if r["state"] == "OCCUPIED" and r["guests"] is not None and state == "OCCUPIED":
                        guest_err.append(abs(guests - r["guests"]))
                    break
    n = sum(sum(c.values()) for c in conf.values())
    ok = sum(conf[a][a] for a in STATES)
    cls = {}
    for a in STATES:
        tp = conf[a][a]
        fn = sum(conf[a].values()) - tp
        fp = sum(conf[b][a] for b in STATES if b != a)
        p = tp / (tp + fp) if tp + fp else None
        r_ = tp / (tp + fn) if tp + fn else None
        cls[a] = {"precision": None if p is None else round(p, 3), "recall": None if r_ is None else round(r_, 3),
                  "support": tp + fn}

    # how late does the system notice a table filling / being left?
    delays, missed = [], 0
    for r in truth:
        if r["state"] != "OCCUPIED":
            continue
        seen = next((t for t, snap in samples if t >= r["t0"] - grace and r["table"] in snap
                     and snap[r["table"]][0] == "OCCUPIED"), None)
        if seen is None or seen > r["t1"]:
            missed += 1
        else:
            delays.append(round(max(0.0, seen - r["t0"]), 1))
    return {
        "frames_scored": n,
        "state_accuracy": round(ok / n, 3) if n else None,
        "per_class": cls,
        "confusion": {a: dict(conf[a]) for a in STATES},
        "per_table_accuracy": {k: round(v[0] / v[1], 3) for k, v in sorted(per_table.items()) if v[1]},
        "guest_count_mae": round(sum(guest_err) / len(guest_err), 2) if guest_err else None,
        "guest_count_exact": round(sum(1 for e in guest_err if e == 0) / len(guest_err), 3) if guest_err else None,
        "seat_detect_delay_sec": {"mean": round(sum(delays) / len(delays), 1) if delays else None,
                                  "max": max(delays) if delays else None, "missed_parties": missed},
    }


def format_report(m: dict) -> str:
    L = ["ACCURACY vs ground truth",
         f"  frames scored: {m['frames_scored']}   state accuracy: {m['state_accuracy']}",
         f"  guest count: mean abs error {m['guest_count_mae']}, exact {m['guest_count_exact']}",
         f"  seat-detect delay: {m['seat_detect_delay_sec']}"]
    for k, v in m["per_class"].items():
        L.append(f"  {k:15s} precision {v['precision']}  recall {v['recall']}  (n={v['support']})")
    L.append("  per table: " + ", ".join(f"{k} {v}" for k, v in m["per_table_accuracy"].items()))
    return "\n".join(L)
