"""Un singur transfer, din linia de comanda.

  python3 run.py --mode reno --size 500 --loss 0.02
  python3 run.py --mode gbn --window 10 --loss 0.05 --save rezultate/gbn.json
"""

import argparse
import json
import os

from rdt.sender import MODES
from rdt.session import DEFAULTS, run_transfer

NAMES = {"sw": "Stop-and-Wait", "gbn": "Go-Back-N", "sr": "Selective Repeat",
         "tahoe": "TCP Tahoe", "reno": "TCP Reno", "newreno": "TCP NewReno"}


def args():
    d = DEFAULTS
    a = argparse.ArgumentParser(description="Transfer fiabil peste UDP")
    a.add_argument("--mode", choices=MODES, default=d["mode"])
    a.add_argument("--size", type=float, default=d["size_kb"], help="KB de trimis")
    a.add_argument("--file", help="trimite un fisier adevarat in loc de date random")
    a.add_argument("--window", type=int, default=d["window"], help="fereastra pt gbn/sr")
    a.add_argument("--delay", type=float, default=d["delay_ms"], help="ms, intr-un sens")
    a.add_argument("--jitter", type=float, default=d["jitter_ms"])
    a.add_argument("--loss", type=float, default=d["loss"])
    a.add_argument("--ack-loss", type=float, default=d["ack_loss"])
    a.add_argument("--corrupt", type=float, default=d["corrupt"])
    a.add_argument("--rate", type=float, default=d["rate"], help="pachete/s, 0 = nelimitat")
    a.add_argument("--queue", type=int, default=d["queue"])
    a.add_argument("--seed", type=int, default=d["seed"])
    a.add_argument("--save", help="salveaza tot jurnalul intr-un JSON")
    return a.parse_args()


def main():
    o = args()
    data = open(o.file, "rb").read() if o.file else None
    print(f"{NAMES[o.mode]}: trimit {len(data) // 1024 if data else o.size:.0f} KB ...")
    r = run_transfer(mode=o.mode, size_kb=o.size, data=data, window=o.window,
                     delay_ms=o.delay, jitter_ms=o.jitter, loss=o.loss,
                     ack_loss=o.ack_loss, corrupt=o.corrupt, rate=o.rate,
                     queue=o.queue, seed=o.seed)
    s = r["stats"]
    if r["error"]:
        print("EROARE:", r["error"])
    print(f"  fisier primit corect : {'da' if r['ok'] else 'NU'}")
    print(f"  durata               : {s['duration']:.2f} s")
    print(f"  goodput              : {s['goodput_kbs']:.1f} KB/s")
    print(f"  pachete de date      : {s['packets']} (trimise in total {s['sent']})")
    print(f"  retransmisii         : {s['retx']}  (timeout: {s['timeouts']}, fast retransmit: {s['fast_retx']})")
    print(f"  pierdute pe drum     : {s['dropped_loss']} aleator, {s['dropped_queue']} coada plina")
    print(f"  SRTT / RTO la final  : {s['final_srtt'] * 1000:.0f} ms / {s['final_rto'] * 1000:.0f} ms")
    if o.save:
        os.makedirs(os.path.dirname(o.save) or ".", exist_ok=True)
        r["params"].pop("data", None)
        with open(o.save, "w") as f:
            json.dump(r, f)
        print("  jurnal salvat in", o.save)


if __name__ == "__main__":
    main()
