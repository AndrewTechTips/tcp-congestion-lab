const $ = s => document.querySelector(s);
const form = $("#form");
const TCP = ["tahoe", "reno", "newreno"];
const NAMES = {
  sw: "Stop-and-Wait", gbn: "Go-Back-N", sr: "Selective Repeat",
  tahoe: "TCP Tahoe", reno: "TCP Reno", newreno: "TCP NewReno",
};
const PRESETS = {
  clean: { loss: 0, ack_loss: 0, corrupt: 0, rate: 0, queue: 12, size_kb: 400, jitter_ms: 0 },
  congestion: { loss: 0, ack_loss: 0, corrupt: 0, rate: 200, queue: 12, size_kb: 800, jitter_ms: 0 },
  lossy: { loss: 0.03, ack_loss: 0.01, corrupt: 0.01, rate: 0, queue: 12, size_kb: 300, jitter_ms: 0 },
};

let last = null;

// ---------- form ----------

function params() {
  const p = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    p[el.name] = el.name === "mode" ? el.value : Number(el.value);
  }
  return p;
}

function syncOutputs() {
  for (const o of form.querySelectorAll("output[data-for]")) {
    const v = form.elements[o.dataset.for].value;
    o.textContent = num(+(v * 100).toFixed(1)) + "%";
  }
  form.querySelector(".win").style.display =
    ["gbn", "sr"].includes(form.elements.mode.value) ? "" : "none";
}
form.addEventListener("input", syncOutputs);

for (const b of document.querySelectorAll("[data-preset]")) {
  b.addEventListener("click", () => {
    const pr = PRESETS[b.dataset.preset];
    for (const k in pr) form.elements[k].value = pr[k];
    syncOutputs();
  });
}

async function runOnce(p) {
  const res = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(p),
  });
  const r = await res.json();
  if (!res.ok) throw new Error(r.error || res.statusText);
  return r;
}

form.addEventListener("submit", async e => {
  e.preventDefault();
  const st = $("#status");
  $("#go").disabled = true;
  st.className = "status";
  st.textContent = t("sending");
  const t0 = performance.now();
  try {
    last = await runOnce(params());
    st.textContent = t("done_in", { s: num((performance.now() - t0) / 1000, 1) });
    if (last.error) { st.textContent = last.error; st.className = "status err"; }
    renderAll();
    if (fromHash.get("tab") === "ladder") $("#ljump").click();
  } catch (err) {
    st.textContent = t("err", { m: err.message });
    st.className = "status err";
  }
  $("#go").disabled = false;
});

// ---------- tabs ----------

for (const b of document.querySelectorAll(".tabs button")) {
  b.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach(x => x.classList.toggle("active", x === b));
    document.querySelectorAll(".panel").forEach(x => x.classList.toggle("active", x.id === "tab-" + b.dataset.tab));
    renderAll();
  });
}

function renderAll() {
  if (!last) return;
  renderStats(last);
  const tab = document.querySelector(".tabs .active").dataset.tab;
  if (tab === "cwnd") renderCwnd(last);
  if (tab === "seq") renderSeq(last);
  if (tab === "ladder") renderLadder(last);
}

// ---------- stats ----------

function renderStats(r) {
  const s = r.stats;
  const n = x => x.toLocaleString(LANG === "ro" ? "ro-RO" : "en-GB");
  const cards = [
    [r.ok ? t("yes") : t("no"), t("c_ok"), r.ok ? "good" : "bad"],
    [n(s.duration) + " s", t("c_dur")],
    [n(s.goodput_kbs) + " KB/s", t("c_good")],
    [`${s.packets} / ${s.sent}`, t("c_pk")],
    [n(Math.round(s.efficiency * 1000) / 10) + "%", t("c_eff")],
    [s.retx, t("c_retx"), s.retx ? "bad" : ""],
    [s.timeouts, t("c_to")],
    [s.fast_retx, t("c_fr")],
    [`${s.dropped_loss} / ${s.dropped_queue}`, t("c_lost")],
    [`${Math.round(s.final_srtt * 1000)} / ${Math.round(s.final_rto * 1000)} ms`, t("c_rtt")],
  ];
  $("#stats").innerHTML = cards.map(([v, l, c]) =>
    `<div class="stat ${c || ""}"><b>${v}</b><span>${l}</span></div>`).join("");
}

// ---------- congestion window ----------

