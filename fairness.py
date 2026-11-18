"""Testul de echitate: doua fluxuri prin acelasi router.

Primul flux porneste singur si ia toata legatura. Al doilea intra dupa
cateva secunde. Daca AIMD isi face treaba, cele doua ajung sa imparta
legatura cam in mod egal. Masuram asta cu indicele lui Jain:
  J = (x1 + x2)^2 / (2 * (x1^2 + x2^2))     1 = perfect egal, 0.5 = unul ia tot

  python3 fairness.py
  python3 fairness.py --mode tahoe --start2 3
"""

import argparse
import os
import socket
import threading
import time

from rdt.link import Link, Router
from rdt.receiver import Receiver
from rdt.sender import MODES, Sender


def udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    return s


def flow(name, mode, size_kb, start, router, clock, delay, out):
    time.sleep(start)
    s_sock, r_sock = udp(), udp()
    data_link = Link(s_sock, "data", delay, clock=clock, router=router)
    ack_link = Link(r_sock, "ack", delay, clock=clock)
    rx = Receiver(r_sock, ack_link, clock, linger=0.3)
    th = threading.Thread(target=rx.run, daemon=True)
    th.start()
    log = []
    tx = Sender(s_sock, data_link, r_sock.getsockname(), os.urandom(int(size_kb * 1024)),
                mode, clock=clock, log=log)
    tx.run()
    rx.stopped = True
    th.join(timeout=2)
    for x in (data_link, ack_link):
        x.close()
    out[name] = {"log": log, "trace": tx.trace, "ok": rx.data is not None}


def rate_per_bin(log, step, t_end):
    """Pachete confirmate pe secunda, pe intervale de `step` secunde."""
    bins = [0.0] * (int(t_end / step) + 1)
    last = 0
    for e in log:
        if e["ev"] == "ack" and e["seq"] > last:
            bins[int(e["t"] / step)] += e["seq"] - last
            last = e["seq"]
    return [b / step for b in bins]


def jain(x1, x2):
    return (x1 + x2) ** 2 / (2 * (x1 ** 2 + x2 ** 2)) if x1 + x2 else 0


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--mode", choices=MODES, default="reno")
    a.add_argument("--rate", type=float, default=200)
    a.add_argument("--queue", type=int, default=20)
    a.add_argument("--start2", type=float, default=4.0, help="cand porneste al doilea flux (s)")
    a.add_argument("--size1", type=float, default=2500)
    a.add_argument("--size2", type=float, default=1500)
    a.add_argument("--plot", default="referat/figuri/fig_echitate.png")
    o = a.parse_args()

    t0 = time.monotonic()
    clock = lambda: time.monotonic() - t0
    router = Router(o.rate, o.queue)        # acelasi router pentru amandoua
    out = {}
    th = [threading.Thread(target=flow, args=("flux 1", o.mode, o.size1, 0, router, clock, 0.04, out)),
          threading.Thread(target=flow, args=("flux 2", o.mode, o.size2, o.start2, router, clock, 0.04, out))]
    print(f"doua fluxuri {o.mode}, router de {o.rate:.0f} pachete/s, al doilea intra la {o.start2} s ...")
    for t in th:
        t.start()
    for t in th:
        t.join()

    step = 0.5
    t_end = clock()
    r1 = rate_per_bin(out["flux 1"]["log"], step, t_end)
    r2 = rate_per_bin(out["flux 2"]["log"], step, t_end)
    # perioada in care merg amandoua, fara prima secunda de dupa intrarea fluxului 2
    t_stop2 = max(e["t"] for e in out["flux 2"]["log"])
    t_stop1 = max(e["t"] for e in out["flux 1"]["log"])
    a_, b_ = int((o.start2 + 1) / step), int(min(t_stop1, t_stop2) / step)
    x1 = sum(r1[a_:b_]) / max(b_ - a_, 1)
    x2 = sum(r2[a_:b_]) / max(b_ - a_, 1)
    print(f"  fisiere primite corect: {out['flux 1']['ok']} / {out['flux 2']['ok']}")
    print(f"  cat timp merg amandoua: flux 1 = {x1:.0f} pachete/s, flux 2 = {x2:.0f} pachete/s")
    print(f"  indicele Jain = {jain(x1, x2):.3f}  (1 = impartire perfect egala)")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("(fara matplotlib nu desenez graficul)")
        return
    ts = [i * step for i in range(len(r1))]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 4.8), sharex=True)
    ax1.step(ts, r1, where="post", color="#2f6fdb", label="flux 1")
    ax1.step(ts, r2, where="post", color="#d23f31", label="flux 2")
    ax1.axhline(o.rate, color="#888", ls=":", lw=1)
    ax1.set_ylabel("pachete/s")
    ax1.set_title(f"Două fluxuri {o.mode.capitalize()} prin același router "
                  f"(indice Jain = {jain(x1, x2):.3f})", loc="left", fontsize=10)
    ax1.legend(fontsize=8)
    for n, c in (("flux 1", "#2f6fdb"), ("flux 2", "#d23f31")):
        tr = out[n]["trace"]
        ax2.step([x[0] for x in tr], [x[1] for x in tr], where="post", color=c, lw=1.2, label=n)
    ax2.set_ylabel("cwnd (pachete)")
    ax2.set_xlabel("timp (s)")
    for ax in (ax1, ax2):
        ax.grid(alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    os.makedirs(os.path.dirname(o.plot), exist_ok=True)
    fig.savefig(o.plot, dpi=150)
    print("  grafic salvat in", o.plot)


if __name__ == "__main__":
    main()
