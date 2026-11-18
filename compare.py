"""Ruleaza toate protocoalele la mai multe rate de pierdere si scrie un CSV.

  python3 compare.py                 # varianta rapida
  python3 compare.py --runs 5        # mai multe repetari, medii mai stabile

Fiecare punct e media a --runs transferuri cu seed-uri diferite.
"""

import argparse
import csv
import os

from rdt.session import run_transfer

MODES = ["sw", "gbn", "sr", "tahoe", "reno", "newreno"]
LOSSES = [0.0, 0.01, 0.02, 0.05, 0.10]


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--runs", type=int, default=3)
    a.add_argument("--size", type=float, default=150)
    a.add_argument("--out", default="rezultate/comparatie.csv")
    o = a.parse_args()

    os.makedirs(os.path.dirname(o.out), exist_ok=True)
    rows = []
    for mode in MODES:
        for loss in LOSSES:
            acc = {"goodput_kbs": 0, "duration": 0, "retx": 0, "timeouts": 0,
                   "efficiency": 0}
            for k in range(o.runs):
                # stop-and-wait e lent, ii dam un fisier mai mic
                size = o.size / 5 if mode == "sw" else o.size
                r = run_transfer(mode=mode, size_kb=size, loss=loss,
                                 ack_loss=loss / 2, seed=100 + k)
                if not r["ok"]:
                    print("  !! transfer esuat:", mode, loss, r["error"])
                for key in acc:
                    acc[key] += r["stats"][key]
            row = {"mode": mode, "loss": loss}
            row.update({k: round(v / o.runs, 4) for k, v in acc.items()})
            rows.append(row)
            print(f"{mode:8} p={loss:<5} goodput={row['goodput_kbs']:7.1f} KB/s"
                  f"  retx={row['retx']:6.1f}  timeout={row['timeouts']:5.1f}")

    with open(o.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("scris in", o.out)


if __name__ == "__main__":
    main()
