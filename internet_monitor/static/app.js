"use strict";

const REFRESH_MS = 30_000;
const SVG_NS = "http://www.w3.org/2000/svg";

const state = { range: "24h", custom: null, report: null };

const $ = (sel) => document.querySelector(sel);
const tooltip = $("#tooltip");

// ---------- formatting ----------

function fmtDuration(seconds) {
  if (seconds == null) return "–";
  seconds = Math.round(seconds);
  if (seconds < 60) return `${seconds}s`;
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m ${s}s`;
}

function fmtPercent(ratio) {
  if (ratio == null) return "–";
  const p = ratio * 100;
  if (p === 100) return "100%";
  return `${p >= 99.99 ? p.toFixed(3) : p.toFixed(2)}%`;
}

function fmtMs(ms) {
  return ms == null ? "–" : `${ms < 10 ? ms.toFixed(1) : Math.round(ms)} ms`;
}

function fmtDateTime(ts) {
  return new Date(ts * 1000).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function fmtTick(ts, span) {
  const d = new Date(ts * 1000);
  if (span <= 86400) return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  if (span <= 3 * 86400) {
    return d.toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function fmtBucketRange(b) {
  const opts = { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" };
  const s = new Date(b.start * 1000);
  const e = new Date(b.end * 1000);
  const sameDay = s.toDateString() === e.toDateString();
  const endStr = sameDay
    ? e.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    : e.toLocaleString(undefined, opts);
  return `${s.toLocaleString(undefined, opts)} – ${endStr}`;
}

function uptimeColor(u) {
  if (u == null) return "var(--nodata)";
  if (u >= 1) return "var(--c100)";
  if (u >= 0.99) return "var(--c99)";
  if (u >= 0.95) return "var(--c95)";
  if (u >= 0.8) return "var(--c80)";
  return "var(--c0)";
}

// ---------- svg helpers ----------

function el(name, attrs = {}, parent) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

function prepareSvg(svg) {
  svg.replaceChildren();
  const w = svg.clientWidth;
  const h = svg.clientHeight;
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  return { w, h };
}

function drawTimeAxis(svg, report, x0, x1, y) {
  const span = report.end - report.start;
  const ticks = Math.max(2, Math.min(8, Math.floor((x1 - x0) / 110)));
  for (let i = 0; i <= ticks; i++) {
    const ts = report.start + (span * i) / ticks;
    const x = x0 + ((x1 - x0) * i) / ticks;
    const anchor = i === 0 ? "start" : i === ticks ? "end" : "middle";
    el("text", { x, y, "text-anchor": anchor }, svg).textContent = fmtTick(ts, span);
  }
}

function showTooltip(evt, html) {
  tooltip.innerHTML = html;
  tooltip.hidden = false;
  const pad = 14;
  const { innerWidth: vw } = window;
  const rect = tooltip.getBoundingClientRect();
  let left = evt.clientX + pad;
  if (left + rect.width > vw - 8) left = evt.clientX - rect.width - pad;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${evt.clientY + pad}px`;
}

function hideTooltip() {
  tooltip.hidden = true;
}

function bucketTooltip(b) {
  if (!b.checks) return `<b>${fmtBucketRange(b)}</b><br>No data (monitor not running)`;
  return `<b>${fmtBucketRange(b)}</b><br>
    Uptime: ${fmtPercent(b.uptime)}<br>
    Failed checks: ${b.failed_checks} / ${b.checks}<br>
    Latency: ${fmtMs(b.avg_latency_ms)} avg, ${fmtMs(b.max_latency_ms)} max`;
}

// ---------- charts ----------

function drawTimeline(report) {
  const svg = $("#timeline");
  const { w, h } = prepareSvg(svg);
  const buckets = report.buckets;
  const top = 4, bottom = h - 22;
  const span = report.end - report.start;
  const xOf = (ts) => ((ts - report.start) / span) * w;

  for (const b of buckets) {
    const x = xOf(b.start);
    const bw = Math.max(1, xOf(b.end) - x);
    const gap = bw > 4 ? 1 : 0;
    const rect = el("rect", {
      class: "bar", x, y: top, width: Math.max(1, bw - gap), height: bottom - top,
      rx: bw > 6 ? 2 : 0, fill: uptimeColor(b.uptime),
    }, svg);
    rect.addEventListener("mousemove", (e) => showTooltip(e, bucketTooltip(b)));
    rect.addEventListener("mouseleave", hideTooltip);
  }
  drawTimeAxis(svg, report, 0, w, h - 6);
}

