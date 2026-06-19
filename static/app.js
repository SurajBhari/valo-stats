/* ─────────────────────────────────────────────────────────
   Valo Stats — app.js
   Vanilla JS, no build step, no external deps.
   Data contract: POST /api/report/start, SSE /api/report/stream/:id
   ───────────────────────────────────────────────────────── */

"use strict";

/* ── DOM refs ────────────────────────────────────────────── */
const form       = document.getElementById("report-form");
const inputName  = document.getElementById("input-name");
const inputTag   = document.getElementById("input-tag");
const inputRegion= document.getElementById("input-region");
const inputWindow= document.getElementById("input-window");
const btnSubmit  = document.getElementById("btn-submit");
const errNameTag = document.getElementById("error-name-tag");
const errApi     = document.getElementById("error-api");

const emptyState    = document.getElementById("empty-state");
const jobPanel      = document.getElementById("job-panel");
const navStatus     = document.getElementById("nav-status");
const footerJobId   = document.getElementById("footer-job-id");

const jobPlayerName = document.getElementById("job-player-name");
const jobPlayerMeta = document.getElementById("job-player-meta");
const jobStatusBadge= document.getElementById("job-status-badge");

const pausedBanner    = document.getElementById("paused-banner");
const pausedCountdown = document.getElementById("paused-countdown");

const progressBar  = document.getElementById("progress-bar");
const progressPct  = document.getElementById("progress-pct");
const etaValue     = document.getElementById("eta-value");

const statMatches  = document.getElementById("stat-matches");
const statPages    = document.getElementById("stat-pages");
const statOldest   = document.getElementById("stat-oldest");

const messageDot   = document.getElementById("message-dot");
const messageText  = document.getElementById("message-text");

const errorPanel   = document.getElementById("error-panel");
const errorMsg     = document.getElementById("error-msg");

const downloadSection = document.getElementById("download-section");
const downloadSub     = document.getElementById("download-sub");
const btnDownload     = document.getElementById("btn-download");

const btnReset     = document.getElementById("btn-reset");

/* ── State ───────────────────────────────────────────────── */
let currentEs  = null;   // active EventSource
let currentJob = null;   // { name, tag, region, window, job_id }

/* ── Utilities ───────────────────────────────────────────── */
function fmtEta(seconds) {
  if (seconds == null || seconds < 0) return "Calculating...";
  if (seconds < 10) return "almost done";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `~${s}s`;
  return `~${m}m ${String(s).padStart(2, "0")}s`;
}

function fmtDate(epochSec) {
  if (epochSec == null) return "Waiting...";
  const d = new Date(epochSec * 1000);
  return d.toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric"
  });
}

