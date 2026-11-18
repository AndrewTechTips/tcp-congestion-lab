"""The receiver. It learns which mode to run from the sender's SYN."""

import socket
import time

from . import packet as P

CUMULATIVE = ("sw", "gbn")      # in order only, everything else is dropped
BUFFERING = ("tahoe", "reno", "newreno")  # like TCP: keep what arrives early
SELECTIVE = ("sr",)


class Receiver:
    def __init__(self, sock, link, clock=None, log=None, linger=1.0):
        self.sock = sock
        self.link = link
        self.clock = clock or time.monotonic
        self.log = log if log is not None else []
        self.linger = linger

        self.mode = None
        self.window = 1
        self.expected = 0        # next seq we expect in order
        self.buf = {}            # packets that arrived early (sr / tcp)
        self.chunks = []
        self.peer = None
        self.data = None         # filled in once FIN arrives and nothing is missing
        self.stopped = False

    def _ev(self, ev, seq=None):
        self.log.append({"t": round(self.clock(), 5), "ev": ev, "seq": seq})

    def _send(self, ptype, seq=0, ack=0):
        self.link.send(P.build(ptype, seq, ack), self.peer)

    def _deliver_in_order(self):
        while self.expected in self.buf:
            self.chunks.append(self.buf.pop(self.expected))
            self.expected += 1

    def _on_data(self, seq, payload):
        if self.mode in SELECTIVE:
            if self.expected <= seq < self.expected + self.window:
                if seq in self.buf:
                    self._ev("dup", seq)
                else:
                    self.buf[seq] = payload
                    self._ev("buffer" if seq != self.expected else "deliver", seq)
                self._send(P.ACK, ack=seq)
                self._deliver_in_order()
            elif seq < self.expected:
                # our ACK got lost and the sender is retrying. Confirm it again.
                self._ev("dup", seq)
                self._send(P.ACK, ack=seq)
            else:
                self._ev("discard", seq)
            return

        if seq == self.expected:
            self.buf[seq] = payload
            self._ev("deliver", seq)
            self._deliver_in_order()
        elif seq > self.expected and self.mode in BUFFERING:
            if seq not in self.buf:
                self.buf[seq] = payload
                self._ev("buffer", seq)
            else:
                self._ev("dup", seq)
        else:
            # gbn/sw drop anything out of order; seq < expected is a duplicate
            self._ev("discard" if seq > self.expected else "dup", seq)
        # cumulative ACK: "I have everything up to expected-1, send expected"
        self._send(P.ACK, ack=self.expected)

    def run(self, idle_timeout=30.0):
        last_rx = time.monotonic()
        done_at = None
        self.sock.settimeout(0.1)
        while not self.stopped:
            now = time.monotonic()
            if done_at is not None and now - done_at > self.linger:
                break   # a small TIME_WAIT: we kept answering late FINs for a while
            if now - last_rx > idle_timeout:
                break
            try:
                raw, addr = self.sock.recvfrom(4096)
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                break
            last_rx = time.monotonic()
            pkt = P.parse(raw)
            if pkt is None:
                self._ev("corrupt")
                continue
            ptype, seq, ack, payload = pkt
            self.peer = addr

            if ptype == P.SYN:
                mode, window = payload.decode().split(",")
                self.mode, self.window = mode, int(window)
                self._ev("syn")
                self._send(P.SYNACK)
            elif ptype == P.ACK:
                pass   # third step of the handshake, nothing to do
            elif ptype == P.DATA and self.mode:
                self._on_data(seq, payload)
            elif ptype == P.FIN:
                if self.expected >= seq:
                    if self.data is None:
                        self.data = b"".join(self.chunks)
                        self._ev("fin", seq)
                        done_at = time.monotonic()
                    self._send(P.FINACK, ack=seq)
        return self.data
