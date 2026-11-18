"""Genereaza graficele folosite in referat (are nevoie de matplotlib).

  pip install matplotlib
  python3 compare.py --runs 5     # o data, pt. figura cu comparatia
  python3 figuri.py
"""

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from rdt.session import run_transfer

OUT = "referat/figuri"
BLUE, RED, GREEN, ORANGE, GRAY, PURPLE = "#2f6fdb", "#d23f31", "#2a9d5c", "#e08a14", "#888888", "#8a4fc7"

plt.rcParams.update({
    "figure.dpi": 150, "font.size": 9.5, "axes.grid": True, "grid.alpha": 0.3,
    "axes.spines.top": False, "axes.spines.right": False,
})


def markers(ax, r):
    for e in r["sender"]:
        if e["ev"] == "timeout":
            ax.axvline(e["t"], color=RED, ls=":", lw=1, alpha=0.7)
        elif e["ev"] == "fast_retx":
            ax.axvline(e["t"], color=ORANGE, ls=":", lw=1, alpha=0.7)


def cwnd_plot(ax, r, title):
    tr = r["trace"]
    t = [x[0] for x in tr]
    ax.step(t, [x[1] for x in tr], where="post", color=BLUE, lw=1.6, label="cwnd")
    ax.step(t, [min(x[2], 70) for x in tr], where="post", color=ORANGE, ls="--", lw=1.1, label="ssthresh")
    markers(ax, r)
    ax.plot([], [], color=RED, ls=":", label="timeout")
    ax.plot([], [], color=ORANGE, ls=":", label="3 ACK duplicate")
    ax.set_title(title, loc="left", fontsize=10)
    ax.set_ylabel("pachete")
    ax.legend(loc="upper right", fontsize=8, ncol=4)


def fig_reno():
    r = run_transfer(mode="reno", size_kb=1500, seed=3)
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    cwnd_plot(ax, r, "TCP Reno, legătură de 200 pachete/s, RTT 80 ms, coada de 12 pachete")
    ax.set_xlabel("timp (s)")
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig_reno_cwnd.png")
    plt.close(fig)
    return r


def fig_tahoe_vs_reno():
    fig, axs = plt.subplots(3, 1, figsize=(7.2, 6.6), sharex=True)
    for ax, mode, name in zip(axs, ["tahoe", "reno", "newreno"], ["TCP Tahoe", "TCP Reno", "TCP NewReno"]):
        r = run_transfer(mode=mode, size_kb=1200, seed=7, loss=0.005)
        s = r["stats"]
        cwnd_plot(ax, r, f"{name}: {s['goodput_kbs']:.0f} KB/s, {s['timeouts']} timeout-uri, {s['fast_retx']} fast retransmit")
    axs[-1].set_xlabel("timp (s)")
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig_tahoe_reno_newreno.png")
    plt.close(fig)


def fig_seq(mode, name, fname, **kw):
    r = run_transfer(mode=mode, **kw)
    sent = [(e["t"], e["seq"]) for e in r["sender"] if e["ev"] == "send"]
    retx = [(e["t"], e["seq"]) for e in r["sender"] if e["ev"] == "retx"]
    lost = [(w["t"], w["seq"]) for w in r["wire"] if w["dir"] == "data" and w["type"] == 0 and w["drop"]]
    acks = sorted((w["arrive"], w["ack"]) for w in r["wire"] if w["dir"] == "ack" and w["type"] == 1 and not w["drop"])
    hi, line = 0, []
    for t, a in acks:
        hi = max(hi, a)
        line.append((t, hi))

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    if mode != "sr" and line:
        ax.step(*zip(*line), where="post", color=GREEN, lw=1.2, label="ACK cumulativ")
    ax.scatter(*zip(*sent), s=4, color=BLUE, label="trimis")
    if retx:
        ax.scatter(*zip(*retx), s=10, color=RED, label="retrimis")
    if lost:
        ax.scatter(*zip(*lost), s=22, marker="x", color=RED, lw=1, label="pierdut")
    markers(ax, r)
    s = r["stats"]
    ax.set_title(f"{name}: {s['packets']} pachete, {s['retx']} retransmisii, {s['duration']:.1f} s", loc="left", fontsize=10)
    ax.set_xlabel("timp (s)")
    ax.set_ylabel("număr pachet")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(f"{OUT}/{fname}")
    plt.close(fig)
    return r


def fig_rtt(r):
    tr = [x for x in r["trace"] if x[3] > 0]
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    ax.step([x[0] for x in tr], [x[3] * 1000 for x in tr], where="post", color=GREEN, label="SRTT")
    ax.step([x[0] for x in tr], [x[4] * 1000 for x in tr], where="post", color=RED, ls="--", label="RTO")
    ax.set_xlabel("timp (s)")
    ax.set_ylabel("ms")
    ax.set_title("Estimarea RTT și timeout-ul (RFC 6298), același transfer TCP Reno", loc="left", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig_rtt.png")
    plt.close(fig)


def fig_compare(path="rezultate/comparatie.csv"):
    if not os.path.exists(path):
        print("lipseste", path, "- ruleaza intai compare.py")
        return
    rows = list(csv.DictReader(open(path)))
    names = {"sw": "Stop-and-Wait", "gbn": "Go-Back-N (N=8)", "sr": "Selective Repeat (N=8)",
             "tahoe": "TCP Tahoe", "reno": "TCP Reno", "newreno": "TCP NewReno"}
    colors = [GRAY, RED, GREEN, PURPLE, ORANGE, BLUE]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    for (m, n), c in zip(names.items(), colors):
        pts = [(float(x["loss"]) * 100, float(x["goodput_kbs"])) for x in rows if x["mode"] == m]
        ax.plot(*zip(*pts), marker="o", ms=4, color=c, label=n)
    ax.set_xlabel("pierdere pe calea de date (%)")
    ax.set_ylabel("goodput (KB/s)")
    ax.set_title("Goodput în funcție de rata de pierdere (media a 5 rulări)", loc="left", fontsize=10)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig_comparatie.png")
    plt.close(fig)


def _box(ax, x, y, w, h, text, color="#2f6fdb", fill="#eef3fc"):
    from matplotlib.patches import FancyBboxPatch
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=fill, ec=color, lw=1.4))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8.5)