function sanitizeTag(raw) {
  // Strip leading # if the user typed it
  return raw.replace(/^#/, "").trim();
}

function buildPdfUrl(jobId, name, tag, region) {
  const params = new URLSearchParams({ name, tag, region });
  return `/api/report/${encodeURIComponent(jobId)}/pdf?${params.toString()}`;
}

/* ── Show / hide helpers ─────────────────────────────────── */
function showJobPanel() {
  emptyState.style.display = "none";
  jobPanel.classList.add("active");
}

function resetToIdle() {
  if (currentEs) {
    currentEs.close();
    currentEs = null;
  }
  currentJob = null;

  // Form
  btnSubmit.disabled = false;
  btnSubmit.textContent = "Generate Report";

  // Panel
  jobPanel.classList.remove("active");
  emptyState.style.display = "";

  // Internals
  clearPaused();
  errorPanel.classList.remove("visible");
  downloadSection.classList.remove("visible");
  btnReset.style.display = "none";
  progressBar.style.width = "0%";
  progressBar.className = "progress-bar-fill";
  progressPct.textContent = "0%";
  progressPct.className = "progress-pct";
  etaValue.textContent = "Calculating...";
  statMatches.textContent = "0";
  statPages.textContent = "0";
  statOldest.textContent = "Waiting...";
  messageDot.className = "message-dot";
  messageText.textContent = "Initializing...";
  jobStatusBadge.className = "job-status-badge";
  jobStatusBadge.textContent = "Queued";
  navStatus.textContent = "Ready";
  footerJobId.textContent = "";
}

function showPaused(secondsLeft) {
  pausedBanner.classList.add("visible");
  pausedCountdown.textContent = `${secondsLeft}s`;
  progressBar.classList.add("paused");
  progressBar.classList.remove("running");
  messageDot.className = "message-dot paused";
}

function clearPaused() {
  pausedBanner.classList.remove("visible");
  progressBar.classList.remove("paused");
}

/* ── SSE event handler ───────────────────────────────────── */
function handleEvent(data) {
  const status   = data.status;
  const matches  = data.matches_parsed  ?? 0;
  const pages    = data.pages_fetched   ?? 0;
  const oldestTs = data.oldest_ts       ?? null;
  const pct      = data.progress_pct   ?? 0;
  const eta      = data.eta_seconds     ?? null;
  const msg      = data.message         || "";
  const err      = data.error           || null;
  const pauseSec = data.paused_seconds_left ?? 0;

  /* -- stats counters -- */
  statMatches.textContent = matches;
  statPages.textContent   = pages;
  statOldest.textContent  = fmtDate(oldestTs);

  /* -- progress bar -- */
  if (status === "done") {
    progressBar.style.width = "100%";
    progressBar.className   = "progress-bar-fill done";
    progressPct.textContent = "100%";
    progressPct.className   = "progress-pct done-pct";
  } else {
    progressBar.style.width = `${Math.min(pct, 99)}%`;   // never show 100% until done
    progressPct.textContent = `${Math.round(pct)}%`;
  }

  /* -- ETA -- */
  etaValue.textContent = status === "done" ? "Complete" : fmtEta(eta);

  /* -- paused banner -- */
  if (status === "paused") {
    showPaused(pauseSec);
  } else {
    clearPaused();
  }

  /* -- status badge + dot -- */
  jobStatusBadge.className = `job-status-badge ${status}`;
  jobStatusBadge.textContent = status.charAt(0).toUpperCase() + status.slice(1);

  /* -- message -- */
  messageDot.className = `message-dot ${status}`;
  if (status === "running")  messageDot.classList.add("running");
  if (msg) messageText.textContent = msg;

  /* -- nav bar -- */
  if (status === "running") navStatus.textContent = `${matches} matches fetched`;
  if (status === "paused")  navStatus.textContent = `Paused - ${pauseSec}s`;
  if (status === "done")    navStatus.textContent = "Done";
  if (status === "error")   navStatus.textContent = "Error";

  /* -- meta line under name -- */
  jobPlayerMeta.textContent = (function() {
    if (status === "running") return `Fetching page ${pages}... ${matches} matches so far`;
    if (status === "paused")  return `Rate limited - resuming in ${pauseSec}s`;
    if (status === "done")    return `${matches} matches parsed across ${pages} pages`;
    if (status === "error")   return "Fetch failed";
    return "Working...";
  })();

  /* -- terminal states -- */
  if (status === "done") {
    if (currentEs) { currentEs.close(); currentEs = null; }
    const { name, tag, region, job_id } = currentJob;
    const url = buildPdfUrl(job_id, name, tag, region);
    btnDownload.href = url;
    downloadSub.textContent =
      `${matches} matches parsed. Opens in a new tab (PDF or HTML fallback).`;
    downloadSection.classList.add("visible");
    btnReset.style.display = "";
    btnSubmit.disabled = false;
    btnSubmit.textContent = "Generate Report";
  }

  if (status === "error") {
    if (currentEs) { currentEs.close(); currentEs = null; }
    errorMsg.textContent = err || msg || "An unknown error occurred.";
    errorPanel.classList.add("visible");
    btnReset.style.display = "";
    btnSubmit.disabled = false;
    btnSubmit.textContent = "Generate Report";
    navStatus.textContent = "Error";
  }
}

/* ── Start job + open SSE stream ─────────────────────────── */
async function startReport(name, tag, region, window) {
  btnSubmit.disabled = true;
  btnSubmit.textContent = "Starting...";
  errApi.style.display = "none";

  let jobId;
  try {
    const res = await fetch("/api/report/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, tag, region, window }),
    });
    const json = await res.json();
    if (!res.ok) {
      const msg = json.error || `Server error ${res.status}`;
      errApi.textContent = msg;
      errApi.style.display = "block";
      btnSubmit.disabled = false;
      btnSubmit.textContent = "Generate Report";
      return;
    }
    jobId = json.job_id;
  } catch (e) {
    errApi.textContent = "Could not reach the server. Is it running?";
    errApi.style.display = "block";
    btnSubmit.disabled = false;
    btnSubmit.textContent = "Generate Report";
    return;
  }

  /* Job started — show the panel */
  currentJob = { name, tag, region, window, job_id: jobId };
  footerJobId.textContent = `job ${jobId.slice(0, 8)}`;

  // Set player name immediately — use DOM methods, no innerHTML
  jobPlayerName.textContent = "";
  const nameNode = document.createTextNode(name);
  const tagSpan  = document.createElement("span");
  tagSpan.className = "tag";
  tagSpan.textContent = `#${tag}`;
  jobPlayerName.appendChild(nameNode);
  jobPlayerName.appendChild(tagSpan);
  jobPlayerMeta.textContent = "Connecting to stream...";
  jobStatusBadge.className = "job-status-badge running";
  jobStatusBadge.textContent = "Running";
  navStatus.textContent = "Running";

  // Reset result areas
  errorPanel.classList.remove("visible");
  downloadSection.classList.remove("visible");
  btnReset.style.display = "none";

  showJobPanel();
  btnSubmit.textContent = "Running...";

  /* Open SSE */
  const es = new EventSource(`/api/report/stream/${encodeURIComponent(jobId)}`);
  currentEs = es;

  es.onmessage = function(event) {
    let data;
    try { data = JSON.parse(event.data); }
    catch { return; }
    handleEvent(data);
  };

  es.onerror = function() {
    es.close();
    currentEs = null;
    // Only surface error if job not already done
    if (currentJob && currentJob.job_id === jobId) {
      errorMsg.textContent = "Connection to the event stream was lost.";
      errorPanel.classList.add("visible");
      btnReset.style.display = "";
      btnSubmit.disabled = false;
      btnSubmit.textContent = "Generate Report";
      navStatus.textContent = "Disconnected";
      messageDot.className = "message-dot";
    }
  };
}

/* ── Form submission ─────────────────────────────────────── */
form.addEventListener("submit", function(e) {
  e.preventDefault();

  // Clear previous errors
  errNameTag.classList.remove("visible");
  errApi.style.display = "none";

  const name   = inputName.value.trim();
  const rawTag = inputTag.value.trim();
  const tag    = sanitizeTag(rawTag);
  const region = inputRegion.value;
  const window = inputWindow.value;

  if (!name || !tag) {
    errNameTag.classList.add("visible");
    if (!name) inputName.focus();
    else inputTag.focus();
    return;
  }

  // If a job is running, close it first
  if (currentEs) {
    currentEs.close();
    currentEs = null;
  }

  startReport(name, tag, region, window);
});

/* ── Reset button ────────────────────────────────────────── */
btnReset.addEventListener("click", function() {
  resetToIdle();
  inputName.focus();
});

/* ── Strip leading # from tag field on blur ──────────────── */
inputTag.addEventListener("blur", function() {
  inputTag.value = sanitizeTag(inputTag.value);
});

/* ── On page load: focus name field ─────────────────────── */
window.addEventListener("DOMContentLoaded", function() {
  inputName.focus();
});