function niceMax(v) {
  if (v <= 0) return 10;
  const pow = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * pow >= v) return m * pow;
  return 10 * pow;
}

function drawLatency(report) {
  const svg = $("#latency");
  const { w, h } = prepareSvg(svg);
  const left = 48, right = w - 4, top = 8, bottom = h - 22;
  const buckets = report.buckets;
  const values = buckets.map((b) => b.avg_latency_ms).filter((v) => v != null);
  if (!values.length) {
    el("text", { x: w / 2, y: h / 2, "text-anchor": "middle" }, svg).textContent = "No latency data";
    return;
  }
  const sorted = [...values].sort((a, b) => a - b);
  // Scale to the 98th percentile so a single spike doesn't flatten the chart.
  const yMax = niceMax(sorted[Math.floor((sorted.length - 1) * 0.98)] * 1.15);
  const span = report.end - report.start;
  const xOf = (ts) => left + ((ts - report.start) / span) * (right - left);
  const yOf = (v) => bottom - (Math.min(v, yMax) / yMax) * (bottom - top);

  for (let i = 0; i <= 4; i++) {
    const v = (yMax * i) / 4;
    const y = yOf(v);
    el("line", { class: "grid", x1: left, x2: right, y1: y, y2: y }, svg);
    el("text", { x: left - 6, y: y + 4, "text-anchor": "end" }, svg).textContent = `${v} ms`;
  }

  // Split the line into segments wherever there's no data.
  let segments = [], current = [];
  for (const b of buckets) {
    if (b.avg_latency_ms == null) {
      if (current.length) segments.push(current);
      current = [];
    } else {
      current.push([xOf((b.start + b.end) / 2), yOf(b.avg_latency_ms)]);
    }
  }
  if (current.length) segments.push(current);
  for (const seg of segments) {
    const pts = seg.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    if (seg.length === 1) {
      el("circle", { cx: seg[0][0], cy: seg[0][1], r: 2, fill: "var(--accent)" }, svg);
      continue;
    }
    const first = seg[0][0].toFixed(1), last = seg[seg.length - 1][0].toFixed(1);
    el("polygon", { class: "area", points: `${first},${bottom} ${pts} ${last},${bottom}` }, svg);
    el("polyline", { class: "line", points: pts }, svg);
  }
  drawTimeAxis(svg, report, left, right, h - 6);

  const hover = el("line", { class: "hover-line", y1: top, y2: bottom, visibility: "hidden" }, svg);
  const overlay = el("rect", { x: left, y: top, width: right - left, height: bottom - top,
                               fill: "transparent" }, svg);
  overlay.addEventListener("mousemove", (e) => {
    const box = svg.getBoundingClientRect();
    const ts = report.start + ((e.clientX - box.left - left) / (right - left)) * span;
    const b = buckets.find((bk) => ts >= bk.start && ts < bk.end) ?? buckets[buckets.length - 1];
    const x = xOf((b.start + b.end) / 2);
    hover.setAttribute("x1", x);
    hover.setAttribute("x2", x);
    hover.setAttribute("visibility", "visible");
    showTooltip(e, bucketTooltip(b));
  });
  overlay.addEventListener("mouseleave", () => {
    hover.setAttribute("visibility", "hidden");
    hideTooltip();
  });

  const clipped = values.filter((v) => v > yMax).length;
  $("#latency-note").textContent = clipped ? `${clipped} spike(s) above ${yMax} ms clipped` : "";
}

// ---------- page sections ----------

