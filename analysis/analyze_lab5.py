"""Аналіз ЛР5: таблиці 1-6 за JSON-файлами прогонів у results/lab5/."""
import argparse
import glob
import json
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(d, cfg):
    runs = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(d, f"{cfg}_run*.json")))]
    x1 = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(d, f"{cfg}_x1_*.json")))]
    cs = {r: [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(d, f"{cfg}_cs_{r}_*.json")))] for r in "wr"}
    if not runs or not x1 or not cs["w"] or not cs["r"]:
        raise SystemExit(f"для {cfg} бракує файлів у {d}")
    order = sorted(runs, key=lambda r: r["roles"]["all"]["X"])
    med = order[len(order) // 2]
    t_w = statistics.median(c["t_cs_us"] for c in cs["w"])
    t_r = statistics.median(c["t_cs_us"] for c in cs["r"])
    n, n_w, n_r = med["meta"]["n"], med["meta"]["n_w"], med["meta"]["n_r"]
    tbar = (n_w * t_w + n_r * t_r) / n
    return {
        "name": cfg, "med": med, "runs": runs,
        "X_range": (min(r["roles"]["all"]["X"] for r in runs), max(r["roles"]["all"]["X"] for r in runs)),
        "X1": statistics.median(c["X1"] for c in x1),
        "t_cs_w_us": t_w, "t_cs_r_us": t_r, "t_cs_bar_us": tbar,
        "limit_ops": 1e6 / tbar,
        "ok": all(r["invariants_ok"] for r in runs) and all(c["invariants_ok"] for c in x1),
    }


def fmt(x, k=1):
    return f"{x:,.{k}f}".replace(",", " ").replace(".", ",")


def ratio(rw, g, digits=3):
    if g == 0:
        return f"{fmt(rw - g, digits)} (різниця RW − G)"
    return fmt(rw / g, digits)


def tables(G, RW):
    mg, mr = G["med"], RW["med"]
    n, n_w, n_r = mg["meta"]["n"], mg["meta"]["n_w"], mg["meta"]["n_r"]
    out = []
    meta = mg["meta"]
    out.append("Таблиця 1. Стенд")
    out.append(f"n = {n}, n_w = {n_w}, n_r = {n_r}; {meta['implementation']} {meta['python']}, GIL "
               f"{'увімкнено' if meta['gil_enabled'] else 'вимкнено'}; логічних ядер {meta['logical_cores']}; "
               f"X_1 = {fmt(G['X1'], 0)} (глобальний замок) / {fmt(RW['X1'], 0)} ({RW['name']}) оп/с; "
               f"інваріанти: {'виконано' if G['ok'] and RW['ok'] else 'ПОРУШЕНО'}")
    out.append("")
    for title, c in (("Таблиця 2. Глобальний замок", G), ("Таблиця 3. RWLock (політика " + RW["name"].split("-")[1] + ")", RW)):
        m = c["med"]["roles"]
        out.append(title)
        out.append("| Роль | Операцій за D | X, оп/с | p50, мкс | p99, мкс | Найбільший t_wait, мс | w | cv |" + (" t_cs, мкс |" if c is G else ""))
        out.append("|---|---|---|---|---|---|---|---|" + ("---|" if c is G else ""))
        for key, name, t in (("write", "Запис", c["t_cs_w_us"]), ("read", "Читання", c["t_cs_r_us"]), ("all", "Разом", c["t_cs_bar_us"])):
            r = m[key]
            row = f"| {name} | {r['ops']} | {fmt(r['X'], 0)} | {fmt(r['p50_us'], 2)} | {fmt(r['p99_us'], 2)} | {fmt(r['wait_max_ms'], 2)} | {fmt(r['w'], 3)} | {fmt(r['cv'], 3)} |"
            if c is G:
                row += f" {fmt(t, 3)} |"
            out.append(row)
        if c is G:
            out.append(f"t_cs,w = {fmt(G['t_cs_w_us'], 3)} мкс, t_cs,r = {fmt(G['t_cs_r_us'], 3)} мкс; "
                       f"t̄_cs = ({n_w}·{fmt(G['t_cs_w_us'], 3)} + {n_r}·{fmt(G['t_cs_r_us'], 3)}) / {n} = {fmt(G['t_cs_bar_us'], 3)} мкс; "
                       f"1 / t̄_cs = {fmt(G['limit_ops'], 0)} оп/с")
        out.append("")
    out.append("Таблиця 4. Операції потоків за D секунд")
    out.append("| Потік | Роль | Глобальний замок | RWLock |")
    out.append("|---|---|---|---|")
    for tg, tr in zip(mg["threads"], mr["threads"]):
        out.append(f"| {tg['id']} | {tg['role']} | {tg['ops']} | {tr['ops']} |")
    out.append("")
    Xg, Xr_ = mg["roles"]["all"]["X"], mr["roles"]["all"]["X"]
    Sg, Srw = Xg / G["X1"], Xr_ / RW["X1"]
    Sw = mr["roles"]["write"]["X"] / mg["roles"]["write"]["X"]
    Sr = mr["roles"]["read"]["X"] / mg["roles"]["read"]["X"]
    rho = Xg * G["t_cs_bar_us"] / 1e6
    out.append("Таблиця 5. Метрики прискорення")
    out.append("| Метрика | Формула з числами | Значення |")
    out.append("|---|---|---|")
    out.append(f"| S(n), глобальний замок | {fmt(Xg, 0)} / {fmt(G['X1'], 0)} | {fmt(Sg, 3)} |")
    out.append(f"| E(n), глобальний замок | {fmt(Sg, 3)} / {n} | {fmt(Sg / n, 3)} |")
    out.append(f"| S(n), RWLock | {fmt(Xr_, 0)} / {fmt(RW['X1'], 0)} | {fmt(Srw, 3)} |")
    out.append(f"| E(n), RWLock | {fmt(Srw, 3)} / {n} | {fmt(Srw / n, 3)} |")
    out.append(f"| S_w | {fmt(mr['roles']['write']['X'], 0)} / {fmt(mg['roles']['write']['X'], 0)} | {fmt(Sw, 3)} |")
    out.append(f"| S_r | {fmt(mr['roles']['read']['X'], 0)} / {fmt(mg['roles']['read']['X'], 0)} | {fmt(Sr, 3)} |")
    out.append(f"| S_Σ | {fmt(Xr_, 0)} / {fmt(Xg, 0)} | {fmt(Xr_ / Xg, 3)} |")
    out.append(f"| ρ, завантаженість глобального замка | {fmt(Xg, 0)} · {fmt(G['t_cs_bar_us'], 3)}·10⁻⁶ | {fmt(rho, 3)} |")
    out.append(f"X(G) = {fmt(Xg, 0)} оп/с проти межі 1 / t̄_cs = {fmt(G['limit_ops'], 0)} оп/с: X(G) становить {fmt(100 * Xg / G['limit_ops'], 1)} % межі.")
    out.append("")
    out.append("Таблиця 6. Порівняння доступу до даних")
    out.append("| Показник | G: запис | G: читання | RW: запис | RW: читання | RW/G: запис | RW/G: читання |")
    out.append("|---|---|---|---|---|---|---|")
    rows = [("X, оп/с", "X", 0), ("x, на один потік ролі, оп/с", "x", 0), ("p50, мкс", "p50_us", 2), ("p99, мкс", "p99_us", 2),
            ("h = p99 / p50", None, 2), ("Найбільший t_wait, мс", "wait_max_ms", 2), ("w", "w", 3), ("cv", "cv", 3),
            ("φ, частка ролі в усіх операціях", "phi", 3)]
    for label, key, d in rows:
        vals = []
        for c in (mg, mr):
            for role in ("write", "read"):
                r = c["roles"][role]
                vals.append(r["p99_us"] / r["p50_us"] if key is None and r["p50_us"] else (r[key] if key else 0.0))
        out.append(f"| {label} | " + " | ".join(fmt(v, d) for v in vals) + f" | {ratio(vals[2], vals[0])} | {ratio(vals[3], vals[1])} |")
    out.append("")
    out.append(f"Розкид X між трьома прогонами (мін–макс, оп/с): G {fmt(G['X_range'][0], 0)}–{fmt(G['X_range'][1], 0)}; "
               f"{RW['name']} {fmt(RW['X_range'][0], 0)}–{fmt(RW['X_range'][1], 0)}.")
    return "\n".join(out)


def figures(G, RW, d):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    labels = ["запис", "читання", "разом"]
    xs = range(3)
    for off, c, lab in ((-0.2, G, "глобальний замок"), (0.2, RW, RW["name"])):
        vals = [c["med"]["roles"][k]["X"] for k in ("write", "read", "all")]
        ax[0].bar([x + off for x in xs], vals, 0.4, label=lab)
    ax[0].set_xticks(list(xs)); ax[0].set_xticklabels(labels); ax[0].set_ylabel("X, оп/с"); ax[0].set_title("Швидкість доступу за ролями"); ax[0].legend()
    for off, c, lab in ((-0.2, G, "глобальний замок"), (0.2, RW, RW["name"])):
        ax[1].bar([t["id"] + off for t in c["med"]["threads"]], [t["ops"] for t in c["med"]["threads"]], 0.4, label=lab)
    ax[1].set_xlabel("номер потоку"); ax[1].set_ylabel("операцій за D"); ax[1].set_title("Операції потоків"); ax[1].set_xticks([t["id"] for t in G["med"]["threads"]])
    fig.savefig(os.path.join(d, "lab5_summary.png"), dpi=150)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=os.path.join(ROOT, "results", "lab5"))
    p.add_argument("--rw", default="rw-writer", help="rw-writer або rw-reader")
    a = p.parse_args()
    G, RW = load(a.dir, "global"), load(a.dir, a.rw)
    text = tables(G, RW)
    with open(os.path.join(a.dir, f"analysis_lab5_{a.rw}.md"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    figures(G, RW, a.dir)
    print(text)


if __name__ == "__main__":
    main()