def _arrow(ax, x1, y1, x2, y2, text="", color="#444444", dy=0.12):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.2))
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + dy, text, ha="center", fontsize=7.5, color=color)


def fig_arhitectura():
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    _box(ax, 0.2, 4.7, 3.0, 0.9, "Interfața web\nweb/ (HTML + JavaScript)", GRAY, "#f2f2f2")
    _box(ax, 3.9, 4.7, 2.4, 0.9, "server.py\nHTTP + JSON", GRAY, "#f2f2f2")
    _box(ax, 7.0, 4.7, 2.8, 0.9, "run.py, compare.py,\nfairness.py", GRAY, "#f2f2f2")
    _box(ax, 3.0, 3.2, 4.2, 0.9, "session.py\nporneste ambele capete, strange jurnalul")
    _box(ax, 0.2, 1.2, 2.5, 1.3, "Expeditor\nsender.py\n(fereastra, cwnd, timere)")
    _box(ax, 7.3, 1.2, 2.5, 1.3, "Receptor\nreceiver.py\n(buffer, ACK)")
    _box(ax, 3.6, 1.75, 2.8, 0.75, "Link + Router (link.py)\nîntârziere, pierderi, coadă", RED, "#fbeceb")
    _box(ax, 3.6, 0.35, 2.8, 0.7, "Link (link.py)\nîntârziere, pierderi ACK", RED, "#fbeceb")
    _box(ax, 0.4, 0.1, 2.1, 0.7, "packet.py, rtt.py", GREEN, "#e9f5ee")
    _arrow(ax, 3.2, 5.15, 3.9, 5.15, "parametri")
    _arrow(ax, 5.1, 4.7, 5.1, 4.1)
    _arrow(ax, 8.4, 4.7, 6.8, 3.9)
    _arrow(ax, 3.4, 3.4, 1.6, 2.5)
    _arrow(ax, 6.8, 3.4, 8.5, 2.5)
    _arrow(ax, 2.7, 2.12, 3.6, 2.12, "DATA", BLUE)
    _arrow(ax, 6.4, 2.12, 7.3, 2.12, "UDP", BLUE)
    _arrow(ax, 7.3, 1.5, 6.4, 0.7, "ACK", GREEN, dy=-0.2)
    _arrow(ax, 3.6, 0.7, 2.7, 1.5, "UDP", GREEN, dy=-0.2)
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig_arhitectura.png")
    plt.close(fig)


def fig_automat():
    from matplotlib.patches import Circle
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.4)
    ax.axis("off")
    st = {"ÎNCHIS": (1.0, 2.3), "SYN TRIMIS": (3.4, 2.3), "TRANSFER": (6.0, 2.3),
          "FIN TRIMIS": (8.6, 2.3)}
    for name, (x, y) in st.items():
        ax.add_patch(Circle((x, y), 0.72, fc="#eef3fc", ec=BLUE, lw=1.4))
        ax.text(x, y, name, ha="center", va="center", fontsize=8.5, weight="bold")
    _arrow(ax, 1.72, 2.3, 2.68, 2.3, "trimite SYN")
    _arrow(ax, 4.12, 2.3, 5.28, 2.3, "primește SYN-ACK\n/ trimite ACK", dy=0.18)
    _arrow(ax, 6.72, 2.3, 7.88, 2.3, "toate confirmate\n/ trimite FIN", dy=0.18)
    ax.annotate("", xy=(1.0, 1.58), xytext=(8.6, 1.58),
                arrowprops=dict(arrowstyle="-|>", color="#444", lw=1.2, connectionstyle="arc3,rad=-0.25"))
    ax.text(4.8, 0.3, "primește FIN-ACK", ha="center", fontsize=7.5, color="#444")
    for x, t in ((3.4, "timeout / retrimite SYN"), (8.6, "timeout / retrimite FIN")):
        ax.annotate("", xy=(x + 0.3, 3.0), xytext=(x - 0.3, 3.0),
                    arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.1, connectionstyle="arc3,rad=-1.6"))
        ax.text(x, 3.75, t, ha="center", fontsize=7.5, color=RED)
    ax.annotate("", xy=(6.3, 3.0), xytext=(5.7, 3.0),
                arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=1.1, connectionstyle="arc3,rad=-1.6"))
    ax.text(6.0, 3.75, "ACK / timeout / 3 dup ACK\n(bucla principală)", ha="center", fontsize=7.5, color=GREEN)
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig_automat.png")
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    r = fig_reno()
    fig_rtt(r)
    fig_tahoe_vs_reno()
    fig_seq("gbn", "Go-Back-N, pierdere 3%", "fig_seq_gbn.png", size_kb=120, loss=0.03, rate=0, seed=4)
    fig_seq("sr", "Selective Repeat, pierdere 3%", "fig_seq_sr.png", size_kb=120, loss=0.03, rate=0, seed=4)
    fig_compare()
    fig_arhitectura()
    fig_automat()
    print("figurile sunt in", OUT)
