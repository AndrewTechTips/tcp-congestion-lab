"""The bad network between sender and receiver.

On localhost packets arrive instantly and are never lost, so there is
nothing to see. Link sits in front of the UDP socket and spoils the traffic
on purpose: propagation delay, random loss, flipped bytes and, optionally,
a router with a limited rate and a finite tail-drop queue.
A full queue is congestion, which is exactly what congestion control is for.
"""

import heapq
import random
import threading
import time

from .packet import HEADER


class Router:
    """A router's output queue. Kept apart from Link so several flows can
    share one (the fairness test in fairness.py)."""

    def __init__(self, rate, queue):
        self.rate = rate            # packets/s on the outgoing link
        self.queue = queue          # how many packets fit in the queue
        self.busy_until = 0.0       # when the router finishes sending what it has queued
        self.lock = threading.Lock()

    def backlog(self, now):
        return max(0.0, (self.busy_until - now) * self.rate)


class Link:
    def __init__(self, sock, name="data", delay=0.05, jitter=0.0, loss=0.0,
                 corrupt=0.0, rate=None, queue=None, seed=None, clock=None, log=None,
                 router=None):
        self.sock = sock
        self.name = name
        self.delay = delay          # one-way propagation delay (s)
        self.jitter = jitter
        self.loss = loss            # loss probability 0..1
        self.corrupt = corrupt      # probability of flipping a byte
        # rate-limited router; None means an infinitely fast link
        self.router = router or (Router(rate, queue) if rate else None)
        self.rng = random.Random(seed)
        self.clock = clock or time.monotonic
        self.log = log if log is not None else []

        self._heap = []
        self._n = 0
        self._cv = threading.Condition()
        self._stop = False
        self._th = threading.Thread(target=self._deliver_loop, daemon=True)
        self._th.start()

    def backlog(self, now=None):
        if not self.router:
            return 0
        return self.router.backlog(self.clock() if now is None else now)

    def send(self, data: bytes, addr):
        now = self.clock()
        ptype, seq, ack, _, _ = HEADER.unpack_from(data)
        ev = {"t": round(now, 5), "dir": self.name, "type": ptype, "seq": seq,
              "ack": ack, "arrive": None, "drop": None}

        if self.rng.random() < self.loss:
            ev["drop"] = "loss"
            self.log.append(ev)
            return

        start = now
        r = self.router
        if r:
            with r.lock:
                q = r.backlog(now)
                ev["q"] = round(q, 2)
                if r.queue is not None and q >= r.queue:
                    ev["drop"] = "queue"   # the router's queue is full
                    self.log.append(ev)
                    return
                r.busy_until = max(now, r.busy_until) + 1.0 / r.rate
                start = r.busy_until

        arrive = start + self.delay
        if self.jitter:
            arrive += self.rng.uniform(0, self.jitter)

        if self.rng.random() < self.corrupt:
            # flip a random byte; the checksum has to catch it
            b = bytearray(data)
            i = self.rng.randrange(len(b))
            b[i] ^= 0xFF
            data = bytes(b)
            ev["corrupt"] = True

        ev["arrive"] = round(arrive, 5)
        self.log.append(ev)
        with self._cv:
            self._n += 1
            heapq.heappush(self._heap, (arrive, self._n, data, addr))
            self._cv.notify()

    def _deliver_loop(self):
        with self._cv:
            while not self._stop:
                if not self._heap:
                    self._cv.wait()
                    continue
                arrive, _, data, addr = self._heap[0]
                wait = arrive - self.clock()
                if wait > 0:
                    self._cv.wait(wait)
                    continue
                heapq.heappop(self._heap)
                try:
                    self.sock.sendto(data, addr)
                except OSError:
                    pass  # the socket closed in the meantime, nobody is listening

    def close(self):
        with self._cv:
            self._stop = True
            self._cv.notify()
        self._th.join(timeout=1)
