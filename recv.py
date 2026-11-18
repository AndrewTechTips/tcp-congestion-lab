"""The receiver as a separate process. Handy for watching the packets in
Wireshark (loopback interface, filter: udp.port == 9000).

  python3 recv.py --port 9000 --out received.bin
"""

import argparse
import socket

from rdt.link import Link
from rdt.receiver import Receiver


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--port", type=int, default=9000)
    a.add_argument("--out", default="received.bin")
    a.add_argument("--delay", type=float, default=40, help="ms on the ACK path")
    a.add_argument("--ack-loss", type=float, default=0.0)
    o = a.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", o.port))
    link = Link(sock, "ack", o.delay / 1000, loss=o.ack_loss)
    print(f"listening on 127.0.0.1:{o.port} ...")
    rx = Receiver(sock, link, linger=2.0)
    data = rx.run(idle_timeout=120)
    link.close()
    if data is None:
        print("nothing complete arrived")
        return
    with open(o.out, "wb") as f:
        f.write(data)
    print(f"done, received {len(data)} bytes in {rx.mode} mode -> {o.out}")


if __name__ == "__main__":
    main()
