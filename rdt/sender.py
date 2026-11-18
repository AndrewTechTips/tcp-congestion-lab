"""Expeditorul. Un singur fir de executie si o bucla de evenimente:
trimite cat ii permite fereastra, apoi asteapta un ACK sau un timeout.

Moduri:
  sw     stop-and-wait (fereastra = 1)
  gbn    Go-Back-N, fereastra fixa, la timeout retrimite toata fereastra
  sr     Selective Repeat, timer pe fiecare pachet, retrimite doar ce s-a pierdut
  tahoe  TCP Tahoe: slow start + AIMD, la 3 ACK-uri duplicate cwnd = 1
  reno   TCP Reno: ca Tahoe, dar cu fast recovery (cwnd = ssthresh + 3)
  newreno  Reno reparat (RFC 6582): un ACK partial nu scoate din fast recovery,
           asa ca supravietuieste mai multor pierderi in aceeasi fereastra

Numerotam pachete, nu octeti ca in TCP-ul adevarat. E mai usor de urmarit
pe grafice si nu schimba nimic din idee.
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
            raise ValueError(f"mod necunoscut: {mode}")
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

        # starea ferestrei
        self.base = 0          # cel mai vechi pachet neconfirmat
        self.nxt = 0           # urmatorul pachet nou de trimis
        self.sent_at = {}      # seq -> momentul ultimei trimiteri
        self.ever_sent = set()
        self.retx = set()      # pachete retrimise (pt. algoritmul lui Karn)
        self.timer = None      # un singur timer (sw, gbn, tcp)
        self.timers = {}       # sr: cate un timer pe pachet
        self.acked = set()     # sr

        # control congestie
        self.cwnd = 1.0
        self.ssthresh = 64.0
        self.dupacks = 0
        self.in_recovery = False
        self.recover = -1      # cel mai mare seq trimis cand am detectat ultima pierdere

        self.trace = []        # [t, cwnd, ssthresh, srtt, rto]
        self.stats = {"sent": 0, "retx": 0, "timeouts": 0, "fast_retx": 0,
                      "dupacks": 0, "corrupt_acks": 0}

    # ---- utilitare --------------------------------------------------------

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
        # Karn: nu masuram RTT pe pachete retrimise, nu stim carui ACK ii apartine
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

    # ---- handshake si inchidere ------------------------------------------

    def _exchange(self, ptype, seq, payload, want, tries=12):
        """Trimite un pachet de control pana primeste raspunsul asteptat."""
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
        raise TransferError(f"nu raspunde la {P.TYPE_NAMES[ptype]}")

    # ---- transferul --------------------------------------------------------

    def run(self):
        t_start = self.now()
        self._record()
        self._exchange(P.SYN, 0, f"{self.mode},{self.window}".encode(), P.SYNACK)
        self.link.send(P.build(P.ACK), self.peer)
        self._record()
        t_data = self.now()

        while self.base < self.n:
            if self.now() - t_start > self.max_time:
                raise TransferError("transferul dureaza prea mult, ma opresc")

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

    # ---- ACK-uri -----------------------------------------------------------

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

    # ---- controlul congestiei (doar tahoe/reno) ----------------------------

    def _cc_new_ack(self, newly, ack):
        if self.in_recovery:
            if self.mode == "newreno" and ack <= self.recover:
                # ACK partial: mai lipseste ceva din fereastra veche.
                # Retrimitem imediat, fara sa asteptam alte 3 duplicate.
                self.cwnd = max(self.cwnd - newly + 1, 1)
                self._send_data(self.base)
                self._record()
                return
            # am iesit din fast recovery, dezumflam fereastra
            self.cwnd = self.ssthresh
            self.in_recovery = False
        elif self.cwnd < self.ssthresh:
            self.cwnd += newly                   # slow start: +1 pe fiecare ACK
        else:
            self.cwnd += newly / self.cwnd       # AIMD: ~ +1 pe fiecare RTT
        self.cwnd = min(self.cwnd, self.rwnd)
        self._record()

    def _cc_dupack(self):
        if self.in_recovery:
            # inca un pachet a parasit reteaua
            self.cwnd = min(self.cwnd + 1, self.rwnd)
            self._record()
            return
        if self.dupacks == 3:
            # RFC 6582: daca ACK-ul nu trece de recover, duplicatele vin din
            # retransmisiile noastre, nu dintr-o pierdere noua. Le ignoram.
            if self.mode != "reno" and self.base <= self.recover:
                return
            self.stats["fast_retx"] += 1
            flight = self.nxt - self.base
            self.ssthresh = max(flight / 2, 2)
            self._ev("fast_retx", self.base)
            if self.mode == "tahoe":
                self.cwnd = 1.0
                self.recover = self.nxt - 1
                self.nxt = self.base         # o luam de la capat cu slow start
            else:
                self.cwnd = self.ssthresh + 3
                self.in_recovery = True
                self.recover = self.nxt - 1
                self._send_data(self.base)   # retrimitem doar pachetul lipsa
            self.timer = self.now() + self.rtt.rto
            self._record()

    # ---- timeout-uri -------------------------------------------------------

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
        # sw, gbn si tcp: ne intoarcem la base si retrimitem de acolo
        self.nxt = self.base
        self.timer = None
