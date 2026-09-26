/* Grid Pulse dashboard — no build step, no CDN, plain fetch + inline SVG. */

const REPO_RAW = "https://raw.githubusercontent.com/KrishSachdev/grid-pulse/main/data/raw";
const WINDOW_DAYS = 14;
const SVG_NS = "http://www.w3.org/2000/svg";

// ---------- date helpers (calendar-label arithmetic; India has one timezone, no DST) ----------

function istTodayStr() {
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit",
  });
  return fmt.format(new Date()); // "YYYY-MM-DD"
}

function addDaysToDateStr(dateStr, delta) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + delta);
  return dt.toISOString().slice(0, 10);
}

function shortLabel(dateStr) {
  const [, m, d] = dateStr.split("-");
  return `${d}/${m}`;
}

// ---------- data fetch ----------

async function fetchDay(kind, dateStr) {
  const url = `${REPO_RAW}/${kind}/${dateStr}.jsonl`;
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return [];
    const text = await res.text();
    return text
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        try {
          return JSON.parse(l);
        } catch (e) {
          return null;
        }
      })
      .filter(Boolean);
  } catch (e) {
    return [];
  }
}

// ---------- small SVG chart helpers ----------

function el(tag, attrs) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}

function clearSvg(svg) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
}

const CHART_W = 460, CHART_H = 240;
const PAD = { l: 44, r: 12, t: 12, b: 28 };

// Axis range that hugs the data: a round step (1/2/2.5/5 x 10^k) giving about
// 4-5 gridlines, with both ends snapped to that step. (The old version rounded
// the max alone to 1/2/5 x 10^k, so ~32,000 MW became a 50,000 MW axis.)
function niceScale(lo, hi, floorAtZero) {
  if (floorAtZero) lo = 0;
  if (!(hi > lo)) hi = lo + 1;
  const raw = (hi - lo) / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((c) => c >= raw);
  const yMin = Math.max(0, Math.floor(lo / step) * step);
  const yMax = Math.ceil(hi / step) * step;
  return { yMin, yMax, grid: Math.round((yMax - yMin) / step) };
}

function drawAxes(svg, yMax, yMin, xLabels, gridCount = 4) {
  const innerH = CHART_H - PAD.t - PAD.b;
  const innerW = CHART_W - PAD.l - PAD.r;
  for (let i = 0; i <= gridCount; i++) {
    const y = PAD.t + (innerH * i) / gridCount;
    svg.appendChild(el("line", {
      x1: PAD.l, x2: CHART_W - PAD.r, y1: y, y2: y, class: "grid-line",
    }));
    const val = yMax - ((yMax - yMin) * i) / gridCount;
    const label = el("text", { x: PAD.l - 6, y: y + 3, class: "axis-text", "text-anchor": "end" });
    label.textContent = Math.round(val).toLocaleString();
    svg.appendChild(label);
  }
  if (xLabels) {
    const step = Math.max(1, Math.floor(xLabels.length / 7));
    xLabels.forEach((lab, i) => {
      if (i % step !== 0 && i !== xLabels.length - 1) return;
      const x = PAD.l + (innerW * i) / Math.max(1, xLabels.length - 1);
      const t = el("text", { x, y: CHART_H - 8, class: "axis-text", "text-anchor": "middle" });
      t.textContent = lab;
      svg.appendChild(t);
    });
  }
  return { innerW, innerH };
}

function lineChart(svg, series, xLabels) {
  clearSvg(svg);
  const allVals = series.flatMap((s) => s.values.filter((v) => v !== null && v !== undefined));
  if (!allVals.length) {
    svg.appendChild(el("text", { x: CHART_W / 2, y: CHART_H / 2, class: "axis-text", "text-anchor": "middle" }))
      .textContent = "No data";
    return;
  }
  const rawMax = Math.max(...allVals);
  const rawMin = Math.min(...allVals);
  const { yMin, yMax, grid } = niceScale(rawMin * 0.97, rawMax * 1.03);
  const n = series[0].values.length;
  const { innerW, innerH } = drawAxes(svg, yMax, yMin, xLabels, grid);

  series.forEach((s) => {
    let d = "";
    let started = false;
    s.values.forEach((v, i) => {
      const x = PAD.l + (innerW * i) / Math.max(1, n - 1);
      if (v === null || v === undefined) {
        started = false;
        return;
      }
      const y = PAD.t + innerH - ((v - yMin) / (yMax - yMin || 1)) * innerH;
      d += (started ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1) + " ";
      started = true;
    });
    svg.appendChild(el("path", { d, fill: "none", stroke: s.color, "stroke-width": 2 }));
  });
}

