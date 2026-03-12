// FitOps Dashboard — shared Chart.js helpers

// ─── Activity Detail: Map + Stream Chart ─────────────────────────────────────

// Shared state for bidirectional map↔chart hover sync
const _activitySync = { map: null, hoverMarker: null, chart: null, latlng: null, _busy: false };

/** Find the index of the closest latlng point to (lat, lng). */
function _nearestPointIndex(latlng, lat, lng) {
  let best = 0, bestD = Infinity;
  for (let i = 0; i < latlng.length; i++) {
    const d = (latlng[i][0] - lat) ** 2 + (latlng[i][1] - lng) ** 2;
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

/** Drive chart tooltip to a specific data index (called from map hover). */
function _syncChartToIndex(idx) {
  const chart = _activitySync.chart;
  if (!chart || _activitySync._busy) return;
  const acts = chart.data.datasets
    .map((_, di) => ({ datasetIndex: di, index: idx }))
    .filter((a) => !chart.data.datasets[a.datasetIndex]._isThreshold);
  _activitySync._busy = true;
  chart.tooltip.setActiveElements(acts, { x: 0, y: 0 });
  chart.update('none');
  _activitySync._busy = false;
}

/**
 * Render an interactive Leaflet map of the GPS route with hover sync.
 * @param {string} containerId - ID of the div to mount the map into
 * @param {[number, number][]} latlng - Array of [lat, lng] pairs
 */
function renderActivityMap(containerId, latlng) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!latlng || latlng.length < 2) {
    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#4b5563;font-size:0.875rem;">No GPS data</div>';
    return;
  }

  _activitySync.latlng = latlng;

  const map = L.map(containerId, { scrollWheelZoom: false, zoomControl: true });
  _activitySync.map = map;

  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '© OpenStreetMap, © CARTO',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(map);

  const polyline = L.polyline(latlng, { color: '#f97316', weight: 3, opacity: 0.9 }).addTo(map);
  map.fitBounds(polyline.getBounds(), { padding: [16, 16] });

  L.circleMarker(latlng[0], {
    radius: 7, color: '#22c55e', fillColor: '#22c55e', fillOpacity: 1, weight: 2,
  }).addTo(map).bindTooltip('Start');

  L.circleMarker(latlng[latlng.length - 1], {
    radius: 7, color: '#ef4444', fillColor: '#ef4444', fillOpacity: 1, weight: 2,
  }).addTo(map).bindTooltip('End');

  // Hover marker (orange dot, hidden until mousemove)
  _activitySync.hoverMarker = L.circleMarker([0, 0], {
    radius: 6, color: '#f97316', fillColor: '#f97316', fillOpacity: 1, weight: 2, opacity: 0,
  }).addTo(map);

  // Invisible thick polyline for reliable mouse hit detection
  const hitPoly = L.polyline(latlng, { color: 'transparent', weight: 20, opacity: 0.001 }).addTo(map);
  hitPoly.on('mousemove', (e) => {
    const idx = _nearestPointIndex(latlng, e.latlng.lat, e.latlng.lng);
    _syncChartToIndex(idx);
    // Move the orange dot to the hovered point
    _activitySync.hoverMarker.setLatLng(latlng[idx]).setStyle({ opacity: 1, fillOpacity: 1 });
  });
  hitPoly.on('mouseout', () => {
    const chart = _activitySync.chart;
    if (chart) { chart.tooltip.setActiveElements([], { x: 0, y: 0 }); chart.update('none'); }
    _activitySync.hoverMarker.setStyle({ opacity: 0, fillOpacity: 0 });
  });

  map.on('click', () => map.scrollWheelZoom.enable());
  map.on('blur',  () => map.scrollWheelZoom.disable());
}


/**
 * Format seconds as M:SS.
 * @param {number} s
 * @returns {string}
 */
function _fmtMMSS(s) {
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}


/**
 * Render a multi-metric stream chart (HR, Pace, GAP, Altitude, Cadence, Power).
 * @param {string} canvasId
 * @param {Object} streams - Stream arrays keyed by type
 * @param {string} sportType - Strava sport type string
 * @param {{lt1?: number|null, lt2?: number|null}} [thresholds]
 * @returns {Chart} Chart.js instance
 */
