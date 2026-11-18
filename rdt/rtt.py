"""Estimarea RTT si calculul timeout-ului, dupa RFC 6298."""


class RttEstimator:
    ALPHA = 1 / 8
    BETA = 1 / 4

    def __init__(self, initial_rto=1.0, min_rto=0.2, max_rto=8.0):
        self.srtt = None
        self.rttvar = None
        self.rto = initial_rto
        self.min_rto = min_rto
        self.max_rto = max_rto

    def sample(self, r):
        if self.srtt is None:
            # prima masuratoare
            self.srtt = r
            self.rttvar = r / 2
        else:
            # ordinea conteaza: rttvar se actualizeaza cu srtt-ul vechi
            self.rttvar = (1 - self.BETA) * self.rttvar + self.BETA * abs(self.srtt - r)
            self.srtt = (1 - self.ALPHA) * self.srtt + self.ALPHA * r
        self.rto = self._clamp(self.srtt + 4 * self.rttvar)

    def backoff(self):
        # dupa un timeout dublam RTO-ul (exponential backoff)
        self.rto = self._clamp(self.rto * 2)

    def _clamp(self, x):
        return max(self.min_rto, min(self.max_rto, x))
