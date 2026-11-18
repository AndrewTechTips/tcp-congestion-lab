"""The sender. One thread and one event loop: send as much as the window
allows, then wait for an ACK or a timeout.

Modes:
  sw       stop-and-wait (window = 1)
  gbn      Go-Back-N, fixed window, resends the whole window on a timeout
  sr       Selective Repeat, a timer per packet, resends only what was lost
  tahoe    TCP Tahoe: slow start + AIMD, cwnd = 1 on three duplicate ACKs
  reno     TCP Reno: like Tahoe, with fast recovery (cwnd = ssthresh + 3)
  newreno  Reno fixed by RFC 6582: a partial ACK does not end fast recovery,
           so it survives several losses in the same window

Packets are numbered, not bytes as in real TCP. It keeps the charts readable
and changes nothing about the idea.
"""

import math
import socket
import time

from . import packet as P
from .rtt import RttEstimator

MODES = ("sw", "gbn", "sr", "tahoe", "reno", "newreno")
TCP_MODES = ("tahoe", "reno", "newreno")


class TransferError(Exception):
    pass


class Sender:
    def __init__(self, sock, link, peer, data, mode="reno", window=8,
                 rwnd=64, clock=None, log=None, init_rto=1.0, min_rto=0.2,
                 max_time=120.0):
        if mode not in MODES:
            raise ValueError(f"unknown mode: {mode}")
        self.sock = sock
        self.link = link
        self.peer = peer
        self.mode = mode
        self.window = 1 if mode == "sw" else window
        self.rwnd = rwnd
        self.clock = clock or time.monotonic
        self.log = log if log is not None else []
        self.rtt = RttEstimator(init_rto, min_rto)
        self.max_time = max_time

        self.chunks = [data[i:i + P.MAX_PAYLOAD]
                       for i in range(0, len(data), P.MAX_PAYLOAD)] or [b""]
        self.n = len(self.chunks)

        # window state
        self.base = 0          # oldest unacknowledged packet
        self.nxt = 0           # next new packet to send
        self.sent_at = {}      # seq -> time of the last send
        self.ever_sent = set()
        self.retx = set()      # packets sent more than once (for Karn's rule)
        self.timer = None      # a single timer (sw, gbn, tcp)
        self.timers = {}       # sr: one timer per packet
        self.acked = set()     # sr

        # congestion control
        self.cwnd = 1.0
        self.ssthresh = 64.0
        self.dupacks = 0
        self.in_recovery = False
        self.recover = -1      # highest seq sent when the last loss was detected

        self.trace = []        # [t, cwnd, ssthresh, srtt, rto]
        self.stats = {"sent": 0, "retx": 0, "timeouts": 0, "fast_retx": 0,
                      "dupacks": 0, "corrupt_acks": 0}

    # ---- helpers --------------------------------------------------------

    def now(self):
        return self.clock()

    def _ev(self, ev, seq=None, **extra):
        e = {"t": round(self.now(), 5), "ev": ev, "seq": seq}
        e.update(extra)
        self.log.append(e)

    def _record(self):
        self.trace.append([round(self.now(), 5), round(self.cwnd, 3),
                           round(min(self.ssthresh, 999), 3),
                           round(self.rtt.srtt or 0, 5), round(self.rtt.rto, 5)])

    def _wnd(self):
        if self.mode in TCP_MODES:
            return max(1, min(int(math.floor(self.cwnd)), self.rwnd))
        return self.window

    def _send_data(self, seq):
        self.link.send(P.build(P.DATA, seq, 0, self.chunks[seq]), self.peer)
        self.stats["sent"] += 1
        if seq in self.ever_sent:
            self.retx.add(seq)
            self.stats["retx"] += 1
            self._ev("retx", seq)
        else:
            self.ever_sent.add(seq)
            self._ev("send", seq)
        self.sent_at[seq] = self.now()
        if self.mode == "sr":
            self.timers[seq] = self.now() + self.rtt.rto
        elif self.timer is None:
            self.timer = self.now() + self.rtt.rto

    def _restart_timer(self):
        self.timer = self.now() + self.rtt.rto if self.base < self.nxt else None

    def _sample(self, seq):
        # Karn: no RTT samples from retransmitted packets, the ACK could be for either copy
        if seq in self.sent_at and seq not in self.retx:
            self.rtt.sample(self.now() - self.sent_at[seq])

    def _recv(self, timeout):
        self.sock.settimeout(max(timeout, 0.0005))
        try:
            raw, _ = self.sock.recvfrom(4096)
        except (socket.timeout, TimeoutError):
            return None
        pkt = P.parse(raw)
        if pkt is None:
            self.stats["corrupt_acks"] += 1
            self._ev("corrupt")
            return False
        return pkt

    # ---- handshake and teardown ------------------------------------------

    def _exchange(self, ptype, seq, payload, want, tries=12):
        """Sends a control packet until the expected answer comes back."""
        for attempt in range(tries):
            t0 = self.now()
            self.link.send(P.build(ptype, seq, 0, payload), self.peer)
            self._ev(P.TYPE_NAMES[ptype].lower(), seq)
            deadline = t0 + self.rtt.rto
            while self.now() < deadline:
                pkt = self._recv(deadline - self.now())
                if pkt and pkt[0] == want:
                    if attempt == 0:
                        self.rtt.sample(self.now() - t0)
                    return
            self.rtt.backoff()
        raise TransferError(f"no answer to {P.TYPE_NAMES[ptype]}")

    # ---- the transfer --------------------------------------------------------

    def run(self):
        t_start = self.now()
        self._record()
        self._exchange(P.SYN, 0, f"{self.mode},{self.window}".encode(), P.SYNACK)
        self.link.send(P.build(P.ACK), self.peer)
        self._record()
        t_data = self.now()

        while self.base < self.n:
            if self.now() - t_start > self.max_time:
                raise TransferError("transfer is taking too long, giving up")

            while self.nxt < self.n and self.nxt < self.base + self._wnd():
                if self.mode == "sr" and self.nxt in self.acked:
                    self.nxt += 1
                    continue
                self._send_data(self.nxt)
                self.nxt += 1

            deadline = self._next_deadline()
            pkt = self._recv(deadline - self.now() if deadline else 1.0)
            if pkt:
                if pkt[0] == P.ACK:
                    self._on_ack(pkt[2])
            elif pkt is None:
                self._check_timeouts()

        t_end = self.now()
        self._exchange(P.FIN, self.n, b"", P.FINACK)
        return {"t_start": t_start, "t_data": t_data, "t_end": t_end,
                "t_closed": self.now()}

    def _next_deadline(self):
        if self.mode == "sr":
            return min(self.timers.values()) if self.timers else None
        return self.timer

    # ---- ACKs -----------------------------------------------------------

    def _on_ack(self, ack):
        if self.mode == "sr":
            self._on_ack_sr(ack)
            return

        if ack > self.base:
            newly = ack - self.base
            self._sample(ack - 1)
            self._ev("ack", ack)
            self.base = ack
            self.nxt = max(self.nxt, ack)
            self.dupacks = 0
            if self.mode in TCP_MODES:
                self._cc_new_ack(newly, ack)
            else:
                self._record()
            self._restart_timer()
        elif ack == self.base and self.base < self.nxt:
            self.dupacks += 1
            self.stats["dupacks"] += 1
            self._ev("dupack", ack, n=self.dupacks)
            if self.mode in TCP_MODES:
                self._cc_dupack()

    def _on_ack_sr(self, seq):
        if seq < self.base or seq in self.acked:
            return
        self._sample(seq)
        self.acked.add(seq)
        self.timers.pop(seq, None)
        self._ev("ack", seq)
        self._record()
        while self.base in self.acked:
            self.base += 1

    # ---- congestion control (tahoe/reno/newreno only) ----------------------------

    def _cc_new_ack(self, newly, ack):
        if self.in_recovery:
            if self.mode == "newreno" and ack <= self.recover:
                # partial ACK: something from the old window is still missing.
                # resend it now instead of waiting for three more duplicates.
                self.cwnd = max(self.cwnd - newly + 1, 1)
                self._send_data(self.base)
                self._record()
                return
            # leaving fast recovery, deflate the window
            self.cwnd = self.ssthresh
            self.in_recovery = False
        elif self.cwnd < self.ssthresh:
            self.cwnd += newly                   # slow start: +1 per ACK
        else:
            self.cwnd += newly / self.cwnd       # AIMD: about +1 per RTT
        self.cwnd = min(self.cwnd, self.rwnd)
        self._record()

    def _cc_dupack(self):
        if self.in_recovery:
            # one more packet has left the network
            self.cwnd = min(self.cwnd + 1, self.rwnd)
            self._record()
            return
        if self.dupacks == 3:
            # RFC 6582: if the ACK has not passed recover, these duplicates come from
            # our own retransmissions, not from a new loss. Ignore them.
            if self.mode != "reno" and self.base <= self.recover:
                return
            self.stats["fast_retx"] += 1
            flight = self.nxt - self.base
            self.ssthresh = max(flight / 2, 2)
            self._ev("fast_retx", self.base)
            if self.mode == "tahoe":
                self.cwnd = 1.0
                self.recover = self.nxt - 1
                self.nxt = self.base         # start over with slow start
            else:
                self.cwnd = self.ssthresh + 3
                self.in_recovery = True
                self.recover = self.nxt - 1
                self._send_data(self.base)   # resend only the missing packet
            self.timer = self.now() + self.rtt.rto
            self._record()

    # ---- timeouts -------------------------------------------------------

    def _check_timeouts(self):
        now = self.now()
        if self.mode == "sr":
            expired = [s for s, d in self.timers.items() if d <= now]
            if expired:
                self.stats["timeouts"] += 1
                self.rtt.backoff()
                for s in sorted(expired):
                    self._ev("timeout", s)
                    self._send_data(s)
            return

        if self.timer is None or self.timer > now:
            return
        self.stats["timeouts"] += 1
        self._ev("timeout", self.base)
        self.rtt.backoff()
        if self.mode in TCP_MODES:
            flight = self.nxt - self.base
            self.ssthresh = max(flight / 2, 2)
            self.cwnd = 1.0
            self.in_recovery = False
            self.dupacks = 0
            self.recover = self.nxt - 1
            self._record()
        # sw, gbn and tcp: go back to base and resend from there
        self.nxt = self.base
        self.timer = None
