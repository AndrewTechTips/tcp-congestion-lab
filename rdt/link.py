"""Legatura "proasta" dintre expeditor si receptor.

Pe localhost pachetele ajung instant si nu se pierd niciodata, asa ca nu ai
ce sa vezi. Clasa asta sta in fata socket-ului UDP si strica intentionat
traficul: intarziere de propagare, pierderi aleatoare, biti corupti si,
optional, un router cu debit limitat si coada finita (tail drop).
Coada plina = congestie, exact cazul pentru care exista controlul congestiei.
"""

import heapq
import random
import threading
import time

from .packet import HEADER


class Router:
    """Coada unui router. Separata de Link ca s-o poata imparti mai multe
    fluxuri (testul de echitate din fairness.py)."""

    def __init__(self, rate, queue):
        self.rate = rate            # pachete/s pe legatura de iesire
        self.queue = queue          # cate pachete incap in coada
        self.busy_until = 0.0       # cand termina routerul de trimis ce are in coada
        self.lock = threading.Lock()

    def backlog(self, now):
        return max(0.0, (self.busy_until - now) * self.rate)


class Link:
    def __init__(self, sock, name="data", delay=0.05, jitter=0.0, loss=0.0,
                 corrupt=0.0, rate=None, queue=None, seed=None, clock=None, log=None,
                 router=None):
        self.sock = sock
        self.name = name
        self.delay = delay          # intarzierea de propagare, intr-un singur sens (s)
        self.jitter = jitter
        self.loss = loss            # probabilitate de pierdere 0..1
        self.corrupt = corrupt      # probabilitate sa stricam un octet
        # router cu debit limitat; None = legatura infinit de rapida
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
                    ev["drop"] = "queue"   # coada routerului e plina
                    self.log.append(ev)
                    return
                r.busy_until = max(now, r.busy_until) + 1.0 / r.rate
                start = r.busy_until

        arrive = start + self.delay
        if self.jitter:
            arrive += self.rng.uniform(0, self.jitter)

        if self.rng.random() < self.corrupt:
            # stricam un octet random, checksum-ul trebuie sa prinda asta
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
                    pass  # socket-ul s-a inchis intre timp, nu ne mai pasa

    def close(self):
        with self._cv:
            self._stop = True
            self._cv.notify()
        self._th.join(timeout=1)
