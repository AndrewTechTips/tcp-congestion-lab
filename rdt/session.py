"""Porneste expeditorul si receptorul in acelasi proces, pe localhost,
si strange tot ce s-a intamplat intr-un singur dictionar (pt. grafice)."""

import hashlib
import os
import socket
import threading
import time

from .link import Link
from .receiver import Receiver
from .sender import Sender, TransferError

DEFAULTS = {
    "mode": "reno",
    "size_kb": 300,       # cat de mare e fisierul trimis
    "window": 8,          # pt. gbn / sr
    "rwnd": 64,
    "delay_ms": 40,       # intr-un sens, deci RTT ~ 80 ms
    "jitter_ms": 0,
    "loss": 0.0,          # pierdere aleatoare pe calea de date
    "ack_loss": 0.0,      # pierdere pe calea ACK-urilor
    "corrupt": 0.0,
    "rate": 200,          # pachete/s la router (0 = fara limita)
    "queue": 12,          # locuri in coada routerului
    "seed": 1,
    "data": None,         # optional, bytes de trimis in loc de date random
}


def _udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    return s


def run_transfer(**kw):
    p = dict(DEFAULTS)
    p.update({k: v for k, v in kw.items() if v is not None})

    data = p.pop("data")
    if data is None:
        data = os.urandom(int(p["size_kb"] * 1024))

    t0 = time.monotonic()
    clock = lambda: time.monotonic() - t0
    wire = []                      # tot ce trece pe fir, din ambele sensuri
    s_log, r_log = [], []

    s_sock, r_sock = _udp(), _udp()
    rate = p["rate"] or None
    data_link = Link(s_sock, "data", p["delay_ms"] / 1000, p["jitter_ms"] / 1000,
                     p["loss"], p["corrupt"], rate, p["queue"] if rate else None,
                     p["seed"], clock, wire)
    ack_link = Link(r_sock, "ack", p["delay_ms"] / 1000, p["jitter_ms"] / 1000,
                    p["ack_loss"], 0.0, None, None,
                    (p["seed"] or 0) + 1000, clock, wire)

    rx = Receiver(r_sock, ack_link, clock, r_log, linger=0.3)
    rx_thread = threading.Thread(target=rx.run, daemon=True)
    rx_thread.start()

    tx = Sender(s_sock, data_link, r_sock.getsockname(), data, p["mode"],
                p["window"], p["rwnd"], clock, s_log)
    error = None
    times = {}
    try:
        times = tx.run()
    except TransferError as e:
        error = str(e)

    rx.stopped = True
    rx_thread.join(timeout=2)
    data_link.close()
    ack_link.close()
    s_sock.close()
    r_sock.close()

    received = rx.data or b""
    ok = hashlib.sha256(received).digest() == hashlib.sha256(data).digest()
    duration = (times.get("t_end", clock()) - times.get("t_data", 0)) or 1e-9

    stats = dict(tx.stats)
    stats.update({
        "packets": tx.n,
        "bytes": len(data),
        "duration": round(duration, 4),
        "goodput_kbs": round(len(data) / 1024 / duration, 2),
        "efficiency": round(tx.n / stats["sent"], 4) if stats["sent"] else 0,
        "dropped_queue": sum(1 for w in wire if w["drop"] == "queue"),
        "dropped_loss": sum(1 for w in wire if w["drop"] == "loss"),
        "corrupted": sum(1 for w in wire if w.get("corrupt")),
        "final_srtt": round(tx.rtt.srtt or 0, 5),
        "final_rto": round(tx.rtt.rto, 5),
        "sha256": hashlib.sha256(data).hexdigest(),
    })

    return {
        "params": p,
        "ok": ok and error is None,
        "error": error,
        "times": times,
        "stats": stats,
        "trace": tx.trace,
        "sender": s_log,
        "receiver": r_log,
        "wire": wire,
    }