function barChart(svg, values, xLabels, colorFn) {
  clearSvg(svg);
  const nonNull = values.filter((v) => v !== null && v !== undefined);
  if (!nonNull.length) {
    const t = el("text", { x: CHART_W / 2, y: CHART_H / 2, class: "axis-text", "text-anchor": "middle" });
    t.textContent = "No data";
    svg.appendChild(t);
    return;
  }
  const rawMax = Math.max(...nonNull);
  const { yMin, yMax, grid } = niceScale(0, rawMax * 1.05, true);
  const { innerW, innerH } = drawAxes(svg, yMax, yMin, xLabels, grid);
  const n = values.length;
  const bw = (innerW / n) * 0.6;
  values.forEach((v, i) => {
    if (v === null || v === undefined) return;
    const cx = PAD.l + (innerW * (i + 0.5)) / n;
    const h = ((v - yMin) / (yMax - yMin || 1)) * innerH;
    const y = PAD.t + innerH - h;
    svg.appendChild(el("rect", {
      x: cx - bw / 2, y, width: bw, height: Math.max(1, h),
      fill: colorFn ? colorFn(v, i) : "var(--accent)", rx: 2,
    }));
  });
}

function scatterChart(svg, points) {
  clearSvg(svg);
  if (!points.length) {
    const t = el("text", { x: CHART_W / 2, y: CHART_H / 2, class: "axis-text", "text-anchor": "middle" });
    t.textContent = "No data";
    svg.appendChild(t);
    return;
  }
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xMax = Math.max(...xs) + 1, xMin = Math.min(...xs) - 1;
  const { yMin, yMax, grid: gridCount } = niceScale(Math.min(...ys) * 0.97, Math.max(...ys) * 1.03);
  const innerH = CHART_H - PAD.t - PAD.b;
  const innerW = CHART_W - PAD.l - PAD.r;

  // y grid + labels (reuse drawAxes logic minus x labels, then add x-axis temp labels manually)
  for (let i = 0; i <= gridCount; i++) {
    const y = PAD.t + (innerH * i) / gridCount;
    svg.appendChild(el("line", { x1: PAD.l, x2: CHART_W - PAD.r, y1: y, y2: y, class: "grid-line" }));
    const val = yMax - ((yMax - yMin) * i) / gridCount;
    const label = el("text", { x: PAD.l - 6, y: y + 3, class: "axis-text", "text-anchor": "end" });
    label.textContent = Math.round(val).toLocaleString();
    svg.appendChild(label);
  }
  for (let i = 0; i <= 4; i++) {
    const x = PAD.l + (innerW * i) / 4;
    const val = xMin + ((xMax - xMin) * i) / 4;
    const t = el("text", { x, y: CHART_H - 8, class: "axis-text", "text-anchor": "middle" });
    t.textContent = val.toFixed(0) + "°";
    svg.appendChild(t);
  }

  points.forEach((p) => {
    const x = PAD.l + ((p.x - xMin) / (xMax - xMin || 1)) * innerW;
    const y = PAD.t + innerH - ((p.y - yMin) / (yMax - yMin || 1)) * innerH;
    svg.appendChild(el("circle", { cx: x, cy: y, r: 2.4, fill: "var(--accent)", opacity: 0.55 }));
  });
}

// ---------- data shaping ----------

function hourlySeries(records) {
  const arr = new Array(24).fill(null);
  for (const r of records) {
    if (r.ok && typeof r.demand_met_mw === "number" && r.slot) {
      const h = parseInt(r.slot.slice(11, 13), 10);
      arr[h] = r.demand_met_mw;
    }
  }
  return arr;
}

function dailyPeak(records) {
  const oks = records.filter((r) => r.ok && typeof r.demand_met_mw === "number");
  if (!oks.length) return null;
  return Math.max(...oks.map((r) => r.demand_met_mw));
}

// Hours a day could have had so far: 24 for past days, only the hours already
// started for today (IST). Without this, today always looked "mostly missed".
function expectedHours(dateStr) {
  if (dateStr !== istTodayStr()) return 24;
  const h = Number(new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata", hour: "2-digit", hour12: false,
  }).format(new Date()));
  return Math.max(1, (h % 24) + 1);
}

function hoursCaptured(records) {
  const hours = new Set();
  for (const r of records) if (r.ok && r.slot) hours.add(r.slot.slice(11, 13));
  return hours.size;
}

function latestOkRecord(records) {
  let best = null;
  for (const r of records) {
    if (r.ok && r.ts_ist && (!best || r.ts_ist > best.ts_ist)) best = r;
  }
  return best;
}

// ---------- main ----------

