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

// ---------- formular ----------

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
    o.textContent = (v * 100).toFixed(1).replace(".0", "").replace(".", ",") + "%";
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
  st.textContent = "se transferă...";
  const t = performance.now();
  try {
    last = await runOnce(params());
    st.textContent = `gata în ${((performance.now() - t) / 1000).toFixed(1)} s`;
    if (last.error) { st.textContent = last.error; st.className = "status err"; }
    renderAll();
    if (fromHash.get("tab") === "ladder") $("#ljump").click();
  } catch (err) {
    st.textContent = "eroare: " + err.message + " (e pornit server.py?)";
    st.className = "status err";
  }
  $("#go").disabled = false;
});

// ---------- taburi ----------

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

// ---------- statistici ----------

function renderStats(r) {
  const s = r.stats;
  const n = x => x.toLocaleString("ro-RO");
  const cards = [
    [r.ok ? "da" : "NU", "fișier primit identic", r.ok ? "good" : "bad"],
    [n(s.duration) + " s", "durata transferului"],
    [n(s.goodput_kbs) + " KB/s", "goodput (date utile)"],
    [`${s.packets} / ${s.sent}`, "pachete utile / trimise"],
    [n(Math.round(s.efficiency * 1000) / 10) + "%", "eficiență"],
    [s.retx, "retransmisii", s.retx ? "bad" : ""],
    [s.timeouts, "timeout-uri"],
    [s.fast_retx, "fast retransmit"],
    [`${s.dropped_loss} / ${s.dropped_queue}`, "pierdute: aleator / coadă"],
    [`${Math.round(s.final_srtt * 1000)} / ${Math.round(s.final_rto * 1000)} ms`, "SRTT / RTO final"],
  ];
  $("#stats").innerHTML = cards.map(([v, l, c]) =>
    `<div class="stat ${c || ""}"><b>${v}</b><span>${l}</span></div>`).join("");
}

// ---------- fereastra de congestie ----------

// cate pachete sunt trimise si inca neconfirmate, din jurnalul expeditorului
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
      out.clear();   // expeditorul o ia de la base, restul le considera pierdute
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
    series.push({ type: "step", points: [[0, w], [tEnd, w]], color: css("--c-send"), label: "fereastra (fixă)", width: 2 });
  }
  series.push({ type: "step", points: flight, color: css("--muted"), label: "pachete în zbor", width: 1 });

  const markers = r.sender.filter(e => e.ev === "timeout").map(e => ({ x: e.t, color: css("--c-retx") }))
    .concat(r.sender.filter(e => e.ev === "fast_retx").map(e => ({ x: e.t, color: css("--c-warn") })));
  const yMax = Math.max(4, ...series.flatMap(s => s.points.map(p => p[1]))) * 1.12;

  plot($("#cwnd"), {
    title: `${NAMES[mode]}: fereastra în timp`,
    xLabel: "timp (s)", yLabel: "pachete", xMax: tEnd, yMax, series, markers,
    legendExtra: [
      { label: "timeout", color: css("--c-retx") },
      { label: "3 ACK duplicate", color: css("--c-warn") },
    ],
  });

  const rt = r.trace.filter(t => t[3] > 0);
  const rttMax = Math.max(0.05, ...rt.map(t => t[4])) * 1000 * 1.15;
  plot($("#rtt"), {
    title: "Estimarea RTT (RFC 6298)",
    xLabel: "timp (s)", yLabel: "ms", xMax: tEnd, yMax: rttMax,
    series: [
      { type: "step", points: rt.map(t => [t[0], t[3] * 1000]), color: css("--c-ack"), label: "SRTT" },
      { type: "step", points: rt.map(t => [t[0], t[4] * 1000]), color: css("--c-retx"), label: "RTO", dash: [5, 3] },
    ],
  });
}

// ---------- secventa-timp ----------

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
  // ACK-ul cumulativ nu scade niciodata, chiar daca ajung ACK-uri vechi mai tarziu
  let hi = 0;
  const ackLine = acks.map(a => [a[0], (hi = Math.max(hi, a[1]))]);

  plot($("#seqplot"), {
    title: `${NAMES[r.params.mode]}: numărul de secvență în timp`,
    xLabel: "timp (s)", yLabel: "nr. pachet", xMax: endTime(r), yMax: r.stats.packets * 1.05,
    series: [
      { type: "step", points: ackLine, color: css("--c-ack"), label: "ACK cumulativ", width: 1.5 },
      { type: "dots", points: sack, color: css("--c-ack"), label: sack.length ? "ACK individual" : "", radius: 1.5 },
      { type: "dots", points: sent, color: css("--c-send"), label: "trimis" },
      { type: "dots", points: retx, color: css("--c-retx"), label: "retrimis", radius: 2.6 },
      { type: "cross", points: lost, color: css("--c-retx"), label: "pierdut" },
    ],
  });
}

// ---------- diagrama pachetelor ----------

const lstart = $("#lstart"), lspan = $("#lspan");
lstart.addEventListener("input", () => last && renderLadder(last));
lspan.addEventListener("change", () => last && renderLadder(last));
$("#ljump").addEventListener("click", () => {
  if (!last) return;
  const d = last.wire.find(w => w.drop);
  if (!d) { $("#ljump").textContent = "nicio pierdere"; return; }
  const span = Number(lspan.value);
  lstart.value = Math.max(0, d.t - span * 0.25);
  renderLadder(last);
});

