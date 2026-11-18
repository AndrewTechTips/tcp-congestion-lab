"""Receptorul ca proces separat. Util ca sa vezi pachetele in Wireshark
(interfata loopback, filtru: udp.port == 9000).

  python3 recv.py --port 9000 --out primit.bin
"""

import argparse
import socket

from rdt.link import Link
from rdt.receiver import Receiver


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--port", type=int, default=9000)
    a.add_argument("--out", default="primit.bin")
    a.add_argument("--delay", type=float, default=40, help="ms pe calea ACK")
    a.add_argument("--ack-loss", type=float, default=0.0)
    o = a.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", o.port))
    link = Link(sock, "ack", o.delay / 1000, loss=o.ack_loss)
    print(f"astept pe 127.0.0.1:{o.port} ...")
    rx = Receiver(sock, link, linger=2.0)
    data = rx.run(idle_timeout=120)
    link.close()
    if data is None:
        print("n-a venit nimic complet")
        return
    with open(o.out, "wb") as f:
        f.write(data)
    print(f"gata, am primit {len(data)} octeti in modul {rx.mode} -> {o.out}")


if __name__ == "__main__":
    main()