function renderStreamChart(canvasId, streams, sportType, thresholds = {}) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !streams) return null;

  const RUN_SPORTS = new Set(['Run', 'TrailRun', 'VirtualRun', 'Walk', 'Hike']);
  const isRun = RUN_SPORTS.has(sportType);

  // X-axis label arrays
  const distLabels = (streams.distance || []).map(m => (m / 1000).toFixed(2));
  const timeLabels = (streams.time || []).map(s => _fmtMMSS(s));
  const xLabels = distLabels.length > 0 ? distLabels : timeLabels;

  const datasets = [];
  const scales = {
    x: {
      grid: { color: '#1f2937' },
      ticks: { maxTicksLimit: 10, color: '#6b7280', font: { size: 11 } },
    },
  };

  // Altitude — filled area (rendered first so it's behind other lines)
  if ((streams.altitude || []).length > 0) {
    datasets.push({
      label: 'Altitude',
      data: streams.altitude,
      borderColor: '#66bb6a',
      backgroundColor: 'rgba(102,187,106,0.12)',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.2,
      yAxisID: 'yAlt',
      fill: 'origin',
      _metricKey: 'alt',
    });
    const altVals = streams.altitude.filter(Boolean);
    scales.yAlt = {
      display: false,
      position: 'right',
      min: Math.min(...altVals) * 0.9,
      suggestedMax: Math.max(...altVals) * 1.05,
    };
  }

  // Heart Rate
  if ((streams.heartrate || []).length > 0) {
    const hrVals = streams.heartrate.filter(Boolean);
    datasets.push({
      label: 'Heart Rate',
      data: streams.heartrate,
      borderColor: '#ef5350',
      backgroundColor: 'rgba(239,83,80,0.08)',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.2,
      yAxisID: 'yHR',
      fill: false,
      _metricKey: 'hr',
    });
    scales.yHR = {
      position: 'left',
      title: { display: true, text: 'bpm', color: '#9ca3af', font: { size: 11 } },
      grid: { color: '#1f2937' },
      min: Math.floor(Math.min(...hrVals) * 0.88),
      suggestedMax: Math.max(...hrVals) * 1.02,
      ticks: { color: '#ef5350', font: { size: 11 } },
    };

    // LT2 threshold line (dashed red)
    if (thresholds.lt2) {
      datasets.push({
        label: 'LT2',
        data: Array(xLabels.length).fill(thresholds.lt2),
        borderColor: 'rgba(239,83,80,0.55)',
        borderWidth: 1,
        borderDash: [6, 4],
        pointRadius: 0,
        yAxisID: 'yHR',
        fill: false,
        _isThreshold: true,
      });
    }
    // LT1 threshold line (dashed orange)
    if (thresholds.lt1) {
      datasets.push({
        label: 'LT1',
        data: Array(xLabels.length).fill(thresholds.lt1),
        borderColor: 'rgba(251,146,60,0.55)',
        borderWidth: 1,
        borderDash: [6, 4],
        pointRadius: 0,
        yAxisID: 'yHR',
        fill: false,
        _isThreshold: true,
      });
    }
  }

  // Pace (from velocity_smooth)
  if ((streams.velocity_smooth || []).length > 0) {
    const paceData = streams.velocity_smooth.map(v => v > 0.1 ? 1000 / v : null);
    const paceVals = paceData.filter(Boolean);
    datasets.push({
      label: 'Pace',
      data: paceData,
      borderColor: '#42a5f5',
      backgroundColor: 'rgba(66,165,245,0.08)',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.2,
      yAxisID: 'yPace',
      fill: false,
      _metricKey: 'pace',
    });
    const p95 = paceVals.slice().sort((a, b) => a - b)[Math.floor(paceVals.length * 0.95)] || 600;
    scales.yPace = {
      position: 'right',
      reverse: true,
      title: { display: true, text: 'min/km', color: '#9ca3af', font: { size: 11 } },
      grid: { drawOnChartArea: false },
      min: 0,
      max: p95 * 1.05,
      ticks: {
        color: '#42a5f5',
        font: { size: 11 },
        callback: v => _fmtMMSS(v),
        maxTicksLimit: 6,
      },
    };

    // Grade-Adjusted Pace — use Strava's stream if available, else compute from grade_smooth
    const gasStream = streams.grade_adjusted_speed || [];
    let gapData = null;
    if (gasStream.length > 0) {
      gapData = gasStream.map(v => v > 0.1 ? 1000 / v : null);
    } else if ((streams.grade_smooth || []).length > 0) {
      gapData = streams.velocity_smooth.map((v, i) => {
        if (v <= 0.1) return null;
        const g = streams.grade_smooth[i] || 0;
        const adjSpeed = v * (1 + 0.033 * g);
        return adjSpeed > 0.1 ? 1000 / adjSpeed : null;
      });
    }
    if (gapData) {
      datasets.push({
        label: 'GAP',
        data: gapData,
        borderColor: '#38bdf8',
        borderWidth: 1.5,
        borderDash: [5, 3],
        pointRadius: 0,
        tension: 0.2,
        yAxisID: 'yPace',
        fill: false,
        hidden: false,
        _metricKey: 'gap',
      });
    }
  }

  // Cadence (hidden by default)
  if ((streams.cadence || []).length > 0) {
    const cadData = streams.cadence.map(v => isRun ? v * 2 : v);
    datasets.push({
      label: 'Cadence',
      data: cadData,
      borderColor: '#ffa726',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.2,
      yAxisID: 'yCad',
      fill: false,
      hidden: true,
      _metricKey: 'cad',
    });
    const cadVals = cadData.filter(Boolean);
    scales.yCad = {
      display: false,
      position: 'right',
      min: Math.min(...cadVals) * 0.85,
      suggestedMax: Math.max(...cadVals) * 1.05,
    };
  }

  // Power (hidden by default)
  if ((streams.watts || []).length > 0) {
    datasets.push({
      label: 'Power',
      data: streams.watts,
      borderColor: '#ab47bc',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.2,
      yAxisID: 'yPwr',
      fill: false,
      hidden: true,
      _metricKey: 'pwr',
    });
    const pwrVals = streams.watts.filter(Boolean);
    scales.yPwr = {
      display: false,
      position: 'right',
      min: 0,
      suggestedMax: Math.max(...pwrVals) * 1.05,
    };
  }

  const chart = new Chart(ctx, {
    type: 'line',
    data: { labels: xLabels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      onHover: (event, activeElements) => {
        if (_activitySync._busy || !_activitySync.hoverMarker) return;
        const ll = _activitySync.latlng;
        if (!ll) return;
        if (!activeElements.length) {
          _activitySync.hoverMarker.setStyle({ opacity: 0, fillOpacity: 0 });
          return;
        }
        const idx = activeElements[0].index;
        if (idx < ll.length) {
          _activitySync.hoverMarker.setLatLng(ll[idx]).setStyle({ opacity: 1, fillOpacity: 1 });
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          filter: (item) => !item.dataset._isThreshold,
          callbacks: {
            label: (item) => {
              const ds = item.dataset;
              const v = item.parsed.y;
              if (v === null || v === undefined) return null;
              if (ds.label === 'Heart Rate') return ` HR: ${Math.round(v)} bpm`;
              if (ds.label === 'Pace')        return ` Pace: ${_fmtMMSS(v)}/km`;
              if (ds.label === 'GAP')         return ` GAP: ${_fmtMMSS(v)}/km`;
              if (ds.label === 'Altitude')    return ` Alt: ${Math.round(v)} m`;
              if (ds.label === 'Cadence')     return ` Cadence: ${Math.round(v)} ${isRun ? 'spm' : 'rpm'}`;
              if (ds.label === 'Power')       return ` Power: ${Math.round(v)} W`;
              return ` ${ds.label}: ${v}`;
            },
            afterBody: (items) => {
              // Show threshold values when HR is being hovered
              const lines = [];
              if (thresholds.lt2) lines.push(` LT2: ${thresholds.lt2} bpm`);
              if (thresholds.lt1) lines.push(` LT1: ${thresholds.lt1} bpm`);
              const hasHR = items.some(i => i.dataset.label === 'Heart Rate');
              return hasHR ? lines : [];
            },
          },
        },
      },
      scales,
    },
  });

  // Store label arrays for x-axis toggle
  chart._distLabels = distLabels.length > 0 ? distLabels : null;
  chart._timeLabels = timeLabels.length > 0 ? timeLabels : null;
  window._activeStreamChart = chart;
  _activitySync.chart = chart;

  return chart;
}


