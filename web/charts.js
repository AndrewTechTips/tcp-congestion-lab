// Small canvas charts. No libraries, so it also works offline.

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function niceStep(range, count) {
  const raw = range / count;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const f = raw / p;
  return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p;
}

function fmt(v) {
  if (Math.abs(v) >= 100 || Number.isInteger(v)) return String(Math.round(v));
  return num(+v.toFixed(2));
}

// value of a step series at time x
function stepAt(points, x) {
  let v = null;
  for (const p of points) {
    if (p[0] > x) break;
    v = p[1];
  }
  return v;
}

function plot(canvas, opt) {
  canvas._opt = opt;
  draw(canvas);
  if (!canvas._wired) {
    canvas._wired = true;
    canvas.addEventListener("mousemove", e => {
      const r = canvas.getBoundingClientRect();
      canvas._hover = e.clientX - r.left;
      draw(canvas);
    });
    canvas.addEventListener("mouseleave", () => { canvas._hover = null; draw(canvas); });
    window.addEventListener("resize", () => canvas._opt && draw(canvas));
  }
}

function draw(canvas) {
  const opt = canvas._opt;
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth;
  const H = canvas.height / (canvas._dpr || 1);
  canvas._dpr = dpr;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  canvas.style.height = H + "px";
  const g = canvas.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, W, H);

  const m = { l: 52, r: 16, t: opt.title ? 30 : 14, b: 40 };
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  const xMin = opt.xMin ?? 0, yMin = opt.yMin ?? 0;
  const xMax = opt.xMax || 1, yMax = opt.yMax || 1;
  const X = x => m.l + (x - xMin) / (xMax - xMin) * pw;
  const Y = y => m.t + ph - (y - yMin) / (yMax - yMin) * ph;

  g.font = "12px -apple-system, 'Segoe UI', Roboto, sans-serif";
  if (opt.title) {
    g.fillStyle = css("--text");
    g.fillText(opt.title, m.l, 18);
  }

  // grid and axes
  g.strokeStyle = css("--grid");
  g.fillStyle = css("--muted");
  g.lineWidth = 1;
  const xs = opt.xTicks || niceStep(xMax - xMin, Math.max(3, pw / 90));
  for (let x = Math.ceil(xMin / xs) * xs; x <= xMax + 1e-9; x += xs) {
    g.beginPath(); g.moveTo(X(x), m.t); g.lineTo(X(x), m.t + ph); g.stroke();
    g.textAlign = "center";
    g.fillText((opt.xFmt || fmt)(x), X(x), m.t + ph + 15);
  }
  const ys = niceStep(yMax - yMin, Math.max(3, ph / 50));
  for (let y = Math.ceil(yMin / ys) * ys; y <= yMax + 1e-9; y += ys) {
    g.beginPath(); g.moveTo(m.l, Y(y)); g.lineTo(m.l + pw, Y(y)); g.stroke();
    g.textAlign = "right";
    g.fillText(fmt(y), m.l - 6, Y(y) + 4);
  }
  g.strokeStyle = css("--muted");
  g.beginPath(); g.moveTo(m.l, m.t); g.lineTo(m.l, m.t + ph); g.lineTo(m.l + pw, m.t + ph); g.stroke();
  g.textAlign = "center";
  g.fillText(opt.xLabel || "", m.l + pw / 2, H - 6);
  g.save();
  g.translate(13, m.t + ph / 2); g.rotate(-Math.PI / 2);
  g.fillText(opt.yLabel || "", 0, 0);
  g.restore();

  g.save();
  g.beginPath(); g.rect(m.l, m.t - 2, pw, ph + 4); g.clip();

  // vertical markers (timeout, fast retransmit)
  for (const mk of opt.markers || []) {
    g.strokeStyle = mk.color;
    g.globalAlpha = 0.35;
    g.setLineDash([3, 3]);
    g.beginPath(); g.moveTo(X(mk.x), m.t); g.lineTo(X(mk.x), m.t + ph); g.stroke();
    g.setLineDash([]);
    g.globalAlpha = 1;
  }

  for (const s of opt.series) {
    const pts = s.points;
    if (!pts.length) continue;
    g.strokeStyle = g.fillStyle = s.color;
    g.lineWidth = s.width || 1.6;
    g.setLineDash(s.dash || []);
    if (s.type === "dots") {
      const r = s.radius || 1.8;
      for (const p of pts) {
        g.beginPath(); g.arc(X(p[0]), Y(p[1]), r, 0, 7); g.fill();
      }
    } else if (s.type === "cross") {
      const r = s.radius || 3;
      g.lineWidth = 1.3;
      for (const p of pts) {
        const x = X(p[0]), y = Y(p[1]);
        g.beginPath(); g.moveTo(x - r, y - r); g.lineTo(x + r, y + r);
        g.moveTo(x + r, y - r); g.lineTo(x - r, y + r); g.stroke();
      }
    } else {
      g.beginPath();
      g.moveTo(X(pts[0][0]), Y(pts[0][1]));
      for (let i = 1; i < pts.length; i++) {
        if (s.type === "step") g.lineTo(X(pts[i][0]), Y(pts[i - 1][1]));
        g.lineTo(X(pts[i][0]), Y(pts[i][1]));
      }
      if (s.type === "step" && opt.xMax) g.lineTo(X(xMax), Y(pts[pts.length - 1][1]));
      g.stroke();
      if (s.marks) {
        for (const p of pts) { g.beginPath(); g.arc(X(p[0]), Y(p[1]), 3, 0, 7); g.fill(); }
      }
    }
    g.setLineDash([]);
  }
  g.restore();

  // legend
  let lx = m.l + 8;
  const ly = m.t + 10;
  g.textAlign = "left";
  for (const s of opt.series.concat(opt.legendExtra || [])) {
    if (!s.label) continue;
    g.fillStyle = s.color;
    g.fillRect(lx, ly - 5, 12, 3);
    g.fillStyle = css("--text");
    g.fillText(s.label, lx + 16, ly);
    lx += g.measureText(s.label).width + 34;
  }

  // values under the cursor
  const hx = canvas._hover;
  if (hx != null && hx >= m.l && hx <= m.l + pw && opt.hover !== false) {
    const x = xMin + (hx - m.l) / pw * (xMax - xMin);
    g.strokeStyle = css("--muted");
    g.beginPath(); g.moveTo(hx, m.t); g.lineTo(hx, m.t + ph); g.stroke();
    const lines = [(opt.xLabel || "x") + ": " + fmt(x)];
    for (const s of opt.series) {
      if (!s.label || s.type === "dots" || s.type === "cross") continue;
      const v = stepAt(s.points, x);
      if (v != null) lines.push(s.label + ": " + fmt(v));
    }
    const bw = Math.max(...lines.map(l => g.measureText(l).width)) + 14;
    const bx = hx + bw + 12 > W ? hx - bw - 8 : hx + 8;
    g.fillStyle = css("--panel");
    g.strokeStyle = css("--line");
    g.fillRect(bx, m.t + 20, bw, lines.length * 16 + 8);
    g.strokeRect(bx, m.t + 20, bw, lines.length * 16 + 8);
    g.fillStyle = css("--text");
    lines.forEach((l, i) => g.fillText(l, bx + 7, m.t + 36 + i * 16));
  }
}
