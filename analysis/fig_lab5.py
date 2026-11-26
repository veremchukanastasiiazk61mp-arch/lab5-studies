"""Діаграми ЛР5 за JSON-файлами прогонів у results/lab5/ (прогін із медіанним X для кожного способу синхронізації)."""
import argparse
import glob
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIGS = [("global", "глобальний замок", "#2a6fb0"), ("rw-writer", "RWLock, пріоритет писців", "#d9822b"),
           ("rw-reader", "RWLock, пріоритет читачів", "#7a7a7a")]


def median_run(d, cfg):
    runs = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(d, f"{cfg}_run*.json")))]
    return sorted(runs, key=lambda r: r["roles"]["all"]["X"])[len(runs) // 2] if runs else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=os.path.join(ROOT, "results", "lab5"))
    p.add_argument("--out", default="")
    a = p.parse_args()
    out = a.out or a.dir
    data = [(lab, col, median_run(a.dir, cfg)) for cfg, lab, col in CONFIGS]
    data = [x for x in data if x[2]]
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

    fig, ax = plt.subplots(figsize=(8, 4.2), constrained_layout=True)
    w = 0.8 / len(data)
    for i, (lab, col, r) in enumerate(data):
        vals = [r["roles"][k]["X"] / 1000 for k in ("write", "read", "all")]
        xs = [j + (i - (len(data) - 1) / 2) * w for j in range(3)]
        bars = ax.bar(xs, vals, w * 0.92, color=col, label=lab)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 8, f"{v:.0f}", ha="center", fontsize=8)
    ax.set_xticks(range(3)); ax.set_xticklabels(["запис X_w", "читання X_r", "разом X"])
    ax.set_ylabel("тисяч операцій за секунду"); ax.set_title("Швидкість доступу за ролями")
    ax.legend(frameon=False, loc="upper left")
    fig.savefig(os.path.join(out, "lab5_rates.png"), dpi=200); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.2), constrained_layout=True)
    for i, (lab, col, r) in enumerate(data):
        th = r["threads"]
        xs = [j + (i - (len(data) - 1) / 2) * w for j in range(len(th))]
        bars = ax.bar(xs, [t["ops"] / 1e6 for t in th], w * 0.92, color=col, label=lab)
        for b, t in zip(bars, th):
            ax.text(b.get_x() + b.get_width() / 2, t["ops"] / 1e6 + 0.04, f"{t['ops'] / 1e6:.2f}", ha="center", fontsize=8)
    ax.set_xticks(range(len(data[0][2]["threads"])))
    ax.set_xticklabels([f"потік {t['id']}\n({t['role']})" for t in data[0][2]["threads"]])
    ax.set_ylabel("мільйонів операцій за D"); ax.set_title("Операції окремих потоків")
    ax.set_ylim(0, max(t["ops"] for _, _, r in data for t in r["threads"]) / 1e6 * 1.3)
    ax.legend(frameon=False, loc="upper center", ncol=3, fontsize=8.5)
    fig.savefig(os.path.join(out, "lab5_threads.png"), dpi=200); plt.close(fig)
    print("збережено lab5_rates.png, lab5_threads.png у", out)


if __name__ == "__main__":
    main()