/**
 * Create metric toggle chips and wire them to the chart.
 * @param {Chart} chart
 * @param {string} containerId
 * @param {{hr, pace, alt, cad, pwr}: boolean} available
 */
function initMetricToggles(chart, containerId, available) {
  const container = document.getElementById(containerId);
  if (!container || !chart) return;

  const METRICS = [
    { key: 'hr',   label: 'HR',       color: '#ef5350', defaultOn: true  },
    { key: 'pace', label: 'Pace',     color: '#42a5f5', defaultOn: true  },
    { key: 'gap',  label: 'GAP',      color: '#38bdf8', defaultOn: true  },
    { key: 'alt',  label: 'Altitude', color: '#66bb6a', defaultOn: true  },
    { key: 'cad',  label: 'Cadence',  color: '#ffa726', defaultOn: false },
    { key: 'pwr',  label: 'Power',    color: '#ab47bc', defaultOn: false },
  ];

  METRICS.forEach(({ key, label, color, defaultOn }) => {
    if (!available[key]) return;

    const btn = document.createElement('button');
    btn.textContent = label;
    btn.dataset.metricKey = key;
    btn.style.cssText = `
      padding: 3px 10px;
      border-radius: 9999px;
      border: 1px solid ${color};
      font-size: 0.75rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s;
    `;

    const setActive = (active) => {
      btn.style.background = active ? color + '33' : 'transparent';
      btn.style.color = active ? color : '#6b7280';
      btn.style.borderColor = active ? color : '#374151';
      btn.dataset.active = active ? '1' : '0';
    };

    setActive(defaultOn);

    btn.addEventListener('click', () => {
      const dsIndex = chart.data.datasets.findIndex(ds => ds._metricKey === key);
      if (dsIndex === -1) return;
      const nowVisible = !chart.isDatasetVisible(dsIndex);
      chart.setDatasetVisibility(dsIndex, nowVisible);
      chart.update('none');
      setActive(nowVisible);
    });

    container.appendChild(btn);
  });
}


