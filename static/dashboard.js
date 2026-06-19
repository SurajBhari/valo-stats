/* dashboard.js — renders interactive Chart.js charts from embedded report data. */
"use strict";

const DATA = JSON.parse(document.getElementById("report-data").textContent);

const RED = "#ff4655";
const RED_SOFT = "rgba(255,70,85,0.55)";
const BLUE = "#4aa8ff";
const GRID = "rgba(255,255,255,0.06)";

Chart.defaults.color = "#8a90a2";
Chart.defaults.font.family = '"Segoe UI", system-ui, Arial, sans-serif';
Chart.defaults.borderColor = GRID;

function mk(id, config) {
  const el = document.getElementById(id);
  if (!el) return;
  config.options = config.options || {};
  config.options.responsive = true;
  config.options.maintainAspectRatio = false;
  new Chart(el, config);
}

function gridScale(extra) {
  return Object.assign({ grid: { color: GRID }, ticks: {} }, extra || {});
}

/* ── Trends: winrate (left axis) + ACS (right axis) ──────────── */
(function () {
  const t = DATA.trends || [];
  if (!t.length) return;
  mk("c-trends", {
    type: "line",
    data: {
      labels: t.map(x => x.month),
      datasets: [
        { label: "Winrate %", data: t.map(x => x.winrate), borderColor: RED,
          backgroundColor: RED_SOFT, yAxisID: "y", tension: 0.3, fill: false, pointRadius: 3 },
        { label: "ACS", data: t.map(x => x.acs), borderColor: BLUE,
          yAxisID: "y1", tension: 0.3, fill: false, pointRadius: 3 },
      ],
    },
    options: {
      interaction: { mode: "index", intersect: false },
      scales: {
        y: gridScale({ position: "left", min: 0, max: 100, title: { display: true, text: "Winrate %" } }),
        y1: gridScale({ position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "ACS" } }),
        x: gridScale(),
      },
      plugins: { legend: { labels: { boxWidth: 12 } } },
    },
  });
})();

/* ── Helper: horizontal winrate bar with games in tooltip ─────── */
function winrateBar(id, rows, labelKey) {
  if (!rows || !rows.length) return;
  mk(id, {
    type: "bar",
    data: {
      labels: rows.map(r => r[labelKey]),
      datasets: [{
        label: "Winrate %",
        data: rows.map(r => r.winrate),
        backgroundColor: RED_SOFT,
        borderColor: RED,
        borderWidth: 1,
        games: rows.map(r => r.matches),
      }],
    },
    options: {
      indexAxis: "y",
      scales: { x: gridScale({ min: 0, max: 100 }), y: gridScale() },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.parsed.x}% winrate · ${ctx.dataset.games[ctx.dataIndex]} games`,
          },
        },
      },
    },
  });
}

winrateBar("c-maps", DATA.per_map, "name");
winrateBar("c-agents", DATA.per_agent, "name");

/* ── Weapons: top kills (vertical bar) ───────────────────────── */
(function () {
  const w = (DATA.detail && DATA.detail.weapons) || [];
  const top = w.slice(0, 10);
  if (!top.length) return;
  mk("c-weapons", {
    type: "bar",
    data: {
      labels: top.map(x => x.name),
      datasets: [{ label: "Kills", data: top.map(x => x.kills),
                   backgroundColor: RED_SOFT, borderColor: RED, borderWidth: 1 }],
    },
    options: { scales: { x: gridScale(), y: gridScale({ beginAtZero: true }) },
               plugins: { legend: { display: false } } },
  });
})();

/* ── Shot placement: doughnut ────────────────────────────────── */
(function () {
  const s = DATA.weapons_shots || {};
  const total = (s.head || 0) + (s.body || 0) + (s.leg || 0);
  if (!total) return;
  mk("c-shots", {
    type: "doughnut",
    data: {
      labels: ["Head", "Body", "Legs"],
      datasets: [{ data: [s.head, s.body, s.leg],
                   backgroundColor: [RED, "#ff8a93", "#5c6173"], borderColor: "#1c1f27", borderWidth: 2 }],
    },
    options: {
      cutout: "58%",
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12 } },
        tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${ctx.parsed} (${(ctx.parsed / total * 100).toFixed(1)}%)` } },
      },
    },
  });
})();

/* ── Activity bucketed in the VIEWER'S LOCAL timezone ─────────────
   Re-bucket raw match samples ([timestamp, won]) using the browser's local
   time (JS Date getHours/getDay are local), so IST users see IST, etc. */
function _winrate(w, g) { return g ? Math.round(w / g * 1000) / 10 : 0; }