async function main() {
  const statusEl = document.getElementById("status");
  try {
    const today = istTodayStr();
    const days = [];
    for (let i = WINDOW_DAYS - 1; i >= 0; i--) days.push(addDaysToDateStr(today, -i));

    const demandByDay = {};
    const weatherByDay = {};
    await Promise.all(
      days.map(async (d) => {
        const [dem, wea] = await Promise.all([fetchDay("demand", d), fetchDay("weather", d)]);
        demandByDay[d] = dem;
        weatherByDay[d] = wea;
      })
    );

    // find latest day that actually has demand data (today's file may not exist yet)
    let latestDay = null;
    for (let i = days.length - 1; i >= 0; i--) {
      if ((demandByDay[days[i]] || []).some((r) => r.ok)) {
        latestDay = days[i];
        break;
      }
    }
    if (!latestDay) throw new Error("No demand data found in the last " + WINDOW_DAYS + " days.");

    const lastWeekDay = addDaysToDateStr(latestDay, -7);
    if (!(lastWeekDay in demandByDay)) {
      demandByDay[lastWeekDay] = await fetchDay("demand", lastWeekDay);
    }

    // --- chart 1: today vs last week ---
    const todaySeries = hourlySeries(demandByDay[latestDay] || []);
    const lastWeekSeries = hourlySeries(demandByDay[lastWeekDay] || []);
    document.getElementById("legToday").textContent = latestDay;
    document.getElementById("legLastWeek").textContent = lastWeekDay;
    const hourLabels = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, "0"));
    lineChart(
      document.getElementById("chartWeek"),
      [
        { values: todaySeries, color: "var(--accent)" },
        { values: lastWeekSeries, color: "var(--accent-2)" },
      ],
      hourLabels
    );

    // --- chart 2: daily peak trend ---
    const peaks = days.map((d) => dailyPeak(demandByDay[d] || []));
    barChart(document.getElementById("chartPeak"), peaks, days.map(shortLabel), () => "var(--accent)");

    // --- health strip ---
    const stripEl = document.getElementById("healthStrip");
    stripEl.innerHTML = "";
    days.forEach((d) => {
      const hrs = hoursCaptured(demandByDay[d] || []);
      const exp = expectedHours(d);
      const cell = document.createElement("div");
      cell.className = "health-cell" + (d === today ? " today" : "");
      // judge by the share of expected hours; the latest hour may still be in flight
      const share = Math.min(hrs + 1, exp) / exp;
      let color = "var(--bad)";
      if (share >= 22 / 24) color = "var(--good)";
      else if (share >= 0.5) color = "var(--warn)";
      cell.style.background = color;
      cell.title = d === today ? `${d} (today so far): ${hrs}/${exp} hours` : `${d}: ${hrs}/24 hours`;
      const lbl = document.createElement("div");
      lbl.className = "lbl";
      lbl.textContent = shortLabel(d);
      cell.appendChild(lbl);
      stripEl.appendChild(cell);
    });

    // --- scatter: temp vs demand ---
    const points = [];
    days.forEach((d) => {
      const tempByHour = {};
      for (const r of weatherByDay[d] || []) {
        if (r.ok && typeof r.temp_c === "number" && r.slot) tempByHour[r.slot.slice(11, 13)] = r.temp_c;
      }
      for (const r of demandByDay[d] || []) {
        if (r.ok && typeof r.demand_met_mw === "number" && r.slot) {
          const h = r.slot.slice(11, 13);
          if (h in tempByHour) points.push({ x: tempByHour[h], y: r.demand_met_mw });
        }
      }
    });
    scatterChart(document.getElementById("chartScatter"), points);

    // --- stat row ---
    let mostRecent = null;
    for (const d of days) {
      const rec = latestOkRecord(demandByDay[d] || []);
      if (rec && (!mostRecent || rec.ts_ist > mostRecent.ts_ist)) mostRecent = rec;
    }
    document.getElementById("statLatestDemand").textContent = mostRecent
      ? mostRecent.demand_met_mw.toLocaleString()
      : "–";
    const todayPeak = dailyPeak(demandByDay[latestDay] || []);
    document.getElementById("statPeak").textContent = todayPeak ? todayPeak.toLocaleString() : "–";
    if (latestDay === today) document.getElementById("statPeakLabel").textContent = "Peak so far today (MW)";
    else document.getElementById("statPeakLabel").textContent = `Peak on ${shortLabel(latestDay)} (MW)`;
    // coverage and full days count only hours that could have been collected
    const totalHours = days.reduce((sum, d) => sum + Math.min(hoursCaptured(demandByDay[d] || []), expectedHours(d)), 0);
    const totalExpected = days.reduce((sum, d) => sum + expectedHours(d), 0);
    document.getElementById("statCoverage").textContent =
      Math.round((100 * totalHours) / totalExpected) + "%";
    const pastDays = days.filter((d) => d !== today);
    const fullDays = pastDays.filter((d) => hoursCaptured(demandByDay[d] || []) >= 22).length;
    document.getElementById("statDays").textContent = `${fullDays}/${pastDays.length}`;
    document.getElementById("statRow").style.display = "flex";

    // --- last updated + status ---
    if (mostRecent) {
      document.getElementById("lastUpdated").textContent =
        "Last updated: " + mostRecent.ts_ist.replace("T", " ") + " (source's last successful reading)";
    }
    statusEl.style.display = "none";
  } catch (err) {
    statusEl.className = "status-line error";
    statusEl.textContent =
      "Could not load live data from GitHub (" + err.message + "). This page fetches directly from " +
      "raw.githubusercontent.com — check your connection or try again shortly.";
  }
}

main();