/**
 * Switch stream chart x-axis between distance and time.
 * @param {'distance'|'time'} mode
 */
function setXAxis(mode) {
  const chart = window._activeStreamChart;
  if (!chart) return;

  const labels = mode === 'distance' ? chart._distLabels : chart._timeLabels;
  if (!labels) return;

  chart.data.labels = labels;
  chart.update();

  const btnDist = document.getElementById('xaxis-distance');
  const btnTime = document.getElementById('xaxis-time');
  if (btnDist && btnTime) {
    const activeStyle = 'background:#f97316;color:#fff;';
    const inactiveStyle = 'background:#1f2937;color:#6b7280;';
    btnDist.style.cssText = (mode === 'distance' ? activeStyle : inactiveStyle) + 'padding:6px 12px;font-size:0.75rem;font-weight:500;transition:all 0.15s;';
    btnTime.style.cssText = (mode === 'time'     ? activeStyle : inactiveStyle) + 'padding:6px 12px;font-size:0.75rem;font-weight:500;transition:all 0.15s;';
  }
}

/**
 * Render a GitHub-style activity heatmap.
 * @param {string} containerId  - div to render into
 * @param {{date: string, count: number, distance_km: number}[]} data
 * @param {string} [tooltipId]  - optional element id to show hover text
 */