const LOCAL_ACT = (function () {
  const samples = DATA.match_samples || [];
  const hours = Array.from({ length: 24 }, () => ({ games: 0, wins: 0 }));
  const days = Array.from({ length: 7 }, () => ({ games: 0, wins: 0 })); // 0=Sun (JS)
  for (const s of samples) {
    const d = new Date(s[0] * 1000);
    const won = s[1] === 1;
    const hb = hours[d.getHours()], db = days[d.getDay()];
    hb.games++; db.games++;
    if (won) { hb.wins++; db.wins++; }
  }
  // Reorder weekdays Mon..Sun for display
  const order = [1, 2, 3, 4, 5, 6, 0];
  const NAMES = { 0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat" };
  return {
    hours,
    weekday: order.map(i => ({ day: NAMES[i], games: days[i].games, wins: days[i].wins })),
  };
})();

const TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "local time";
(function () { const c = document.getElementById("tz-cap"); if (c) c.textContent = `· ${TZ}`; })();

/* ── Activity heatmap: weekday × hour (chartjs-chart-matrix) ──── */
(function () {
  const samples = DATA.match_samples || [];
  const cap = document.getElementById("heat-cap");
  if (!samples.length) {  // no raw samples → can't build a local-tz heatmap
    if (cap) cap.textContent = "Activity heatmap (needs a fresh report)";
    return;
  }
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const jsToIdx = { 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 0: 6 };
  const grid = {}; let maxV = 0;
  for (const s of samples) {
    const d = new Date(s[0] * 1000);
    const k = jsToIdx[d.getDay()] + "|" + d.getHours();
    const c = grid[k] || (grid[k] = { g: 0, w: 0 });
    c.g++; if (s[1] === 1) c.w++;
    if (c.g > maxV) maxV = c.g;
  }
  const cells = [];
  for (let di = 0; di < 7; di++) for (let h = 0; h < 24; h++) {
    const c = grid[di + "|" + h] || { g: 0, w: 0 };
    cells.push({ x: h, y: DAYS[di], v: c.g, wr: _winrate(c.w, c.g) });
  }
  if (cap) cap.textContent = `Activity heatmap — weekday × hour (${TZ})`;

  mk("c-heat", {
    type: "matrix",
    data: { datasets: [{
      label: "Matches",
      data: cells,
      backgroundColor: (c) => {
        const v = c.raw ? c.raw.v : 0;
        if (!v || !maxV) return "rgba(255,255,255,0.03)";
        return `rgba(255,70,85,${(0.15 + 0.85 * v / maxV).toFixed(3)})`;
      },
      borderColor: "#15171c", borderWidth: 1,
      width: (c) => { const a = c.chart.chartArea || {}; return ((a.right - a.left) || 0) / 24 - 2; },
      height: (c) => { const a = c.chart.chartArea || {}; return ((a.bottom - a.top) || 0) / 7 - 2; },
    }] },
    options: {
      scales: {
        x: { type: "linear", position: "top", min: -0.5, max: 23.5, offset: false,
             ticks: { stepSize: 3, callback: (v) => String(v).padStart(2, "0") },
             grid: { display: false } },
        y: { type: "category", labels: ["Sun", "Sat", "Fri", "Thu", "Wed", "Tue", "Mon"],
             offset: true, grid: { display: false } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          title: () => "",
          label: (c) => {
            const r = c.raw;
            return `${r.y} ${String(r.x).padStart(2, "0")}:00 — ${r.v} games · ${r.wr}% WR`;
          },
        } },
      },
    },
  });
})();

/* ── Performance profile (radar) ─────────────────────────────── */
(function () {
  const o = DATA.overview || {};
  const d = DATA.detail;
  const labels = ["Winrate", "HS%", "KDA", "ADR"];
  const vals = [o.winrate || 0, o.hs_pct || 0,
                Math.min((o.kda || 0) / 3 * 100, 100),
                Math.min((o.adr || 0) / 2, 100)];
  if (d && d.combat) { labels.push("Opening"); vals.push(d.combat.opening_winrate || 0); }
  mk("c-radar", {
    type: "radar",
    data: { labels, datasets: [{ label: "Profile", data: vals,
            backgroundColor: RED_SOFT, borderColor: RED, pointBackgroundColor: RED }] },
    options: {
      scales: { r: { min: 0, max: 100, grid: { color: GRID }, angleLines: { color: GRID },
                     pointLabels: { color: "#cfd3df" }, ticks: { display: false, backdropColor: "transparent" } } },
      plugins: { legend: { display: false } },
    },
  });
})();

/* ── Winrate by weekday (local) ──────────────────────────────── */
(function () {
  const useServer = !(DATA.match_samples && DATA.match_samples.length);
  const wd = useServer ? ((DATA.activity && DATA.activity.by_weekday) || []) : LOCAL_ACT.weekday;
  if (!wd.length) return;
  const rates = wd.map(x => x.winrate != null ? x.winrate : _winrate(x.wins, x.games));
  mk("c-weekday", {
    type: "bar",
    data: {
      labels: wd.map(x => x.day),
      datasets: [{ label: "Winrate %", data: rates,
                   backgroundColor: RED_SOFT, borderColor: RED, borderWidth: 1, games: wd.map(x => x.games) }],
    },
    options: {
      scales: { x: gridScale(), y: gridScale({ min: 0, max: 100 }) },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => `${ctx.parsed.y}% · ${ctx.dataset.games[ctx.dataIndex]} games` } },
      },
    },
  });
})();
