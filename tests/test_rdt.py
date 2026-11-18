"""Teste automate. Se ruleaza din folderul proiectului cu:

  python3 -m unittest -v
"""

import os
import socket
import unittest

from rdt import packet as P
from rdt.link import Link
from rdt.rtt import RttEstimator
from rdt.sender import MODES
from rdt.session import run_transfer


class TestPacket(unittest.TestCase):
    # checksum-ul nostru da acelasi rezultat ca exemplul din RFC 1071
    def test_checksum_exemplul_din_rfc1071(self):
        self.assertEqual(P.checksum(bytes.fromhex("0001f203f4f5f6f7")), 0x220D)

    # construiesc un pachet, il citesc inapoi si trebuie sa am aceleasi campuri
    def test_build_parse_dus_intors(self):
        raw = P.build(P.DATA, 42, 7, b"salut")
        self.assertEqual(len(raw), P.HEADER_SIZE + 5)
        self.assertEqual(P.parse(raw), (P.DATA, 42, 7, b"salut"))

    # stric pe rand fiecare bit din pachet; checksum-ul trebuie sa prinda de fiecare data
    def test_orice_bit_stricat_e_detectat(self):
        raw = P.build(P.DATA, 3, 0, b"date de test")
        for i in range(len(raw)):
            for bit in range(8):
                b = bytearray(raw)
                b[i] ^= 1 << bit
                self.assertIsNone(P.parse(bytes(b)), f"octet {i}, bit {bit}")

    # un pachet mai scurt decat antetul e aruncat, nu crapa programul
    def test_pachet_prea_scurt(self):
        self.assertIsNone(P.parse(b"\x00\x01"))


class TestRtt(unittest.TestCase):
    # la prima masuratoare: SRTT = R, RTTVAR = R/2, RTO = SRTT + 4*RTTVAR
    def test_prima_masuratoare(self):
        r = RttEstimator(min_rto=0.0)
        r.sample(0.1)
        self.assertAlmostEqual(r.srtt, 0.1)
        self.assertAlmostEqual(r.rttvar, 0.05)
        self.assertAlmostEqual(r.rto, 0.1 + 4 * 0.05)

    # a doua masuratoare foloseste formulele cu 1/8 si 1/4 din RFC 6298
    def test_a_doua_masuratoare(self):
        r = RttEstimator(min_rto=0.0)
        r.sample(0.1)
        r.sample(0.2)
        # rttvar = 3/4 * 0.05 + 1/4 * |0.1 - 0.2|, srtt = 7/8 * 0.1 + 1/8 * 0.2
        self.assertAlmostEqual(r.rttvar, 0.0625)
        self.assertAlmostEqual(r.srtt, 0.1125)

    # la timeout RTO se dubleaza, dar nu trece de maximul de 8 s
    def test_backoff_dubleaza_dar_are_plafon(self):
        r = RttEstimator(initial_rto=1.0, max_rto=8.0)
        r.backoff()
        self.assertEqual(r.rto, 2.0)
        for _ in range(10):
            r.backoff()
        self.assertEqual(r.rto, 8.0)

    # chiar daca RTT-ul e foarte mic, RTO nu coboara sub 200 ms
    def test_rto_minim(self):
        r = RttEstimator(min_rto=0.2)
        r.sample(0.001)
        self.assertEqual(r.rto, 0.2)


class TestLink(unittest.TestCase):
    def setUp(self):
        self.a = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.a.bind(("127.0.0.1", 0))
        self.b.bind(("127.0.0.1", 0))
        self.b.settimeout(1)

    def tearDown(self):
        self.a.close()
        self.b.close()

    # cu pierdere 100%, legatura simulata arunca toate pachetele
    def test_pierdere_100_la_suta(self):
        log = []
        link = Link(self.a, loss=1.0, delay=0, log=log)
        for i in range(20):
            link.send(P.build(P.DATA, i), self.b.getsockname())
        link.close()
        self.assertTrue(all(e["drop"] == "loss" for e in log))

    # trimit 20 de pachete deodata intr-un router cu coada de 5; ce nu incape e aruncat
    def test_coada_plina_arunca(self):
        log = []
        link = Link(self.a, delay=0, rate=10, queue=5, log=log)
        for i in range(20):
            link.send(P.build(P.DATA, i), self.b.getsockname())
        link.close()
        # unul se transmite chiar acum, 5 asteapta in coada, restul de 14 cad
        self.assertEqual(sum(1 for e in log if e["drop"] == "queue"), 14)

    # fara pierderi, pachetul ajunge la celalalt socket dupa intarziere, neschimbat
    def test_livreaza_dupa_intarziere(self):
        link = Link(self.a, delay=0.05)
        link.send(P.build(P.DATA, 9, 0, b"x"), self.b.getsockname())
        raw, _ = self.b.recvfrom(100)
        link.close()
        self.assertEqual(P.parse(raw)[1], 9)


class TestTransfer(unittest.TestCase):
    """Fisierul trebuie sa ajunga identic, in toate modurile, si cu erori."""

    # trimite date random si verifica (prin SHA-256) ca au ajuns identic
    def check(self, mode, **kw):
        data = os.urandom(int(kw.pop("size_kb", 40) * 1024))
        r = run_transfer(mode=mode, data=data, seed=7, **kw)
        self.assertTrue(r["ok"], f"{mode}: {r['error']}")
        return r

    # retea perfecta: toate cele 6 protocoale merg si nu retrimit nimic
    def test_fara_erori(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                r = self.check(mode, size_kb=10 if mode == "sw" else 40, rate=0)
                self.assertEqual(r["stats"]["retx"], 0)

    # retea proasta (pachete pierdute, ACK-uri pierdute, pachete stricate):
    # fisierul tot trebuie sa ajunga identic, iar protocolul chiar retrimite
    def test_cu_pierderi_si_corupere(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                r = self.check(mode, size_kb=10 if mode == "sw" else 40,
                               loss=0.05, ack_loss=0.03, corrupt=0.02, rate=0)
                self.assertGreater(r["stats"]["retx"], 0)

    # router cu coada mica: TCP umple coada, apar pierderi, dar fisierul ajunge
    def test_congestie_la_router(self):
        for mode in ("tahoe", "reno", "newreno"):
            with self.subTest(mode=mode):
                r = self.check(mode, size_kb=300, rate=200, queue=12)
                self.assertGreater(r["stats"]["dropped_queue"], 0)

    # caz limita: un fisier gol se transfera fara erori
    def test_fisier_gol(self):
        r = run_transfer(mode="reno", data=b"", seed=1)
        self.assertTrue(r["ok"])

    # fara pierderi, slow start dubleaza cwnd: 1, 2, 4, 8, 16...
    def test_slow_start_dubleaza_fereastra(self):
        r = self.check("reno", size_kb=60, rate=0, delay_ms=50)
        cw = [t[1] for t in r["trace"]]
        self.assertIn(2.0, cw)
        self.assertIn(4.0, cw)
        self.assertIn(8.0, cw)
        self.assertIn(16.0, cw)


if __name__ == "__main__":
    unittest.main()