function renderActivityHeatmap(containerId, data, tooltipId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Build a lookup map: date string -> {count, distance_km}
  const lookup = {};
  for (const d of data) {
    lookup[d.date] = d;
  }

  // Color palette: 0 activities -> darkest, 4+ -> brightest
  const COLORS = ["#1f2937", "#7c2d12", "#c2410c", "#ea580c", "#f97316"];
  function color(count) {
    if (count === 0) return COLORS[0];
    if (count === 1) return COLORS[1];
    if (count === 2) return COLORS[2];
    if (count === 3) return COLORS[3];
    return COLORS[4];
  }

  // Build 53 weeks ending today
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Find the Sunday on or after today to make a clean grid
  const endDate = new Date(today);
  // Go back to start of current week (Monday-based)
  const dayOfWeek = (today.getDay() + 6) % 7; // Mon=0 … Sun=6
  const startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - dayOfWeek - 52 * 7);

  const WEEKS = 53;
  const DAY_SIZE = 11;   // px per cell
  const DAY_GAP = 2;     // px gap
  const CELL = DAY_SIZE + DAY_GAP;
  const LABEL_H = 18;    // top label row height

  const DAY_NAMES = ["Mon", "Wed", "Fri"];
  const DAY_ROWS  = [0, 2, 4]; // which row indices get a label

  const svgW = WEEKS * CELL;
  const svgH = LABEL_H + 7 * CELL;

  // Build SVG
  let cells = "";
  const cur = new Date(startDate);
  for (let week = 0; week < WEEKS; week++) {
    for (let dow = 0; dow < 7; dow++) {
      const dateStr = cur.toISOString().slice(0, 10);
      const info = lookup[dateStr] || { count: 0, distance_km: 0 };
      const x = week * CELL;
      const y = LABEL_H + dow * CELL;
      const title = info.count > 0
        ? `${dateStr}: ${info.count} activit${info.count === 1 ? "y" : "ies"}, ${info.distance_km} km`
        : dateStr;
      cells += `<rect x="${x}" y="${y}" width="${DAY_SIZE}" height="${DAY_SIZE}" rx="2"
        fill="${color(info.count)}" data-tip="${title}"
        style="cursor:${info.count > 0 ? 'pointer' : 'default'}"/>`;
      cur.setDate(cur.getDate() + 1);
    }
  }

  // Month labels along the top
  let monthLabels = "";
  const labelCur = new Date(startDate);
  let lastMonth = -1;
  for (let week = 0; week < WEEKS; week++) {
    const m = labelCur.getMonth();
    if (m !== lastMonth) {
      const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      monthLabels += `<text x="${week * CELL}" y="${LABEL_H - 4}" fill="#6b7280" font-size="10" font-family="sans-serif">${MONTH_NAMES[m]}</text>`;
      lastMonth = m;
    }
    labelCur.setDate(labelCur.getDate() + 7);
  }

  // Day-of-week labels on left
  let dowLabels = "";
  for (let i = 0; i < DAY_NAMES.length; i++) {
    const row = DAY_ROWS[i];
    const y = LABEL_H + row * CELL + DAY_SIZE - 1;
    dowLabels += `<text x="-2" y="${y}" fill="#4b5563" font-size="9" font-family="sans-serif" text-anchor="end">${DAY_NAMES[i]}</text>`;
  }

  const svg = `<svg width="${svgW + 24}" height="${svgH}" viewBox="-24 0 ${svgW + 24} ${svgH}" xmlns="http://www.w3.org/2000/svg">
    ${monthLabels}
    ${dowLabels}
    ${cells}
  </svg>`;

  container.innerHTML = svg;

  // Tooltip on hover
  const tooltipEl = tooltipId ? document.getElementById(tooltipId) : null;
  container.querySelectorAll("rect[data-tip]").forEach((rect) => {
    rect.addEventListener("mouseenter", () => {
      if (tooltipEl) tooltipEl.textContent = rect.getAttribute("data-tip");
    });
    rect.addEventListener("mouseleave", () => {
      if (tooltipEl) tooltipEl.textContent = "";
    });
  });
}


/**
 * Render VO2max estimate history as a line chart.
 * @param {string} canvasId
 * @param {{date: string, estimate: number, confidence_label: string}[]} data - oldest first
 */
