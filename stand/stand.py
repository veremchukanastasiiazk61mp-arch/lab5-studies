"""Стенд ЛР5: потоки записують (непарні номери) і читають (парні) структуру С5.

Режими:
  run  n потоків, вимір D секунд після прогріву, JSON з метриками
  x1   один потік по черзі пише і читає в пропорції n_w : n_r (для X_1)
  cs   один потік виконує лише один вид операцій, вимірюється час утримання замка t_cs
"""
import argparse
import gc
import json
import math
import os
import platform
import random
import sys
import threading
import time
from array import array

from stand.aggregator import Aggregator, BUCKETS
from stand.rwlock import RWLock

pc = time.perf_counter_ns


def make_lock(kind, policy):
    """Повертає (acq_w, rel_w, acq_r, rel_r)."""
    if kind == "global":
        lk = threading.Lock()
        return lk.acquire, lk.release, lk.acquire, lk.release
    rw = RWLock(policy)
    return rw.acquire_write, rw.release_write, rw.acquire_read, rw.release_read


def percentile(sorted_vals, q):
    """p_q = tau_(ceil(q * N)) для впорядкованого за зростанням списку."""
    n = len(sorted_vals)
    if n == 0:
        return 0
    return sorted_vals[max(1, math.ceil(q * n)) - 1]


def to_sorted(arrays):
    try:
        import numpy as np
        parts = [np.frombuffer(a, dtype=np.int64) for a in arrays if len(a)]
        if not parts:
            return []
        return np.sort(np.concatenate(parts)).tolist()
    except ImportError:
        merged = []
        for a in arrays:
            merged.extend(a)
        merged.sort()
        return merged


def worker(pattern, acq_w, rel_w, acq_r, rel_r, agg, start_ns, end_ns, seed, barrier, out):
    """Цикл потоку. pattern: 'w' для писця, 'r' для читача, 'wwr' для режиму x1."""
    rnd = random.Random(seed).random
    st = {k: {"taus": array("q"), "ops": 0, "wait_sum": 0, "wait_max": 0, "total": 0} for k in "wr"}
    bad_snapshots = 0
    plen = len(pattern)
    i = 0
    barrier.wait()
    while True:
        kind = pattern[i]
        i += 1
        if i == plen:
            i = 0
        s = st[kind]
        if kind == "w":
            v = int(rnd() * BUCKETS)
            t_call = pc()
            acq_w()
            t_acq = pc()
            agg.add(v)
            rel_w()
            t_ret = pc()
        else:
            t_call = pc()
            acq_r()
            t_acq = pc()
            snap = agg.snapshot()
            rel_r()
            t_ret = pc()
            if sum(snap[0]) != snap[1]:
                bad_snapshots += 1
        s["total"] += 1
        if t_call >= start_ns:
            if t_ret > end_ns:
                # Остання операція не вмістилась у вікно: у вікні враховується лише частина очікування.
                w = min(t_acq, end_ns) - t_call
                if w > 0:
                    s["wait_sum"] += w
                    if w > s["wait_max"]:
                        s["wait_max"] = w
                break
            w = t_acq - t_call
            s["taus"].append(t_ret - t_call)
            s["wait_sum"] += w
            if w > s["wait_max"]:
                s["wait_max"] = w
            s["ops"] += 1
    out["stats"] = st
    out["bad_snapshots"] = bad_snapshots


def run_threads(kind, policy, patterns, duration, warmup, seed):
    acq_w, rel_w, acq_r, rel_r = make_lock(kind, policy)
    agg = Aggregator()
    barrier = threading.Barrier(len(patterns) + 1)
    outs = [{} for _ in patterns]
    threads = []
    gc.collect()
    gc.disable()
    # Вікно виміру задається до старту потоків: всі потоки мають одну й ту саму межу.
    t0 = pc() + 200_000_000
    start_ns = t0 + int(warmup * 1e9)
    end_ns = start_ns + int(duration * 1e9)
    for idx, pat in enumerate(patterns):
        th = threading.Thread(target=worker, args=(pat, acq_w, rel_w, acq_r, rel_r, agg, start_ns, end_ns,
                                                    seed * 1000 + idx, barrier, outs[idx]))
        threads.append(th)
        th.start()
    barrier.wait()
    for th in threads:
        th.join()
    gc.enable()
    return agg, outs


