"""Усі прогони ЛР5: для кожного способу синхронізації 3 прогони n потоків,
3 прогони X_1 і 3 прогони t_cs для запису та для читання. Кожен прогін у окремому процесі."""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def call(args, out):
    cmd = [sys.executable, "-m", "stand.stand"] + args + ["--out", out]
    print(" ".join(cmd[2:]), flush=True)
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode:
        sys.stderr.write(r.stderr)
        raise SystemExit(f"прогін завершився з помилкою: {out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=3)
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--warmup", type=float, default=1.0)
    p.add_argument("--cs-duration", type=float, default=3.0)
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--rw-policies", default="writer", help="через кому: writer,reader")
    p.add_argument("--out", default=os.path.join(ROOT, "results", "lab5"))
    a = p.parse_args()
    configs = [("global", "global", [])]
    for pol in a.rw_policies.split(","):
        configs.append((f"rw-{pol}", "rw", ["--rw-policy", pol]))
    for name, lock, extra in configs:
        base = ["--lock", lock] + extra
        for k in range(1, a.runs + 1):
            call(["run", "--n", str(a.n), "--duration", str(a.duration), "--warmup", str(a.warmup), "--seed", str(k)] + base,
                 os.path.join(a.out, f"{name}_run{k}.json"))
        for k in range(1, a.runs + 1):
            call(["x1", "--n", str(a.n), "--duration", str(a.duration), "--warmup", str(a.warmup), "--seed", str(k)] + base,
                 os.path.join(a.out, f"{name}_x1_{k}.json"))
        for role in ("w", "r"):
            for k in range(1, a.runs + 1):
                call(["cs", "--role", role, "--duration", str(a.cs_duration), "--warmup", "0.5", "--seed", str(k)] + base,
                     os.path.join(a.out, f"{name}_cs_{role}_{k}.json"))


if __name__ == "__main__":
    main()