// how many packets are sent but not yet acknowledged, from the sender's log
function inFlight(r) {
  const out = new Set();
  const pts = [];
  const cumulative = r.params.mode !== "sr";
  for (const e of r.sender) {
    if (e.ev === "send" || e.ev === "retx") out.add(e.seq);
    else if (e.ev === "ack") {
      if (cumulative) { for (const s of out) if (s < e.seq) out.delete(s); }
      else out.delete(e.seq);
    } else if (cumulative && (e.ev === "timeout" ||
               (e.ev === "fast_retx" && r.params.mode === "tahoe"))) {
      out.clear();   // the sender goes back to base and treats the rest as lost
    } else continue;
    pts.push([e.t, out.size]);
  }
  return pts;
}

function endTime(r) {
  return r.times.t_closed || (r.trace.length ? r.trace[r.trace.length - 1][0] : 1);
}

function renderCwnd(r) {
  const mode = r.params.mode;
  const tEnd = endTime(r);
  const flight = inFlight(r);
  const series = [];
  if (TCP.includes(mode)) {
    const cw = r.trace.map(t => [t[0], t[1]]);
    const ss = r.trace.filter(t => t[2] < 900).map(t => [t[0], t[2]]);
    series.push({ type: "step", points: cw, color: css("--c-send"), label: "cwnd", width: 2 });
    series.push({ type: "step", points: ss, color: css("--c-ss"), label: "ssthresh", dash: [6, 4] });
  } else {
    const w = mode === "sw" ? 1 : r.params.window;
    series.push({ type: "step", points: [[0, w], [tEnd, w]], color: css("--c-send"), label: t("fixed_win"), width: 2 });
  }
  series.push({ type: "step", points: flight, color: css("--muted"), label: t("in_flight"), width: 1 });

  const markers = r.sender.filter(e => e.ev === "timeout").map(e => ({ x: e.t, color: css("--c-retx") }))
    .concat(r.sender.filter(e => e.ev === "fast_retx").map(e => ({ x: e.t, color: css("--c-warn") })));
  const yMax = Math.max(4, ...series.flatMap(s => s.points.map(p => p[1]))) * 1.12;

  plot($("#cwnd"), {
    title: t("cwnd_title", { name: NAMES[mode] }),
    xLabel: t("time"), yLabel: t("packets"), xMax: tEnd, yMax, series, markers,
    legendExtra: [
      { label: "timeout", color: css("--c-retx") },
      { label: t("dup3"), color: css("--c-warn") },
    ],
  });

  const rt = r.trace.filter(t => t[3] > 0);
  const rttMax = Math.max(0.05, ...rt.map(t => t[4])) * 1000 * 1.15;
  plot($("#rtt"), {
    title: t("rtt_title"),
    xLabel: t("time"), yLabel: "ms", xMax: tEnd, yMax: rttMax,
    series: [
      { type: "step", points: rt.map(t => [t[0], t[3] * 1000]), color: css("--c-ack"), label: "SRTT" },
      { type: "step", points: rt.map(t => [t[0], t[4] * 1000]), color: css("--c-retx"), label: "RTO", dash: [5, 3] },
    ],
  });
}

// ---------- sequence-time ----------

function renderSeq(r) {
  const sent = [], retx = [], lost = [], acks = [], sack = [];
  for (const e of r.sender) {
    if (e.ev === "send") sent.push([e.t, e.seq]);
    if (e.ev === "retx") retx.push([e.t, e.seq]);
  }
  for (const w of r.wire) {
    if (w.dir === "data" && w.type === 0 && w.drop) lost.push([w.t, w.seq]);
    if (w.dir === "ack" && w.type === 1 && !w.drop) {
      (r.params.mode === "sr" ? sack : acks).push([w.arrive, w.ack]);
    }
  }
  acks.sort((a, b) => a[0] - b[0]);
  sack.sort((a, b) => a[0] - b[0]);
  // the cumulative ACK never goes down, even when old ACKs arrive late
  let hi = 0;
  const ackLine = acks.map(a => [a[0], (hi = Math.max(hi, a[1]))]);

  plot($("#seqplot"), {
    title: t("seq_title", { name: NAMES[r.params.mode] }),
    xLabel: t("time"), yLabel: t("seq_no"), xMax: endTime(r), yMax: r.stats.packets * 1.05,
    series: [
      { type: "step", points: ackLine, color: css("--c-ack"), label: t("cum_ack"), width: 1.5 },
      { type: "dots", points: sack, color: css("--c-ack"), label: sack.length ? t("ind_ack") : "", radius: 1.5 },
      { type: "dots", points: sent, color: css("--c-send"), label: t("sent") },
      { type: "dots", points: retx, color: css("--c-retx"), label: t("resent"), radius: 2.6 },
      { type: "cross", points: lost, color: css("--c-retx"), label: t("lost") },
    ],
  });
}

// ---------- packet diagram ----------