function renderLadder(r) {
  const span = Number(lspan.value);
  const tEnd = endTime(r);
  lstart.max = Math.max(0, tEnd - span * 0.5);
  const a = Number(lstart.value), b = a + span;
  $("#lstart-out").textContent = a.toFixed(2).replace(".", ",") + " s";

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
  parts.push(`<text x="${xs}" y="22" text-anchor="middle" font-weight="600">Expeditor</text>`);
  parts.push(`<text x="${xr}" y="22" text-anchor="middle" font-weight="600">Receptor</text>`);
  parts.push(`<line x1="${xs}" y1="${top}" x2="${xs}" y2="${H - bot}" stroke="${C.muted}" stroke-width="2"/>`);
  parts.push(`<line x1="${xr}" y1="${top}" x2="${xr}" y2="${H - bot}" stroke="${C.muted}" stroke-width="2"/>`);

  // axa timpului in stanga
  const step = niceStep(span, 8);
  for (let t = Math.ceil(a / step) * step; t <= b; t += step) {
    parts.push(`<line x1="40" x2="${W - 40}" y1="${Y(t)}" y2="${Y(t)}" stroke="${C.line}" stroke-dasharray="2 4"/>`);
    parts.push(`<text x="36" y="${Y(t) + 4}" text-anchor="end" fill="${C.muted}">${t.toFixed(2).replace(".", ",")}s</text>`);
  }

  // timeout-urile expeditorului
  for (const e of r.sender) {
    if ((e.ev === "timeout" || e.ev === "fast_retx") && e.t >= a && e.t <= b) {
      const col = e.ev === "timeout" ? C.retx : css("--c-warn");
      const lab = e.ev === "timeout" ? "timeout" : "3 dup ACK";
      parts.push(`<circle cx="${xs}" cy="${Y(e.t)}" r="5" fill="none" stroke="${col}" stroke-width="2"/>`);
      parts.push(`<text x="${xs - 70}" y="${Y(e.t) + 4}" text-anchor="end" fill="${col}" font-weight="600">${lab}</text>`);
    }
  }

  // tot ce e pe fir il desenam intr-un grup taiat la marginile diagramei
  parts.push(`<clipPath id="clipL"><rect x="0" y="${top}" width="${W}" height="${H - top - bot}"/></clipPath><g clip-path="url(#clipL)">`);
  const lastLab = { s: -99, r: -99 };
  let count = 0;
  for (const w of r.wire) {
    const key = w.type + ":" + w.seq;
    const isRetx = w.dir === "data" && w.type === 0 && seen[key];
    seen[key] = true;
    const tArr = w.arrive ?? w.t + r.params.delay_ms / 1000 * 0.45;
    if (tArr < a || w.t > b) continue;
    if (++count > 400) break;   // prea multe sageti nu mai inseamna nimic

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
      parts.push(`<text x="${x2 + (fromS ? 10 : -10)}" y="${y2 + 4}" text-anchor="${fromS ? "start" : "end"}" fill="${C.retx}">${w.drop === "queue" ? "coadă plină" : "pierdut"}</text>`);
    }
    // eticheta doar daca nu se suprapune peste cea de dinainte
    const side = fromS ? "s" : "r";
    if (Y(w.t) - lastLab[side] > 12) {
      lastLab[side] = Y(w.t);
      const lx = fromS ? xs - 8 : xr + 8;
      parts.push(`<text x="${lx}" y="${Y(w.t) + 4}" text-anchor="${fromS ? "end" : "start"}" fill="${col}">${label}${w.corrupt ? " (corupt)" : ""}</text>`);
    }
  }
  parts.push("</g>");
  if (!count) parts.push(`<text x="${W / 2}" y="${H / 2}" text-anchor="middle" fill="${C.muted}">nimic pe fir în intervalul ăsta</text>`);

  $("#ladder").innerHTML = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${parts.join("")}</svg>`;
}

// ---------- comparatie ----------

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

  // cate 4 transferuri deodata, serverul e multithread
  async function worker() {
    while (jobs.length) {
      const { m, l } = jobs.shift();
      const size = Math.min(base.size_kb, 150) / (m === "sw" ? 5 : 1);
      try {
        const r = await runOnce({ ...base, mode: m, loss: l, ack_loss: l / 2, size_kb: size });
        (results[m] ||= {})[l] = r.stats;
      } catch (e) { /* un punct lipsa nu strica graficul */ }
      st.textContent = `${++done} / ${modes.length * losses.length}`;
      drawCompare(results, modes, losses);
    }
  }
  await Promise.all([worker(), worker(), worker(), worker()]);
  st.textContent = "gata";
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
    title: "Goodput în funcție de rata de pierdere",
    xLabel: "pierdere pe calea de date (%)", yLabel: "KB/s",
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

syncOutputs();
// parametri din link, de ex. index.html#mode=gbn&loss=0.03&tab=ladder
const fromHash = new URLSearchParams(location.hash.slice(1));
for (const [k, v] of fromHash) if (form.elements[k]) form.elements[k].value = v;
syncOutputs();
if (fromHash.get("tab")) document.querySelector(`[data-tab=${fromHash.get("tab")}]`)?.click();
form.requestSubmit();