function renderVo2maxChart(canvasId, data) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  const labels = data.map((d) => d.date);
  const estimates = data.map((d) => d.estimate);
  const avg = estimates.reduce((a, b) => a + b, 0) / estimates.length;

  new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "VO₂max (ml/kg/min)",
          data: estimates,
          borderColor: "#a78bfa",
          backgroundColor: "rgba(167,139,250,0.10)",
          borderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          tension: 0.3,
          fill: true,
        },
        {
          label: "Average",
          data: labels.map(() => parseFloat(avg.toFixed(1))),
          borderColor: "rgba(251,146,60,0.5)",
          borderWidth: 1.5,
          borderDash: [5, 4],
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top",
          labels: { usePointStyle: true, pointStyle: "line", padding: 16 },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: "#1f2937" },
          ticks: { maxTicksLimit: 10, maxRotation: 45 },
        },
        y: {
          grid: { color: "#1f2937" },
          title: { display: true, text: "ml/kg/min", color: "#9ca3af" },
          ticks: { callback: (v) => v.toFixed(0) },
          suggestedMin: 30,
        },
      },
    },
  });
}


Chart.defaults.color = "#9ca3af";
Chart.defaults.borderColor = "#1f2937";

/**
 * Render the CTL / ATL / TSB training load chart.
 * @param {string} canvasId
 * @param {string[]} labels  - date strings
 * @param {{ctl: number[], atl: number[], tsb: number[]}} series
 */
function renderTrainingLoadChart(canvasId, labels, series) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "CTL (Fitness)",
          data: series.ctl,
          borderColor: "#60a5fa",
          backgroundColor: "rgba(96,165,250,0.08)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        },
        {
          label: "ATL (Fatigue)",
          data: series.atl,
          borderColor: "#fb923c",
          backgroundColor: "rgba(251,146,60,0.08)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        },
        {
          label: "TSB (Form)",
          data: series.tsb,
          borderColor: "#4ade80",
          backgroundColor: "rgba(74,222,128,0.08)",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          borderDash: [4, 3],
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top",
          labels: { usePointStyle: true, pointStyle: "line", padding: 16 },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: "#1f2937" },
          ticks: {
            maxTicksLimit: 10,
            maxRotation: 0,
          },
        },
        y: {
          grid: { color: "#1f2937" },
          ticks: { callback: (v) => v.toFixed(0) },
        },
      },
    },
  });
}

/**
 * Render weekly training volume bar chart.
 * @param {string} canvasId
 * @param {{week_start: string, distance_km: number, activity_count: number}[]} weeklyData
 */
function renderWeeklyVolumeChart(canvasId, weeklyData) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  const labels = weeklyData.map((w) => w.week_start);
  const distances = weeklyData.map((w) => w.distance_km);
  const counts = weeklyData.map((w) => w.activity_count);

  // Compute average for reference line
  const nonZero = distances.filter((d) => d > 0);
  const avg = nonZero.length ? nonZero.reduce((a, b) => a + b, 0) / nonZero.length : 0;

  new Chart(ctx, {
    data: {
      labels,
      datasets: [
        {
          type: "bar",
          label: "Distance (km)",
          data: distances,
          backgroundColor: "rgba(249,115,22,0.7)",
          borderColor: "#f97316",
          borderWidth: 1,
          borderRadius: 3,
          yAxisID: "y",
        },
        {
          type: "line",
          label: "Avg km/week",
          data: labels.map(() => parseFloat(avg.toFixed(1))),
          borderColor: "rgba(96,165,250,0.5)",
          borderWidth: 1.5,
          borderDash: [5, 4],
          pointRadius: 0,
          fill: false,
          yAxisID: "y",
        },
        {
          type: "line",
          label: "Activities",
          data: counts,
          borderColor: "#4ade80",
          backgroundColor: "rgba(74,222,128,0.1)",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          yAxisID: "y2",
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top",
          labels: { usePointStyle: true, padding: 16 },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.label === "Activities")
                return ` Activities: ${ctx.parsed.y}`;
              return ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} km`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "#1f2937" },
          ticks: { maxTicksLimit: 12, maxRotation: 45 },
        },
        y: {
          grid: { color: "#1f2937" },
          position: "left",
          title: { display: true, text: "km", color: "#9ca3af" },
          ticks: { callback: (v) => v + " km" },
        },
        y2: {
          grid: { drawOnChartArea: false },
          position: "right",
          title: { display: true, text: "count", color: "#9ca3af" },
          ticks: { stepSize: 1, callback: (v) => v },
        },
      },
    },
  });
}
