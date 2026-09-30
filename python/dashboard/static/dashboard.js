/* ═══════════════════════════════════════════════════════════════
   dashboard.js — Rail Anomaly Detection Dashboard
   Handles: SocketIO, charts, live display, history table, toasts
   ═══════════════════════════════════════════════════════════════ */

"use strict";

// ─── GLOBALS ────────────────────────────────────────────────────
const socket = io();

let totalDetections  = 0;
let criticalCount    = 0;
let historyData      = [];
let pieChart         = null;
let barChart         = null;

const CLASS_COLORS = {
  crack:           "#3b82f6",
  rail_defect:     "#8b5cf6",
  fastener_defect: "#f59e0b",
  obstacle:        "#ef4444",
  broken_rail:     "#ec4899",
};

const CLASS_ICONS = {
  crack:           "⚡",
  rail_defect:     "🔧",
  fastener_defect: "🔩",
  obstacle:        "⚠️",
  broken_rail:     "💥",
};

// ─── LIVE CLOCK ─────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  document.getElementById("live-time").textContent =
    now.toLocaleTimeString("en-IN", { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

// ─── SOCKET EVENTS ──────────────────────────────────────────────
socket.on("connect", () => {
  setConnectionStatus(true);
  showToast("✅ Connected to RailGuard dashboard", "green");
});

socket.on("disconnect", () => {
  setConnectionStatus(false);
  showToast("⚠️ Disconnected from server", "orange");
});

socket.on("history", (data) => {
  historyData = data || [];
  rebuildTable();
  rebuildCharts();
  updateKPIs();
});

socket.on("new_detection", (detection) => {
  historyData.unshift(detection);  // newest first
  if (historyData.length > 200) historyData.pop();

  totalDetections = detection.id || (totalDetections + 1);
  if (["HIGH", "CRITICAL"].includes(detection.severity)) criticalCount++;

  updateLiveDisplay(detection);
  updateKPIs(detection);
  prependTableRow(detection);
  updateCharts(detection);
  showToast(
    `${detection.icon || "❓"} <strong>${detection.label}</strong> — ${(detection.confidence * 100).toFixed(1)}%`,
    detection.severity === "CRITICAL" ? "red" : detection.severity === "HIGH" ? "orange" : "blue"
  );
});

socket.on("alert", (data) => {
  showAlertBanner(data.message, data.color);
});

socket.on("stats_update", (stats) => {
  if (!stats) return;
  totalDetections = stats.total || 0;
  updateKPIs();
});

// ─── CONNECTION STATUS ───────────────────────────────────────────
function setConnectionStatus(connected) {
  const pill = document.getElementById("connection-status");
  const dot  = document.getElementById("status-dot");
  const text = document.getElementById("status-text");

  if (connected) {
    pill.classList.add("connected");
    dot.classList.add("connected");
    text.textContent = "Live";
  } else {
    pill.classList.remove("connected");
    dot.classList.remove("connected");
    text.textContent = "Disconnected";
  }
}

// ─── KPI UPDATES ────────────────────────────────────────────────
function updateKPIs(latest) {
  animateCount("kpi-total-val", totalDetections);
  document.getElementById("kpi-critical-val").textContent = criticalCount;

  if (latest) {
    document.getElementById("kpi-latest-icon").textContent = latest.icon || "❓";
    document.getElementById("kpi-latest-val").textContent  = latest.label || "—";
    document.getElementById("kpi-conf-val").textContent =
      latest.confidence ? (latest.confidence * 100).toFixed(1) + "%" : "—";
  }
}

function animateCount(id, target) {
  const el = document.getElementById(id);
  const start = parseInt(el.textContent) || 0;
  const diff  = target - start;
  if (diff === 0) return;
  const step  = Math.ceil(Math.abs(diff) / 20);
  let current = start;

  const timer = setInterval(() => {
    current += (diff > 0 ? step : -step);
    if ((diff > 0 && current >= target) || (diff < 0 && current <= target)) {
      clearInterval(timer);
      current = target;
    }
    el.textContent = current;
  }, 16);
}

// ─── LIVE DISPLAY ────────────────────────────────────────────────
function updateLiveDisplay(d) {
  const container = document.getElementById("live-display");
  const confSection = document.getElementById("conf-section");
  const bboxInfo    = document.getElementById("bbox-info");

  // Build result HTML
  const color = d.color || CLASS_COLORS[d.class] || "#60a5fa";
  container.innerHTML = `
    <div class="live-result">
      <span class="live-defect-icon">${d.icon || "❓"}</span>
      <div class="live-defect-name" style="color:${color};">${d.label || d.class}</div>
      <span class="live-severity-badge"
            style="background:${color}22;color:${color};border:1px solid ${color}55;">
        ${d.severity}
      </span>
      <div class="live-ts">${formatTime(d.timestamp)}</div>
    </div>
  `;

  // Confidence bar
  confSection.style.display = "block";
  document.getElementById("conf-pct").textContent = (d.confidence * 100).toFixed(1) + "%";
  setTimeout(() => {
    document.getElementById("conf-bar").style.width = (d.confidence * 100) + "%";
  }, 50);

  // BBox info
  if (d.bbox && d.bbox.length === 4) {
    bboxInfo.style.display = "flex";
    document.getElementById("bbox-val").textContent =
      d.bbox.map(v => v.toFixed(3)).join(", ");
  } else {
    bboxInfo.style.display = "none";
  }
}

// ─── HISTORY TABLE ───────────────────────────────────────────────
function rebuildTable() {
  const tbody = document.getElementById("history-body");
  tbody.innerHTML = "";

  if (historyData.length === 0) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="6">No detections yet.</td></tr>`;
    return;
  }

  historyData.forEach(d => {
    tbody.appendChild(buildTableRow(d, false));
  });
}

function prependTableRow(d) {
  const tbody = document.getElementById("history-body");

  // Remove empty row if present
  const emptyRow = tbody.querySelector(".empty-row");
  if (emptyRow) emptyRow.remove();

  const tr = buildTableRow(d, true);
  tbody.insertBefore(tr, tbody.firstChild);

  // Limit visible rows
  while (tbody.children.length > 200) {
    tbody.removeChild(tbody.lastChild);
  }
}

function buildTableRow(d, isNew) {
  const tr = document.createElement("tr");
  if (isNew) tr.classList.add("row-new");

  const color = CLASS_COLORS[d.class] || "#60a5fa";

  tr.innerHTML = `
    <td style="font-family:var(--mono);color:var(--text-muted);font-size:11px;">#${d.id || "—"}</td>
    <td style="font-family:var(--mono);font-size:12px;">${formatTime(d.timestamp)}</td>
    <td>
      <span style="display:flex;align-items:center;gap:8px;">
        <span>${d.icon || "❓"}</span>
        <span style="color:${color};font-weight:600;">${d.label || d.class}</span>
      </span>
    </td>
    <td>
      <div style="display:flex;align-items:center;gap:8px;">
        <div style="width:60px;height:5px;border-radius:3px;background:rgba(255,255,255,0.08);overflow:hidden;">
          <div style="width:${(d.confidence*100).toFixed(0)}%;height:100%;background:${color};border-radius:3px;"></div>
        </div>
        <span style="font-family:var(--mono);font-size:12px;">${(d.confidence*100).toFixed(1)}%</span>
      </div>
    </td>
    <td><span class="sev-badge sev-${d.severity}">${d.severity}</span></td>
    <td style="font-size:12px;color:var(--text-muted);">${d.source || "stm32"}</td>
  `;

  return tr;
}

// ─── FILTER ──────────────────────────────────────────────────────
function filterTable() {
  const query = document.getElementById("filter-input").value.toLowerCase();
  const rows  = document.querySelectorAll("#history-body tr:not(.empty-row)");
  rows.forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(query) ? "" : "none";
  });
}

// ─── CLEAR HISTORY ───────────────────────────────────────────────
function clearHistory() {
  historyData = [];
  totalDetections = 0;
  criticalCount = 0;
  rebuildTable();
  updateKPIs();

  // Reset live display
  document.getElementById("live-display").innerHTML = `
    <div class="live-idle">
      <div class="idle-icon">📡</div>
      <p class="idle-text">Waiting for detections...</p>
      <p class="idle-sub">Connect STM32N657-DK and run bridge.py</p>
      <button class="btn-demo" onclick="requestDemo()" id="demo-btn">▶ Run Demo Mode</button>
    </div>
  `;
  document.getElementById("conf-section").style.display = "none";
  document.getElementById("bbox-info").style.display = "none";

  showToast("🗑️ History cleared", "blue");
}

// ─── CHARTS ──────────────────────────────────────────────────────
const CHART_DEFAULTS = {
  color: "#94a3b8",
  font: { family: "Inter", size: 12 },
};

Chart.defaults.color = CHART_DEFAULTS.color;
Chart.defaults.font  = CHART_DEFAULTS.font;

function initCharts() {
  // PIE CHART
  const pieCtx = document.getElementById("pieChart").getContext("2d");
  pieChart = new Chart(pieCtx, {
    type: "doughnut",
    data: {
      labels: ["No data"],
      datasets: [{
        data: [1],
        backgroundColor: ["rgba(255,255,255,0.06)"],
        borderColor:     ["rgba(255,255,255,0.08)"],
        borderWidth: 2,
        hoverOffset: 6,
      }]
    },
    options: {
      responsive: true,
      cutout: "65%",
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.parsed} detections`
          }
        }
      },
      animation: { animateRotate: true, duration: 600 }
    }
  });

  // BAR CHART
  const barCtx = document.getElementById("barChart").getContext("2d");
  barChart = new Chart(barCtx, {
    type: "bar",
    data: {
      labels: [],
      datasets: [{
        label: "Detections",
        data: [],
        backgroundColor: "rgba(59,130,246,0.5)",
        borderColor:     "rgba(59,130,246,0.9)",
        borderWidth: 1,
        borderRadius: 6,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.y} detections` } }
      },
      scales: {
        x: {
          grid: { color: "rgba(255,255,255,0.04)" },
          ticks: { color: "#475569" }
        },
        y: {
          grid: { color: "rgba(255,255,255,0.04)" },
          ticks: { color: "#475569", stepSize: 1 },
          beginAtZero: true
        }
      },
      animation: { duration: 400 }
    }
  });
}

function rebuildCharts() {
  const classCounts = {};
  const hourCounts  = {};

  historyData.forEach(d => {
    classCounts[d.class] = (classCounts[d.class] || 0) + 1;
    const h = d.timestamp ? new Date(d.timestamp).getHours() : 0;
    const key = `${String(h).padStart(2,"0")}:00`;
    hourCounts[key] = (hourCounts[key] || 0) + 1;
  });

  updatePieChart(classCounts);
  updateBarChart(hourCounts);
}

function updateCharts(d) {
  // Update pie
  const labels = pieChart.data.labels;
  const data   = pieChart.data.datasets[0].data;
  const colors = pieChart.data.datasets[0].backgroundColor;
  const borders= pieChart.data.datasets[0].borderColor;

  if (labels[0] === "No data") {
    pieChart.data.labels = [];
    pieChart.data.datasets[0].data = [];
    pieChart.data.datasets[0].backgroundColor = [];
    pieChart.data.datasets[0].borderColor = [];
  }

  const idx = pieChart.data.labels.indexOf(d.label || d.class);
  if (idx >= 0) {
    pieChart.data.datasets[0].data[idx]++;
  } else {
    const c = CLASS_COLORS[d.class] || "#60a5fa";
    pieChart.data.labels.push(d.label || d.class);
    pieChart.data.datasets[0].data.push(1);
    pieChart.data.datasets[0].backgroundColor.push(c + "80");
    pieChart.data.datasets[0].borderColor.push(c);
  }
  pieChart.update("none");
  buildPieLegend();

  // Update bar
  const h = d.timestamp ? new Date(d.timestamp).getHours() : 0;
  const key = `${String(h).padStart(2,"0")}:00`;
  const barIdx = barChart.data.labels.indexOf(key);
  if (barIdx >= 0) {
    barChart.data.datasets[0].data[barIdx]++;
  } else {
    barChart.data.labels.push(key);
    barChart.data.datasets[0].data.push(1);
  }
  barChart.update("none");
}

function updatePieChart(classCounts) {
  const entries = Object.entries(classCounts);
  if (entries.length === 0) return;

  pieChart.data.labels   = entries.map(([cls]) => cls.replace("_"," ").replace(/\b\w/g,c=>c.toUpperCase()));
  pieChart.data.datasets[0].data             = entries.map(([,v]) => v);
  pieChart.data.datasets[0].backgroundColor  = entries.map(([cls]) => (CLASS_COLORS[cls] || "#60a5fa") + "80");
  pieChart.data.datasets[0].borderColor      = entries.map(([cls]) => CLASS_COLORS[cls] || "#60a5fa");
  pieChart.update();
  buildPieLegend();
}

function updateBarChart(hourCounts) {
  const sortedKeys = Object.keys(hourCounts).sort();
  barChart.data.labels = sortedKeys;
  barChart.data.datasets[0].data = sortedKeys.map(k => hourCounts[k]);
  barChart.update();
}

function buildPieLegend() {
  const legend = document.getElementById("pie-legend");
  const labels = pieChart.data.labels;
  const colors = pieChart.data.datasets[0].borderColor;

  legend.innerHTML = labels.map((lbl, i) => `
    <div class="legend-item">
      <div class="legend-dot" style="background:${colors[i]};box-shadow:0 0 6px ${colors[i]};"></div>
      <span>${lbl}</span>
    </div>
  `).join("");
}

// ─── ALERT BANNER ───────────────────────────────────────────────
let alertTimer = null;
function showAlertBanner(message, color) {
  const banner = document.getElementById("alert-banner");
  document.getElementById("alert-text").textContent = message;
  banner.style.color = color || "#ff2d55";
  banner.classList.add("visible");

  if (alertTimer) clearTimeout(alertTimer);
  alertTimer = setTimeout(dismissAlert, 8000);
}

function dismissAlert() {
  document.getElementById("alert-banner").classList.remove("visible");
}

// ─── TOAST ───────────────────────────────────────────────────────
const TOAST_COLORS = {
  red:    "rgba(255,45,85,0.15)",
  orange: "rgba(255,149,0,0.15)",
  yellow: "rgba(255,204,0,0.15)",
  green:  "rgba(52,199,89,0.15)",
  blue:   "rgba(59,130,246,0.15)",
};

function showToast(html, type = "blue") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.style.background = TOAST_COLORS[type] || TOAST_COLORS.blue;
  toast.style.borderColor = `rgba(255,255,255,0.08)`;
  toast.innerHTML = html;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("fade-out");
    setTimeout(() => toast.remove(), 350);
  }, 3500);
}

// ─── DEMO MODE ───────────────────────────────────────────────────
function requestDemo() {
  fetch("/api/demo", { method: "POST" })
    .then(r => r.json())
    .then(() => {
      // Repeatedly call demo every 2 seconds
      if (!window._demoInterval) {
        window._demoInterval = setInterval(() => {
          fetch("/api/demo", { method: "POST" });
        }, 2000);

        const btn = document.getElementById("demo-btn");
        if (btn) {
          btn.textContent = "⏹ Stop Demo";
          btn.onclick = stopDemo;
        }
      }
    });
}

function stopDemo() {
  if (window._demoInterval) {
    clearInterval(window._demoInterval);
    window._demoInterval = null;
  }
  showToast("⏹ Demo mode stopped", "blue");
}

// ─── HELPERS ─────────────────────────────────────────────────────
function formatTime(isoString) {
  if (!isoString) return "—";
  try {
    return new Date(isoString).toLocaleTimeString("en-IN", {
      hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
  } catch { return "—"; }
}

// ─── INIT ────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initCharts();
  showToast("🚆 RailGuard Dashboard loaded", "blue");
});
