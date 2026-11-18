"""Test suite. Run it from the project folder with:

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
    # our checksum gives the same answer as the worked example in RFC 1071
    def test_checksum_matches_rfc1071_example(self):
        self.assertEqual(P.checksum(bytes.fromhex("0001f203f4f5f6f7")), 0x220D)

    # build a packet, parse it back, and every field must survive
    def test_build_then_parse_round_trip(self):
        raw = P.build(P.DATA, 42, 7, b"hello")
        self.assertEqual(len(raw), P.HEADER_SIZE + 5)
        self.assertEqual(P.parse(raw), (P.DATA, 42, 7, b"hello"))

    # flip every bit of the packet in turn; the checksum must catch each one
    def test_any_flipped_bit_is_detected(self):
        raw = P.build(P.DATA, 3, 0, b"some test data")
        for i in range(len(raw)):
            for bit in range(8):
                b = bytearray(raw)
                b[i] ^= 1 << bit
                self.assertIsNone(P.parse(bytes(b)), f"byte {i}, bit {bit}")

    # anything shorter than the header is rejected instead of crashing
    def test_packet_shorter_than_header(self):
        self.assertIsNone(P.parse(b"\x00\x01"))


class TestRtt(unittest.TestCase):
    # first sample: SRTT = R, RTTVAR = R/2, RTO = SRTT + 4*RTTVAR
    def test_first_sample(self):
        r = RttEstimator(min_rto=0.0)
        r.sample(0.1)
        self.assertAlmostEqual(r.srtt, 0.1)
        self.assertAlmostEqual(r.rttvar, 0.05)
        self.assertAlmostEqual(r.rto, 0.1 + 4 * 0.05)

    # the second sample uses the 1/8 and 1/4 gains from RFC 6298
    def test_second_sample(self):
        r = RttEstimator(min_rto=0.0)
        r.sample(0.1)
        r.sample(0.2)
        # rttvar = 3/4 * 0.05 + 1/4 * |0.1 - 0.2|, srtt = 7/8 * 0.1 + 1/8 * 0.2
        self.assertAlmostEqual(r.rttvar, 0.0625)
        self.assertAlmostEqual(r.srtt, 0.1125)

    # a timeout doubles the RTO, but never past the 8 s cap
    def test_backoff_doubles_up_to_the_cap(self):
        r = RttEstimator(initial_rto=1.0, max_rto=8.0)
        r.backoff()
        self.assertEqual(r.rto, 2.0)
        for _ in range(10):
            r.backoff()
        self.assertEqual(r.rto, 8.0)

    # however small the RTT, the RTO stays at 200 ms or more
    def test_rto_floor(self):
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

    # with 100% loss the link drops every packet
    def test_full_loss_drops_everything(self):
        log = []
        link = Link(self.a, loss=1.0, delay=0, log=log)
        for i in range(20):
            link.send(P.build(P.DATA, i), self.b.getsockname())
        link.close()
        self.assertTrue(all(e["drop"] == "loss" for e in log))

    # 20 packets at once into a router with a 5-slot queue; whatever does not fit is dropped
    def test_full_queue_drops_the_excess(self):
        log = []
        link = Link(self.a, delay=0, rate=10, queue=5, log=log)
        for i in range(20):
            link.send(P.build(P.DATA, i), self.b.getsockname())
        link.close()
        # one is on the wire, 5 wait in the queue, the other 14 are dropped
        self.assertEqual(sum(1 for e in log if e["drop"] == "queue"), 14)

    # without loss the packet reaches the other socket, unchanged, after the delay
    def test_delivers_after_the_delay(self):
        link = Link(self.a, delay=0.05)
        link.send(P.build(P.DATA, 9, 0, b"x"), self.b.getsockname())
        raw, _ = self.b.recvfrom(100)
        link.close()
        self.assertEqual(P.parse(raw)[1], 9)


class TestTransfer(unittest.TestCase):
    """The file has to arrive identical in every mode, errors or not."""

    # send random data and check (via SHA-256) that it arrived identical
    def check(self, mode, **kw):
        data = os.urandom(int(kw.pop("size_kb", 40) * 1024))
        r = run_transfer(mode=mode, data=data, seed=7, **kw)
        self.assertTrue(r["ok"], f"{mode}: {r['error']}")
        return r

    # clean network: all six protocols work and resend nothing
    def test_clean_link(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                r = self.check(mode, size_kb=10 if mode == "sw" else 40, rate=0)
                self.assertEqual(r["stats"]["retx"], 0)

    # bad network (lost packets, lost ACKs, corrupted packets):
    # the file still arrives identical, and the protocol really did resend
    def test_loss_and_corruption(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                r = self.check(mode, size_kb=10 if mode == "sw" else 40,
                               loss=0.05, ack_loss=0.03, corrupt=0.02, rate=0)
                self.assertGreater(r["stats"]["retx"], 0)

    # small router queue: TCP fills it, packets drop, the file still arrives
    def test_router_congestion(self):
        for mode in ("tahoe", "reno", "newreno"):
            with self.subTest(mode=mode):
                r = self.check(mode, size_kb=300, rate=200, queue=12)
                self.assertGreater(r["stats"]["dropped_queue"], 0)

    # edge case: an empty file goes through cleanly
    def test_empty_file(self):
        r = run_transfer(mode="reno", data=b"", seed=1)
        self.assertTrue(r["ok"])

    # without loss, slow start doubles cwnd: 1, 2, 4, 8, 16...
    def test_slow_start_doubles_the_window(self):
        r = self.check("reno", size_kb=60, rate=0, delay_ms=50)
        cw = [t[1] for t in r["trace"]]
        self.assertIn(2.0, cw)
        self.assertIn(4.0, cw)
        self.assertIn(8.0, cw)
        self.assertIn(16.0, cw)


if __name__ == "__main__":
    unittest.main()