def cv_of(counts):
    k = len(counts)
    if k == 0:
        return 0.0
    mu = sum(counts) / k
    if mu == 0:
        return 0.0
    sigma = math.sqrt(sum((c - mu) ** 2 for c in counts) / k)
    return sigma / mu


def summarize(kind, policy, n, duration, warmup, agg, outs, patterns):
    n_w = math.ceil(n / 2)
    n_r = n // 2
    roles = {}
    per_thread = []
    total_adds = 0
    for idx, (pat, o) in enumerate(zip(patterns, outs)):
        role = pat[0]
        s = o["stats"][role]
        per_thread.append({"id": idx + 1, "role": "запис" if role == "w" else "читання", "ops": s["ops"]})
        total_adds += o["stats"]["w"]["total"]
    for role, name, k in (("w", "write", n_w), ("r", "read", n_r)):
        taus = [o["stats"][role]["taus"] for pat, o in zip(patterns, outs) if pat[0] == role]
        ops_per_thread = [o["stats"][role]["ops"] for pat, o in zip(patterns, outs) if pat[0] == role]
        srt = to_sorted(taus)
        wait_sum = sum(o["stats"][role]["wait_sum"] for pat, o in zip(patterns, outs) if pat[0] == role)
        wait_max = max([o["stats"][role]["wait_max"] for pat, o in zip(patterns, outs) if pat[0] == role] or [0])
        N = sum(ops_per_thread)
        roles[name] = {
            "threads": k,
            "ops": N,
            "X": N / duration,
            "x": (N / duration / k) if k else 0.0,
            "p50_us": percentile(srt, 0.5) / 1e3,
            "p99_us": percentile(srt, 0.99) / 1e3,
            "wait_max_ms": wait_max / 1e6,
            "w": wait_sum / (k * duration * 1e9) if k else 0.0,
            "cv": cv_of(ops_per_thread),
            "ops_per_thread": ops_per_thread,
        }
    all_taus = [o["stats"][r]["taus"] for o in outs for r in "wr"]
    srt = to_sorted(all_taus)
    N_all = roles["write"]["ops"] + roles["read"]["ops"]
    all_wait_sum = sum(o["stats"][r]["wait_sum"] for o in outs for r in "wr")
    X_w, X_r = roles["write"]["X"], roles["read"]["X"]
    X = X_w + X_r
    roles["all"] = {
        "threads": n,
        "ops": N_all,
        "X": X,
        "p50_us": percentile(srt, 0.5) / 1e3,
        "p99_us": percentile(srt, 0.99) / 1e3,
        "wait_max_ms": max(roles["write"]["wait_max_ms"], roles["read"]["wait_max_ms"]),
        "w": all_wait_sum / (n * duration * 1e9),
        "cv": cv_of([t["ops"] for t in per_thread]),
    }
    roles["write"]["phi"] = X_w / X if X else 0.0
    roles["read"]["phi"] = X_r / X if X else 0.0
    bad = sum(o["bad_snapshots"] for o in outs)
    problems = agg.check(total_adds)
    if bad:
        problems.append(f"знімків з сумою кошиків != count: {bad}")
    return {
        "mode": "run",
        "meta": meta(kind, policy, n, n_w, n_r, duration, warmup),
        "threads": per_thread,
        "roles": roles,
        "invariants_ok": not problems,
        "invariant_problems": problems,
        "final_count": agg.count,
        "total_add_calls": total_adds,
    }


def meta(kind, policy, n, n_w, n_r, duration, warmup):
    gil = getattr(sys, "_is_gil_enabled", lambda: True)()
    return {
        "lock": kind if kind == "global" else f"rw-{policy}",
        "n": n, "n_w": n_w, "n_r": n_r,
        "duration_s": duration, "warmup_s": warmup,
        "structure": "C5", "buckets": BUCKETS,
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "gil_enabled": gil,
        "switch_interval_s": sys.getswitchinterval(),
        "logical_cores": os.cpu_count(),
        "platform": platform.platform(),
        "processor": platform.processor(),
    }


