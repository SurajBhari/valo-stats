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

/* ── Activity by hour (matches) ──────────────────────────────── */
(function () {
  const h = (DATA.activity && DATA.activity.by_hour) || [];
  if (!h.length) return;
  mk("c-hours", {
    type: "bar",
    data: {
      labels: h.map(x => String(x.hour).padStart(2, "0")),
      datasets: [{ label: "Matches", data: h.map(x => x.games),
                   backgroundColor: RED_SOFT, borderColor: RED, borderWidth: 1 }],
    },
    options: {
      scales: { x: gridScale(), y: gridScale({ beginAtZero: true, precision: 0 }) },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => {
          const d = h[ctx.dataIndex];
          return `${d.games} matches · ${d.winrate}% WR`;
        } } },
      },
    },
  });
})();

/* ── Winrate by weekday ──────────────────────────────────────── */
(function () {
  const wd = (DATA.activity && DATA.activity.by_weekday) || [];
  if (!wd.length) return;
  mk("c-weekday", {
    type: "bar",
    data: {
      labels: wd.map(x => x.day),
      datasets: [{ label: "Winrate %", data: wd.map(x => x.winrate),
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