const lstart = $("#lstart"), lspan = $("#lspan");
lstart.addEventListener("input", () => last && renderLadder(last));
lspan.addEventListener("change", () => last && renderLadder(last));
$("#ljump").addEventListener("click", () => {
  if (!last) return;
  const d = last.wire.find(w => w.drop);
  if (!d) { $("#ljump").textContent = t("no_loss"); return; }
  const span = Number(lspan.value);
  lstart.value = Math.max(0, d.t - span * 0.25);
  renderLadder(last);
});

function renderLadder(r) {
  const span = Number(lspan.value);
  const tEnd = endTime(r);
  lstart.max = Math.max(0, tEnd - span * 0.5);
  const a = Number(lstart.value), b = a + span;
  $("#lstart-out").textContent = num(a, 2) + " s";

  const W = 860, H = 640, top = 40, bot = 20;
  const xs = 170, xr = W - 170;
  const Y = t => top + (t - a) / span * (H - top - bot);
  const C = {
    data: css("--c-send"), retx: css("--c-retx"), ack: css("--c-ack"),
    ctl: css("--c4"), muted: css("--muted"), line: css("--line"),
  };
  const names = ["DATA", "ACK", "SYN", "SYN-ACK", "FIN", "FIN-ACK"];
  const seen = {};
  const parts = [];

  parts.push(`<defs>${Object.entries(C).map(([k, c]) =>
    `<marker id="ah-${k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${c}"/></marker>`).join("")}</defs>`);
  parts.push(`<text x="${xs}" y="22" text-anchor="middle" font-weight="600">${t("sender")}</text>`);
  parts.push(`<text x="${xr}" y="22" text-anchor="middle" font-weight="600">${t("receiver")}</text>`);
  parts.push(`<line x1="${xs}" y1="${top}" x2="${xs}" y2="${H - bot}" stroke="${C.muted}" stroke-width="2"/>`);
  parts.push(`<line x1="${xr}" y1="${top}" x2="${xr}" y2="${H - bot}" stroke="${C.muted}" stroke-width="2"/>`);

  // time axis on the left
  const step = niceStep(span, 8);
  for (let tt = Math.ceil(a / step) * step; tt <= b; tt += step) {
    parts.push(`<line x1="40" x2="${W - 40}" y1="${Y(tt)}" y2="${Y(tt)}" stroke="${C.line}" stroke-dasharray="2 4"/>`);
    parts.push(`<text x="36" y="${Y(tt) + 4}" text-anchor="end" fill="${C.muted}">${num(tt, 2)}s</text>`);
  }

  // the sender's timeouts
  for (const e of r.sender) {
    if ((e.ev === "timeout" || e.ev === "fast_retx") && e.t >= a && e.t <= b) {
      const col = e.ev === "timeout" ? C.retx : css("--c-warn");
      const lab = e.ev === "timeout" ? "timeout" : t("dup_ack");
      parts.push(`<circle cx="${xs}" cy="${Y(e.t)}" r="5" fill="none" stroke="${col}" stroke-width="2"/>`);
      parts.push(`<text x="${xs - 70}" y="${Y(e.t) + 4}" text-anchor="end" fill="${col}" font-weight="600">${lab}</text>`);
    }
  }

  // everything on the wire goes into a group clipped to the diagram
  parts.push(`<clipPath id="clipL"><rect x="0" y="${top}" width="${W}" height="${H - top - bot}"/></clipPath><g clip-path="url(#clipL)">`);
  const lastLab = { s: -99, r: -99 };
  let count = 0;
  for (const w of r.wire) {
    const key = w.type + ":" + w.seq;
    const isRetx = w.dir === "data" && w.type === 0 && seen[key];
    seen[key] = true;
    const tArr = w.arrive ?? w.t + r.params.delay_ms / 1000 * 0.45;
    if (tArr < a || w.t > b) continue;
    if (++count > 400) break;   // past this many arrows nobody can read it anyway

    const fromS = w.dir === "data";
    const x1 = fromS ? xs : xr;
    let x2 = fromS ? xr : xs;
    let y2 = Y(tArr);
    const kind = w.type === 0 ? (isRetx ? "retx" : "data") : w.type === 1 ? "ack" : "ctl";
    const col = C[kind];
    if (w.drop) x2 = x1 + (x2 - x1) * 0.45;

    const label = w.type === 0 ? `${isRetx ? "re " : ""}#${w.seq}`
      : w.type === 1 ? `ACK ${w.ack}` : names[w.type];
    parts.push(`<line x1="${x1}" y1="${Y(w.t)}" x2="${x2}" y2="${y2}" stroke="${col}" stroke-width="1.3" ${w.drop ? "" : `marker-end="url(#ah-${kind})"`} ${w.corrupt ? 'stroke-dasharray="4 3"' : ""}/>`);
    if (w.drop) {
      parts.push(`<path d="M${x2 - 6},${y2 - 6} L${x2 + 6},${y2 + 6} M${x2 + 6},${y2 - 6} L${x2 - 6},${y2 + 6}" stroke="${C.retx}" stroke-width="2.2"/>`);
      parts.push(`<text x="${x2 + (fromS ? 10 : -10)}" y="${y2 + 4}" text-anchor="${fromS ? "start" : "end"}" fill="${C.retx}">${w.drop === "queue" ? t("queue_full") : t("lost")}</text>`);
    }
    // label only if it would not overlap the previous one
    const side = fromS ? "s" : "r";
    if (Y(w.t) - lastLab[side] > 12) {
      lastLab[side] = Y(w.t);
      const lx = fromS ? xs - 8 : xr + 8;
      parts.push(`<text x="${lx}" y="${Y(w.t) + 4}" text-anchor="${fromS ? "end" : "start"}" fill="${col}">${label}${w.corrupt ? ` (${t("corrupted")})` : ""}</text>`);
    }
  }
  parts.push("</g>");
  if (!count) parts.push(`<text x="${W / 2}" y="${H / 2}" text-anchor="middle" fill="${C.muted}">${t("empty")}</text>`);

  $("#ladder").innerHTML = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${parts.join("")}</svg>`;
}

// ---------- comparison ----------

$("#cmp-go").addEventListener("click", async () => {
  const btn = $("#cmp-go"), st = $("#cmp-status");
  btn.disabled = true;
  const base = params();
  const modes = Object.keys(NAMES);
  const losses = [0, 0.01, 0.02, 0.05, 0.1];
  const jobs = [];
  for (const m of modes) for (const l of losses) jobs.push({ m, l });
  const results = {};
  let done = 0;
  st.textContent = `0 / ${jobs.length}`;

  // four transfers at a time, the server is multithreaded
  async function worker() {
    while (jobs.length) {
      const { m, l } = jobs.shift();
      const size = Math.min(base.size_kb, 150) / (m === "sw" ? 5 : 1);
      try {
        const r = await runOnce({ ...base, mode: m, loss: l, ack_loss: l / 2, size_kb: size });
        (results[m] ||= {})[l] = r.stats;
      } catch (e) { /* one missing point does not spoil the chart */ }
      st.textContent = `${++done} / ${modes.length * losses.length}`;
      drawCompare(results, modes, losses);
    }
  }
  await Promise.all([worker(), worker(), worker(), worker()]);
  st.textContent = t("done");
  btn.disabled = false;
});

function drawCompare(results, modes, losses) {
  const colors = ["--c1", "--c2", "--c3", "--c4", "--c5", "--c6"].map(css);
  const series = modes.map((m, i) => ({
    type: "line", marks: true, color: colors[i], label: NAMES[m], width: 2,
    points: losses.filter(l => results[m]?.[l]).map(l => [l * 100, results[m][l].goodput_kbs]),
  }));
  const yMax = Math.max(10, ...series.flatMap(s => s.points.map(p => p[1]))) * 1.1;
  plot($("#cmp"), {
    title: t("cmp_title"),
    xLabel: t("loss_axis"), yLabel: "KB/s",
    xMax: 10, yMax, series, hover: false,
  });

  let html = "<table><tr><th>protocol</th>" +
    losses.map(l => `<th>${l * 100}%</th>`).join("") + "</tr>";
  for (const m of modes) {
    html += `<tr><td>${NAMES[m]}</td>` + losses.map(l => {
      const s = results[m]?.[l];
      return `<td>${s ? `${s.goodput_kbs.toFixed(1)} KB/s<br><small>${s.retx} retx, ${s.timeouts} TO</small>` : "…"}</td>`;
    }).join("") + "</tr>";
  }
  $("#cmp-table").innerHTML = html + "</table>";
}

// language switch: redraw everything in the new language
for (const b of document.querySelectorAll("[data-lang]")) b.addEventListener("click", () => setLang(b.dataset.lang));
function onLangChange() { syncOutputs(); renderAll(); }
applyLang();

syncOutputs();
// settings from the link, e.g. index.html#mode=gbn&loss=0.03&tab=ladder&lang=ro
const fromHash = new URLSearchParams(location.hash.slice(1));
for (const [k, v] of fromHash) if (form.elements[k]) form.elements[k].value = v;
syncOutputs();
if (fromHash.get("tab")) document.querySelector(`[data-tab=${fromHash.get("tab")}]`)?.click();
form.requestSubmit();