def mode_run(a):
    n_w, n_r = math.ceil(a.n / 2), a.n // 2
    patterns = ["w" if (i % 2 == 1) else "r" for i in range(1, a.n + 1)]
    agg, outs = run_threads(a.lock, a.rw_policy, patterns, a.duration, a.warmup, a.seed)
    res = summarize(a.lock, a.rw_policy, a.n, a.duration, a.warmup, agg, outs, patterns)
    return res


def mode_x1(a):
    n_w, n_r = math.ceil(a.n / 2), a.n // 2
    pattern = "w" * n_w + "r" * n_r
    agg, outs = run_threads(a.lock, a.rw_policy, [pattern], a.duration, a.warmup, a.seed)
    o = outs[0]
    ops_w, ops_r = o["stats"]["w"]["ops"], o["stats"]["r"]["ops"]
    problems = agg.check(o["stats"]["w"]["total"])
    if o["bad_snapshots"]:
        problems.append(f"знімків з сумою кошиків != count: {o['bad_snapshots']}")
    return {
        "mode": "x1",
        "meta": meta(a.lock, a.rw_policy, a.n, n_w, n_r, a.duration, a.warmup),
        "pattern": pattern,
        "ops_w": ops_w, "ops_r": ops_r,
        "X1": (ops_w + ops_r) / a.duration,
        "invariants_ok": not problems,
        "invariant_problems": problems,
    }


def mode_cs(a):
    """Середній час від отримання до звільнення замка в однопотоковому прогоні."""
    acq_w, rel_w, acq_r, rel_r = make_lock(a.lock, a.rw_policy)
    agg = Aggregator()
    rnd = random.Random(a.seed).random
    acq, rel = (acq_w, rel_w) if a.role == "w" else (acq_r, rel_r)
    gc.collect()
    gc.disable()
    t_start = pc()
    t_meas = t_start + int(a.warmup * 1e9)
    t_end = t_meas + int(a.duration * 1e9)
    hold_sum = 0
    ops = 0
    while True:
        v = int(rnd() * BUCKETS)
        acq()
        t_acq = pc()
        if a.role == "w":
            agg.add(v)
        else:
            agg.snapshot()
        t_rel = pc()
        rel()
        if t_acq >= t_meas:
            hold_sum += t_rel - t_acq
            ops += 1
        if t_rel >= t_end:
            break
    gc.enable()
    return {
        "mode": "cs",
        "meta": meta(a.lock, a.rw_policy, 1, 1, 0, a.duration, a.warmup),
        "role": a.role,
        "ops": ops,
        "t_cs_us": hold_sum / ops / 1e3 if ops else 0.0,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["run", "x1", "cs"])
    p.add_argument("--lock", choices=["global", "rw"], required=True)
    p.add_argument("--rw-policy", choices=["writer", "reader"], default="writer")
    p.add_argument("--n", type=int, default=3)
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--warmup", type=float, default=1.0)
    p.add_argument("--role", choices=["w", "r"], default="w")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--out", default="")
    a = p.parse_args(argv)
    res = {"run": mode_run, "x1": mode_x1, "cs": mode_cs}[a.mode](a)
    text = json.dumps(res, ensure_ascii=False, indent=2)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    return res


if __name__ == "__main__":
    r = main()
    if r["mode"] == "run":
        ro = r["roles"]
        print(f"{r['meta']['lock']}: X_w={ro['write']['X']:.0f} X_r={ro['read']['X']:.0f} X={ro['all']['X']:.0f} "
              f"інваріанти={'ok' if r['invariants_ok'] else r['invariant_problems']}")
    elif r["mode"] == "x1":
        print(f"{r['meta']['lock']}: X_1={r['X1']:.0f} інваріанти={'ok' if r['invariants_ok'] else r['invariant_problems']}")
    else:
        print(f"{r['meta']['lock']} {r['role']}: t_cs={r['t_cs_us']:.3f} мкс")