function renderSummary(report) {
  const s = report.summary;
  $("#c-uptime").textContent = fmtPercent(s.uptime);
  $("#c-outages").textContent = s.outages;
  $("#c-downtime").textContent = s.checks ? fmtDuration(s.downtime) : "–";
  $("#c-longest").textContent = s.outages ? fmtDuration(s.longest_outage) : "–";
  $("#c-latency").textContent = fmtMs(s.avg_latency_ms);
  $("#c-checks").textContent = s.checks.toLocaleString();
}

function renderOutages(report) {
  const tbody = $("#outages tbody");
  tbody.replaceChildren();
  const rows = report.outages.slice(0, 500);
  $("#no-outages").hidden = rows.length > 0;
  $("#outages").hidden = rows.length === 0;
  for (const o of rows) {
    const tr = document.createElement("tr");
    const started = document.createElement("td");
    started.textContent = (o.clipped ? "before " : "") + fmtDateTime(o.start);
    const ended = document.createElement("td");
    if (o.ongoing) {
      ended.textContent = "ongoing";
      ended.className = "ongoing";
    } else {
      ended.textContent = fmtDateTime(o.end);
    }
    const dur = document.createElement("td");
    dur.textContent = fmtDuration(o.duration);
    tr.append(started, ended, dur);
    tbody.appendChild(tr);
  }
}

function renderCharts() {
  if (!state.report) return;
  drawTimeline(state.report);
  drawLatency(state.report);
}

async function loadStatus() {
  const box = $("#status");
  try {
    const st = await (await fetch("api/status")).json();
    let cls, text, sub;
    if (!st.monitoring) {
      cls = "unknown";
      text = "Monitor not running";
      sub = st.last_check ? `Last check ${fmtDateTime(st.last_check)}` : "No checks recorded yet";
    } else if (st.online) {
      cls = "online";
      text = `Online · ${fmtMs(st.latency_ms)}`;
      sub = `for ${fmtDuration(st.now - st.since)} · checking every ${st.interval}s`;
    } else {
      cls = "offline";
      text = "Offline";
      sub = `for ${fmtDuration(st.now - st.since)}`;
    }
    box.className = `status ${cls}`;
    box.title = st.detail ?? "";
    $("#status-text").textContent = text;
    $("#status-sub").textContent = sub;
  } catch {
    box.className = "status unknown";
    $("#status-text").textContent = "Dashboard server unreachable";
    $("#status-sub").textContent = "";
  }
}

async function loadReport() {
  const params = new URLSearchParams({ tz_offset: -new Date().getTimezoneOffset() * 60 });
  if (state.range === "custom" && state.custom) {
    params.set("start", state.custom.start);
    params.set("end", state.custom.end);
  } else {
    params.set("range", state.range);
  }
  try {
    const res = await fetch(`api/report?${params}`);
    if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);
    state.report = await res.json();
  } catch (err) {
    console.error(err);
    return;
  }
  renderSummary(state.report);
  renderOutages(state.report);
  renderCharts();
}

function refresh() {
  loadStatus();
  loadReport();
}

// ---------- controls ----------

function toLocalInput(date) {
  const off = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - off).toISOString().slice(0, 16);
}

$("#ranges").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-range]");
  if (!btn) return;
  document.querySelectorAll("#ranges button[data-range]").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  const form = $("#custom");
  if (btn.dataset.range === "custom") {
    form.hidden = false;
    if (!$("#custom-start").value) {
      const now = new Date();
      $("#custom-end").value = toLocalInput(now);
      $("#custom-start").value = toLocalInput(new Date(now - 86400_000));
    }
    return;
  }
  form.hidden = true;
  state.range = btn.dataset.range;
  loadReport();
});

$("#custom").addEventListener("submit", (e) => {
  e.preventDefault();
  const start = new Date($("#custom-start").value).getTime() / 1000;
  const end = new Date($("#custom-end").value).getTime() / 1000;
  if (!(end > start)) return;
  state.range = "custom";
  state.custom = { start, end };
  loadReport();
});

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(renderCharts, 100);
});

refresh();
setInterval(() => {
  loadStatus();
  // Custom ranges are fixed in time, so only rolling ranges need refreshing.
  if (state.range !== "custom") loadReport();
}, REFRESH_MS);
