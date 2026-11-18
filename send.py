"""Expeditorul ca proces separat. Se porneste dupa recv.py.

  python3 send.py poza.jpg --mode reno --loss 0.03
"""

import argparse
import hashlib
import socket
import time

from rdt.link import Link
from rdt.sender import MODES, Sender


def main():
    a = argparse.ArgumentParser()
    a.add_argument("file")
    a.add_argument("--host", default="127.0.0.1")
    a.add_argument("--port", type=int, default=9000)
    a.add_argument("--mode", choices=MODES, default="reno")
    a.add_argument("--window", type=int, default=8)
    a.add_argument("--delay", type=float, default=40)
    a.add_argument("--loss", type=float, default=0.0)
    a.add_argument("--rate", type=float, default=200)
    a.add_argument("--queue", type=int, default=12)
    o = a.parse_args()

    data = open(o.file, "rb").read()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    link = Link(sock, "data", o.delay / 1000, loss=o.loss,
                rate=o.rate or None, queue=o.queue if o.rate else None)
    tx = Sender(sock, link, (o.host, o.port), data, o.mode, o.window)
    t = time.monotonic()
    tx.run()
    dt = time.monotonic() - t
    link.close()
    s = tx.stats
    print(f"trimis {len(data)} octeti in {dt:.2f} s ({len(data) / 1024 / dt:.1f} KB/s)")
    print(f"retransmisii: {s['retx']}, timeout-uri: {s['timeouts']}, fast retransmit: {s['fast_retx']}")
    print("sha256:", hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
