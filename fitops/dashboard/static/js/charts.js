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
 * Build the compass rose SVG string.
 * @param {number|null} windDirDeg - meteorological FROM direction, or null
 * @returns {string} SVG markup
 */
function _compassSVG(windDirDeg) {
  const cx = 44, cy = 44, r = 30, size = 88;
  // Cardinal + intercardinal tick marks
  let ticks = '';
  for (let i = 0; i < 16; i++) {
    const rad = (i * 22.5 - 90) * Math.PI / 180;
    const inner = i % 4 === 0 ? r - 7 : (i % 2 === 0 ? r - 4 : r - 2);
    ticks += `<line x1="${(cx + r * Math.cos(rad)).toFixed(1)}" y1="${(cy + r * Math.sin(rad)).toFixed(1)}"
      x2="${(cx + inner * Math.cos(rad)).toFixed(1)}" y2="${(cy + inner * Math.sin(rad)).toFixed(1)}"
      stroke="#333" stroke-width="1"/>`;
  }
  // N/S/E/W labels
  const cards = [['N', 0], ['E', 90], ['S', 180], ['W', 270]];
  let labels = '';
  cards.forEach(([lbl, deg]) => {
    const rad = (deg - 90) * Math.PI / 180;
    const tx = (cx + (r + 9) * Math.cos(rad)).toFixed(1);
    const ty = (cy + (r + 9) * Math.sin(rad) + 3).toFixed(1);
    const col = lbl === 'N' ? '#00ff87' : '#3a3a3a';
    labels += `<text x="${tx}" y="${ty}" text-anchor="middle" font-size="8" fill="${col}" font-family="ui-monospace,monospace" font-weight="700">${lbl}</text>`;
  });
  // Wind arrow: FROM direction inward to center
  let windArrow = '';
  if (windDirDeg !== null && windDirDeg !== undefined) {
    const fromRad = (windDirDeg - 90) * Math.PI / 180;
    const tx = (cx + (r - 4) * Math.cos(fromRad)).toFixed(1);
    const ty = (cy + (r - 4) * Math.sin(fromRad)).toFixed(1);
    // Endpoint near center (leave room for arrowhead)
    const ex = (cx - 6 * Math.cos(fromRad)).toFixed(1);
    const ey = (cy - 6 * Math.sin(fromRad)).toFixed(1);
    windArrow = `
      <defs>
        <marker id="wah" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
          <polygon points="0,0 5,2.5 0,5" fill="#00aaff"/>
        </marker>
      </defs>
      <line x1="${tx}" y1="${ty}" x2="${ex}" y2="${ey}"
        stroke="#00aaff" stroke-width="1.5" marker-end="url(#wah)"/>`;
  }
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg">
    <rect width="${size}" height="${size}" fill="rgba(0,0,0,0.78)" rx="0"/>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#222" stroke-width="1"/>
    ${ticks}${labels}${windArrow}
  </svg>`;
}

/**
 * Render an interactive Leaflet map of the GPS route with hover sync.
 * @param {string} containerId - ID of the div to mount the map into
 * @param {[number, number][]} latlng - Array of [lat, lng] pairs
 * @param {{dirDeg?: number, label?: string}|null} [windData] - optional wind info for compass
 */
function renderActivityMap(containerId, latlng, windData) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!latlng || latlng.length < 2) {
    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#4b5563;font-size:0.875rem;">No GPS data</div>';
    return;
  }

  _activitySync.latlng = latlng;

  try {
    const map = L.map(containerId, { scrollWheelZoom: false, zoomControl: true });
    _activitySync.map = map;

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '© OpenStreetMap, © CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map);

    const polyline = L.polyline(latlng, { color: '#00ff87', weight: 2, opacity: 0.9 }).addTo(map);
    map.fitBounds(polyline.getBounds(), { padding: [16, 16] });

    L.circleMarker(latlng[0], {
      radius: 5, color: '#00ff87', fillColor: '#00ff87', fillOpacity: 1, weight: 2,
    }).addTo(map).bindTooltip('Start');

    L.circleMarker(latlng[latlng.length - 1], {
      radius: 5, color: '#ff3355', fillColor: '#ff3355', fillOpacity: 1, weight: 2,
    }).addTo(map).bindTooltip('End');

    // Hover marker (accent dot, hidden until mousemove)
    _activitySync.hoverMarker = L.circleMarker([0, 0], {
      radius: 5, color: '#00ff87', fillColor: '#00ff87', fillOpacity: 1, weight: 2, opacity: 0,
    }).addTo(map);

    // Invisible thick polyline for reliable mouse hit detection
    const hitPoly = L.polyline(latlng, { color: 'transparent', weight: 20, opacity: 0.001 }).addTo(map);
    hitPoly.on('mousemove', (e) => {
      const idx = _nearestPointIndex(latlng, e.latlng.lat, e.latlng.lng);
      _syncChartToIndex(idx);
      _activitySync.hoverMarker.setLatLng(latlng[idx]).setStyle({ opacity: 1, fillOpacity: 1 });
    });
    hitPoly.on('mouseout', () => {
      const chart = _activitySync.chart;
      if (chart) { chart.tooltip.setActiveElements([], { x: 0, y: 0 }); chart.update('none'); }
      _activitySync.hoverMarker.setStyle({ opacity: 0, fillOpacity: 0 });
    });

    // Compass rose control (bottom-right)
    const compassCtrl = L.control({ position: 'bottomright' });
    compassCtrl.onAdd = function() {
      const div = L.DomUtil.create('div');
      div.style.cssText = 'line-height:0;cursor:default;border:1px solid #1a1a1a;';
      div.innerHTML = _compassSVG(windData ? windData.dirDeg : null);
      if (windData && windData.label) div.title = 'Wind from ' + windData.label;
      L.DomEvent.disableClickPropagation(div);
      return div;
    };
    compassCtrl.addTo(map);

    map.on('click', () => map.scrollWheelZoom.enable());
    map.on('blur',  () => map.scrollWheelZoom.disable());
  } catch (e) {
    console.warn('Activity map failed to render:', e);
    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#4b5563;font-size:0.875rem;">Map unavailable</div>';
  }
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
      grid: { color: 'rgba(255,255,255,0.04)' },
      ticks: { maxTicksLimit: 10, color: '#888888', font: { size: 10, family: 'ui-monospace, monospace' } },
    },
  };

  // Altitude — filled area (rendered first so it's behind other lines)
  if ((streams.altitude || []).length > 0) {
    datasets.push({
      label: 'Altitude',
      data: streams.altitude,
      borderColor: '#00ff87',
      backgroundColor: 'rgba(0,255,135,0.06)',
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
      borderColor: '#ff3355',
      backgroundColor: 'rgba(255,51,85,0.06)',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.2,
      yAxisID: 'yHR',
      fill: false,
      _metricKey: 'hr',
    });
    scales.yHR = {
      position: 'left',
      title: { display: true, text: 'bpm', color: '#888', font: { size: 10, family: 'ui-monospace, monospace' } },
      grid: { color: 'rgba(255,255,255,0.04)' },
      min: Math.floor(Math.min(...hrVals) * 0.88),
      suggestedMax: Math.max(...hrVals) * 1.02,
      ticks: { color: '#ff3355', font: { size: 10, family: 'ui-monospace, monospace' } },
    };

    // LT2 threshold line (dashed red)
    if (thresholds.lt2) {
      datasets.push({
        label: 'LT2',
        data: Array(xLabels.length).fill(thresholds.lt2),
        borderColor: 'rgba(255,51,85,0.5)',
        borderWidth: 1,
        borderDash: [6, 4],
        pointRadius: 0,
        yAxisID: 'yHR',
        fill: false,
        _isThreshold: true,
      });
    }
    // LT1 threshold line (dashed amber)
    if (thresholds.lt1) {
      datasets.push({
        label: 'LT1',
        data: Array(xLabels.length).fill(thresholds.lt1),
        borderColor: 'rgba(255,170,0,0.5)',
        borderWidth: 1,
        borderDash: [6, 4],
        pointRadius: 0,
        yAxisID: 'yHR',
        fill: false,
        _isThreshold: true,
      });
    }
  }

  // Pace / Speed (from velocity_smooth)
  if ((streams.velocity_smooth || []).length > 0) {
    const paceData = isRun
      ? streams.velocity_smooth.map(v => v > 0.1 ? 1000 / v : null)
      : streams.velocity_smooth.map(v => v > 0.1 ? v * 3.6 : null);
    const paceVals = paceData.filter(Boolean);
    datasets.push({
      label: isRun ? 'Pace' : 'Speed',
      data: paceData,
      borderColor: '#00aaff',
      backgroundColor: 'rgba(0,170,255,0.06)',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.2,
      yAxisID: 'yPace',
      fill: false,
      _metricKey: 'pace',
    });
    if (isRun) {
      const p95 = paceVals.slice().sort((a, b) => a - b)[Math.floor(paceVals.length * 0.95)] || 600;
      scales.yPace = {
        position: 'right',
        reverse: true,
        title: { display: true, text: 'min/km', color: '#888', font: { size: 10, family: 'ui-monospace, monospace' } },
        grid: { drawOnChartArea: false },
        min: 0,
        max: p95 * 1.05,
        ticks: {
          color: '#00aaff',
          font: { size: 10, family: 'ui-monospace, monospace' },
          callback: v => _fmtMMSS(v),
          maxTicksLimit: 6,
        },
      };
    } else {
      const p5 = paceVals.slice().sort((a, b) => a - b)[Math.floor(paceVals.length * 0.05)] || 0;
      const p95 = paceVals.slice().sort((a, b) => a - b)[Math.floor(paceVals.length * 0.95)] || 50;
      scales.yPace = {
        position: 'right',
        reverse: false,
        title: { display: true, text: 'km/h', color: '#888', font: { size: 10, family: 'ui-monospace, monospace' } },
        grid: { drawOnChartArea: false },
        min: Math.max(0, p5 * 0.9),
        max: p95 * 1.1,
        ticks: {
          color: '#00aaff',
          font: { size: 10, family: 'ui-monospace, monospace' },
          callback: v => `${v.toFixed(0)}`,
          maxTicksLimit: 6,
        },
      };
    }

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
        borderColor: '#00ccff',
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

    // WAP — weather-adjusted pace (s/km for run, converted to km/h for cycling)
    if ((streams.wap_pace || []).length > 0) {
      const wapData = isRun
        ? streams.wap_pace
        : streams.wap_pace.map(v => v > 0 ? 3600 / v : null);
      datasets.push({
        label: isRun ? 'WAP' : 'WAP Speed',
        data: wapData,
        borderColor: '#ff8800',
        borderWidth: 1.5,
        borderDash: [3, 2],
        pointRadius: 0,
        tension: 0.2,
        yAxisID: 'yPace',
        fill: false,
        hidden: false,
        _metricKey: 'wap',
      });
    }

    // True Pace/Speed — GAP + WAP normalised (s/km for run, km/h for cycling)
    if ((streams.true_pace || []).length > 0) {
      const tpData = isRun
        ? streams.true_pace
        : streams.true_pace.map(v => v > 0 ? 3600 / v : null);
      datasets.push({
        label: isRun ? 'True Pace' : 'True Speed',
        data: tpData,
        borderColor: '#00ff87',
        borderWidth: 2,
        borderDash: [4, 2],
        pointRadius: 0,
        tension: 0.2,
        yAxisID: 'yPace',
        fill: false,
        hidden: false,
        _metricKey: 'tp',
      });
    }
  }

  // Cadence (hidden by default)
  if ((streams.cadence || []).length > 0) {
    const cadData = streams.cadence.map(v => isRun ? v * 2 : v);
    datasets.push({
      label: 'Cadence',
      data: cadData,
      borderColor: '#ffaa00',
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
      borderColor: '#aa55ff',
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

  const crosshairPlugin = {
    id: 'crosshair',
    afterDraw(ch) {
      const active = ch.tooltip._active;
      if (!active || !active.length) return;
      const { ctx, chartArea: { top, bottom }, scales: { x } } = ch;
      const xPos = x.getPixelForValue(active[0].index);
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(xPos, top);
      ctx.lineTo(xPos, bottom);
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(255,255,255,0.12)';
      ctx.stroke();
      ctx.restore();
    },
  };

  const chart = new Chart(ctx, {
    type: 'line',
    data: { labels: xLabels, datasets },
    plugins: [crosshairPlugin],
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
              if (ds.label === 'Speed')       return ` Speed: ${v.toFixed(1)} km/h`;
              if (ds.label === 'GAP')         return ` GAP: ${_fmtMMSS(v)}/km`;
              if (ds.label === 'WAP')         return ` WAP: ${_fmtMMSS(v)}/km`;
              if (ds.label === 'WAP Speed')   return ` WAP: ${v.toFixed(1)} km/h`;
              if (ds.label === 'True Pace')   return ` True Pace: ${_fmtMMSS(v)}/km`;
              if (ds.label === 'True Speed')  return ` True Speed: ${v.toFixed(1)} km/h`;
              if (ds.label === 'Altitude')    return ` Alt: ${Math.round(v)} m`;
              if (ds.label === 'Cadence')     return ` Cadence: ${Math.round(v)} ${isRun ? 'spm' : 'rpm'}`;
              if (ds.label === 'Power')       return ` Power: ${Math.round(v)} W`;
              return ` ${ds.label}: ${v}`;
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
function initMetricToggles(chart, containerId, available, sportType) {
  const container = document.getElementById(containerId);
  if (!container || !chart) return;

  const _isRun = new Set(['Run', 'TrailRun', 'VirtualRun', 'Walk', 'Hike']).has(sportType);
  const METRICS = [
    { key: 'hr',   label: 'HR',                      color: '#ff3355', defaultOn: true  },
    { key: 'pace', label: _isRun ? 'Pace' : 'Speed', color: '#00aaff', defaultOn: true  },
    { key: 'gap',  label: 'GAP',      color: '#00ccff', defaultOn: true  },
    { key: 'wap',  label: _isRun ? 'WAP' : 'WAP Speed',        color: '#ff8800', defaultOn: true  },
    { key: 'tp',   label: _isRun ? 'True Pace' : 'True Speed', color: '#00ff87', defaultOn: true  },
    { key: 'alt',  label: 'Altitude', color: '#00ff87', defaultOn: true  },
    { key: 'cad',  label: 'Cadence',  color: '#ffaa00', defaultOn: false },
    { key: 'pwr',  label: 'Power',    color: '#aa55ff', defaultOn: false },
  ];

  METRICS.forEach(({ key, label, color, defaultOn }) => {
    if (!available[key]) return;

    const btn = document.createElement('button');
    btn.textContent = label;
    btn.dataset.metricKey = key;
    btn.style.cssText = `
      padding: 3px 10px;
      border: 1px solid ${color};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      cursor: pointer;
      transition: all 0.1s;
      font-family: ui-monospace, monospace;
    `;

    const setActive = (active) => {
      btn.style.background = active ? color + '18' : 'transparent';
      btn.style.color = active ? color : '#3a3a3a';
      btn.style.borderColor = active ? color : '#2e2e2e';
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
    btnDist.classList.toggle('active', mode === 'distance');
    btnTime.classList.toggle('active', mode === 'time');
  }
}

/**
 * Render a GitHub-style activity heatmap, colored by total duration.
 * Clicking a column shows all activities from that week in the detail panel.
 * @param {string} containerId  - div to render into
 * @param {{date: string, count: number, duration_s: number, distance_km: number, activities: Array}[]} data
 * @param {string} period       - "month" | "year" | "all"
 * @param {string} [tooltipId]  - optional element id to show hover text
 * @param {string} [detailId]   - optional element id to show week detail on click
 */
function renderActivityHeatmap(containerId, data, period, tooltipId, detailId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Build a lookup map: date string -> day info
  const lookup = {};
  for (const d of data) {
    lookup[d.date] = d;
  }

  // Format seconds as "1h 23m" or "45m"
  function fmtDuration(s) {
    if (!s) return "0m";
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }

  // Color palette: intensity based on total duration (minutes)
  const COLORS     = ["#1a1a1a", "rgba(0,255,135,0.15)", "rgba(0,255,135,0.38)", "rgba(0,255,135,0.65)", "#00ff87"];
  const COLORS_DIM = ["#1a1a1a", "rgba(0,100,55,0.5)",   "rgba(0,100,55,0.7)",   "rgba(0,100,55,0.9)",   "#005c30"];
  function colorFor(duration_s, dim) {
    const palette = dim ? COLORS_DIM : COLORS;
    const min = (duration_s || 0) / 60;
    if (min === 0)  return palette[0];
    if (min < 30)   return palette[1];
    if (min < 60)   return palette[2];
    if (min < 90)   return palette[3];
    return palette[4];
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Always render 53 weeks (full calendar) so the SVG fills width with a
  // good aspect ratio.  The selected period is highlighted; everything outside
  // is dimmed with a translucent overlay drawn on top.
  const WEEKS = 53;
  const dayOfWeek = (today.getDay() + 6) % 7; // Mon=0
  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() - dayOfWeek - 52 * 7);

  // Format a Date in local time as YYYY-MM-DD (avoids UTC shift from toISOString)
  function localDateStr(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  const DAY_SIZE = 11;
  const DAY_GAP = 2;
  const CELL = DAY_SIZE + DAY_GAP;
  const LABEL_H = 18;
  const DOW_LABEL_W = 24;

  const DAY_NAMES = ["Mon", "Wed", "Fri"];
  const DAY_ROWS  = [0, 2, 4];

  const svgW = WEEKS * CELL;
  const svgH = LABEL_H + 7 * CELL;

  // Compute which week columns are "in focus" for the selected period
  let focusStartWeek = 0;
  let focusEndWeek   = WEEKS - 1;
  if (period === "week") {
    focusStartWeek = WEEKS - 1; // current week column only
  } else if (period === "month") {
    const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
    firstOfMonth.setHours(0, 0, 0, 0);
    focusStartWeek = Math.max(0, Math.floor((firstOfMonth - startDate) / (7 * 86400000)));
  } else if (period === "year") {
    const firstOfYear = new Date(today.getFullYear(), 0, 1);
    firstOfYear.setHours(0, 0, 0, 0);
    focusStartWeek = Math.max(0, Math.floor((firstOfYear - startDate) / (7 * 86400000)));
  }
  // "all": full range, no dimming

  // Pre-compute per-week date ranges for click handling
  // weekDates[week] = array of 7 dateStrings for that column
  const weekDates = [];
  const buildCur = new Date(startDate);
  for (let week = 0; week < WEEKS; week++) {
    const days = [];
    for (let dow = 0; dow < 7; dow++) {
      days.push(localDateStr(buildCur));
      buildCur.setDate(buildCur.getDate() + 1);
    }
    weekDates.push(days);
  }

  // Build SVG cells — each rect gets data-week index
  let cells = "";
  const cur = new Date(startDate);
  for (let week = 0; week < WEEKS; week++) {
    const dim = (week < focusStartWeek || week > focusEndWeek);
    for (let dow = 0; dow < 7; dow++) {
      const dateStr = localDateStr(cur);
      const info = lookup[dateStr] || { count: 0, duration_s: 0, distance_km: 0, activities: [] };
      const x = week * CELL;
      const y = LABEL_H + dow * CELL;
      const tip = info.duration_s > 0
        ? `${dateStr}: ${fmtDuration(info.duration_s)}, ${info.distance_km} km`
        : dateStr;
      cells += `<rect x="${x}" y="${y}" width="${DAY_SIZE}" height="${DAY_SIZE}" rx="0"
        fill="${colorFor(info.duration_s, dim)}" data-tip="${tip}" data-date="${dateStr}" data-week="${week}"
        style="cursor:pointer"/>`;
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
      monthLabels += `<text x="${week * CELL}" y="${LABEL_H - 4}" fill="#555" font-size="9" font-family="ui-monospace,monospace">${MONTH_NAMES[m]}</text>`;
      lastMonth = m;
    }
    labelCur.setDate(labelCur.getDate() + 7);
  }

  // Day-of-week labels on left
  let dowLabels = "";
  for (let i = 0; i < DAY_NAMES.length; i++) {
    const row = DAY_ROWS[i];
    const y = LABEL_H + row * CELL + DAY_SIZE - 1;
    dowLabels += `<text x="-2" y="${y}" fill="#3a3a3a" font-size="8" font-family="ui-monospace,monospace" text-anchor="end">${DAY_NAMES[i]}</text>`;
  }

  const svg = `<svg width="100%" viewBox="-${DOW_LABEL_W} 0 ${svgW + DOW_LABEL_W} ${svgH}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
    ${monthLabels}
    ${dowLabels}
    ${cells}
  </svg>`;

  container.innerHTML = svg;

  // Tooltip on hover
  const tooltipEl = tooltipId ? document.getElementById(tooltipId) : null;
  const detailEl  = detailId  ? document.getElementById(detailId)  : null;

  let activeWeek = null;

  container.querySelectorAll("rect[data-week]").forEach((rect) => {
    rect.addEventListener("mouseenter", () => {
      if (tooltipEl) tooltipEl.textContent = rect.getAttribute("data-tip");
    });
    rect.addEventListener("mouseleave", () => {
      if (tooltipEl) tooltipEl.textContent = "";
    });
    rect.addEventListener("click", () => {
      if (!detailEl) return;
      const weekIdx = parseInt(rect.getAttribute("data-week"), 10);

      // Toggle off if same week clicked again
      if (activeWeek === weekIdx) {
        activeWeek = null;
        detailEl.innerHTML = "";
        return;
      }
      activeWeek = weekIdx;

      // Gather all activities for this week's 7 days
      const days = weekDates[weekIdx];
      const weekStart = days[0];
      const weekEnd   = days[6];

      const allActivities = [];
      let totalDuration = 0, totalDistance = 0, totalCount = 0;
      for (const dateStr of days) {
        const info = lookup[dateStr];
        if (!info || !info.activities) continue;
        for (const a of info.activities) {
          allActivities.push({ ...a, date: dateStr });
          totalDuration += a.duration_s || 0;
          totalDistance += a.distance_km || 0;
          totalCount++;
        }
      }

      if (allActivities.length === 0) {
        detailEl.innerHTML = `<div style="border-top:1px solid #222;padding-top:10px;margin-top:6px;font-size:11px;color:var(--text-dim);">No activities for week of ${weekStart}</div>`;
        return;
      }

      const rows = allActivities.map(a => {
        const dist = a.distance_km > 0 ? `${a.distance_km} km` : "—";
        const nameCell = a.strava_id
          ? `<a href="/activities/${a.strava_id}" style="color:inherit;text-decoration:none;border-bottom:1px solid #333" onmouseover="this.style.color='var(--accent)'" onmouseout="this.style.color='inherit'">${a.name}</a>`
          : a.name;
        return `<tr>
          <td style="padding:3px 12px 3px 0;color:var(--text-dim);white-space:nowrap">${a.date}</td>
          <td style="padding:3px 12px 3px 0;color:var(--text-dim)">${a.sport_type || "—"}</td>
          <td style="padding:3px 12px 3px 0">${nameCell}</td>
          <td style="padding:3px 12px 3px 0;color:var(--accent);white-space:nowrap">${fmtDuration(a.duration_s)}</td>
          <td style="padding:3px 0;color:var(--text-dim);white-space:nowrap">${dist}</td>
        </tr>`;
      }).join("");

      detailEl.innerHTML = `
        <div style="border-top:1px solid #222;padding-top:10px;margin-top:6px;">
          <span style="font-size:11px;color:var(--text-dim);display:block;margin-bottom:8px;">
            Week of ${weekStart} → ${weekEnd} &nbsp;·&nbsp; ${totalCount} activit${totalCount === 1 ? "y" : "ies"} &nbsp;·&nbsp; ${fmtDuration(totalDuration)} &nbsp;·&nbsp; ${totalDistance.toFixed(1)} km
          </span>
          <table style="font-size:11px;font-family:ui-monospace,monospace;border-collapse:collapse;width:100%">${rows}</table>
        </div>`;
    });
  });
}


/**
 * Render VO2max estimate history.
 * Shows individual activity estimates as scatter (qualifying = purple, easy = gray)
 * and the rolling ratchet estimate as a solid line.
 * @param {string} canvasId
 * @param {{date: string, estimate: number, rolling_vo2max?: number, is_qualifying?: boolean}[]} data - oldest first
 */
function renderVo2maxChart(canvasId, data) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  const labels = data.map((d) => d.date);
  const hasRolling = data.some((d) => d.rolling_vo2max != null);

  // Individual estimates — color by qualifying status
  const scatterColors = data.map((d) =>
    d.is_qualifying ? "rgba(170,85,255,0.75)" : "rgba(120,120,120,0.35)"
  );
  const scatterBorder = data.map((d) =>
    d.is_qualifying ? "#aa55ff" : "#555555"
  );
  const scatterRadius = data.map((d) => (d.is_qualifying ? 4 : 3));

  const datasets = [
    {
      label: "Activity estimate",
      data: data.map((d) => d.estimate),
      type: "scatter",
      backgroundColor: scatterColors,
      borderColor: scatterBorder,
      pointRadius: scatterRadius,
      pointHoverRadius: 6,
      showLine: false,
      order: 2,
    },
  ];

  if (hasRolling) {
    datasets.unshift({
      label: "Rolling VO₂max",
      data: data.map((d) => d.rolling_vo2max ?? null),
      borderColor: "#00ff87",
      backgroundColor: "rgba(0,255,135,0.06)",
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.3,
      fill: false,
      order: 1,
    });
  }

  new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
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
            label: (item) => {
              const v = item.parsed.y;
              if (v == null) return null;
              const suffix = item.dataset.label === "Activity estimate"
                ? (data[item.dataIndex]?.is_qualifying ? " ✓" : " (easy)")
                : "";
              return ` ${item.dataset.label}: ${v.toFixed(1)}${suffix}`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(255,255,255,0.04)" },
          ticks: { maxTicksLimit: 10, maxRotation: 45, font: { size: 10, family: "ui-monospace, monospace" } },
        },
        y: {
          grid: { color: "rgba(255,255,255,0.04)" },
          title: { display: true, text: "ml/kg/min", color: "#888", font: { size: 10, family: "ui-monospace, monospace" } },
          ticks: { callback: (v) => v.toFixed(0), font: { size: 10, family: "ui-monospace, monospace" } },
          suggestedMin: 30,
        },
      },
    },
  });
}


/**
 * Render LT1 / LT2 / vVO2max pace evolution as a line chart.
 * @param {string} canvasId
 * @param {{date: string, derived_lt1_pace_s?: number, derived_lt2_pace_s?: number, derived_vo2max_pace_s?: number}[]} data - oldest first
 */
function renderPaceEvolutionChart(canvasId, data) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  const rows = data.filter(d => d.derived_lt1_pace_s || d.derived_lt2_pace_s || d.derived_vo2max_pace_s);
  if (rows.length === 0) return;

  const labels = rows.map(d => d.date);
  const allPaces = rows.flatMap(d => [d.derived_lt1_pace_s, d.derived_lt2_pace_s, d.derived_vo2max_pace_s].filter(Boolean));
  const paceMin = Math.min(...allPaces) * 0.96;
  const paceMax = Math.max(...allPaces) * 1.04;

  new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "LT1 (aerobic)",
          data: rows.map(d => d.derived_lt1_pace_s || null),
          borderColor: "#00ff87",
          backgroundColor: "rgba(0,255,135,0.06)",
          borderWidth: 1.5,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.3,
          fill: false,
        },
        {
          label: "LT2 (threshold)",
          data: rows.map(d => d.derived_lt2_pace_s || null),
          borderColor: "#ffaa00",
          backgroundColor: "rgba(255,170,0,0.06)",
          borderWidth: 1.5,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.3,
          fill: false,
        },
        {
          label: "vVO₂max",
          data: rows.map(d => d.derived_vo2max_pace_s || null),
          borderColor: "#ff3355",
          backgroundColor: "rgba(255,51,85,0.06)",
          borderWidth: 1.5,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.3,
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
            label: (item) => {
              const v = item.parsed.y;
              if (v === null || v === undefined) return null;
              return ` ${item.dataset.label}: ${_fmtMMSS(v)}/km`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(255,255,255,0.04)" },
          ticks: { maxTicksLimit: 10, maxRotation: 45, font: { size: 10, family: 'ui-monospace, monospace' } },
        },
        y: {
          reverse: true,
          min: paceMin,
          max: paceMax,
          grid: { color: "rgba(255,255,255,0.04)" },
          title: { display: true, text: "min/km", color: "#888", font: { size: 10, family: 'ui-monospace, monospace' } },
          ticks: {
            callback: (v) => _fmtMMSS(v),
            maxTicksLimit: 6,
            font: { size: 10, family: 'ui-monospace, monospace' },
          },
        },
      },
    },
  });
}


Chart.defaults.color = "#888888";
Chart.defaults.borderColor = "rgba(255,255,255,0.04)";
Chart.defaults.font.family = 'ui-monospace, monospace';
Chart.defaults.font.size = 10;

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
          borderColor: "#00aaff",
          backgroundColor: "rgba(0,170,255,0.06)",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        },
        {
          label: "ATL (Fatigue)",
          data: series.atl,
          borderColor: "#ffaa00",
          backgroundColor: "rgba(255,170,0,0.06)",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        },
        {
          label: "TSB (Form)",
          data: series.tsb,
          borderColor: "#00ff87",
          backgroundColor: "rgba(0,255,135,0.06)",
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
          grid: { color: "rgba(255,255,255,0.04)" },
          ticks: { maxTicksLimit: 10, maxRotation: 0 },
        },
        y: {
          grid: { color: "rgba(255,255,255,0.04)" },
          ticks: { callback: (v) => v.toFixed(0) },
        },
      },
    },
  });
}

/**
 * Format decimal hours as "Xh Ym".
 * @param {number} h
 * @returns {string}
 */
function _fmtHours(h) {
  const hrs = Math.floor(h);
  const mins = Math.round((h - hrs) * 60);
  return mins > 0 ? `${hrs}h ${mins}m` : `${hrs}h`;
}

/**
 * Render weekly training volume bar chart.
 * @param {string} canvasId
 * @param {{week_start: string, distance_km: number, duration_h: number, activity_count: number}[]} weeklyData
 * @param {{metric?: 'distance'|'time', runData?: Array, rideData?: Array}} [options]
 */
function renderWeeklyVolumeChart(canvasId, weeklyData, options = {}) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  const isTime  = (options.metric || 'distance') === 'time';
  const isSplit = !!(options.runData && options.rideData);

  const labels   = weeklyData.map((w) => w.week_start);
  const getValue = (w) => isTime ? w.duration_h : w.distance_km;
  const yUnit    = isTime ? 'h' : 'km';
  const fmtVal   = isTime ? _fmtHours : (v) => `${v.toFixed(1)} km`;

  const datasets = [];

  if (isSplit) {
    datasets.push({
      type: 'bar',
      label: `Running (${yUnit})`,
      data: options.runData.map(getValue),
      backgroundColor: 'rgba(0,170,255,0.30)',
      borderColor: '#00aaff',
      borderWidth: 1,
      borderRadius: 0,
      yAxisID: 'y',
      stack: 'vol',
    });
    datasets.push({
      type: 'bar',
      label: `Cycling (${yUnit})`,
      data: options.rideData.map(getValue),
      backgroundColor: 'rgba(255,170,0,0.30)',
      borderColor: '#ffaa00',
      borderWidth: 1,
      borderRadius: 0,
      yAxisID: 'y',
      stack: 'vol',
    });
  } else {
    const values  = weeklyData.map(getValue);
    const nonZero = values.filter((d) => d > 0);
    const avg     = nonZero.length ? nonZero.reduce((a, b) => a + b, 0) / nonZero.length : 0;
    datasets.push({
      type: 'bar',
      label: isTime ? 'Duration (h)' : 'Distance (km)',
      data: values,
      backgroundColor: 'rgba(0,170,255,0.25)',
      borderColor: '#00aaff',
      borderWidth: 1,
      borderRadius: 0,
      yAxisID: 'y',
    });
    datasets.push({
      type: 'line',
      label: `Avg ${yUnit}/week`,
      data: labels.map(() => parseFloat(avg.toFixed(3))),
      borderColor: 'rgba(0,255,135,0.4)',
      borderWidth: 1.5,
      borderDash: [5, 4],
      pointRadius: 0,
      fill: false,
      yAxisID: 'y',
    });
  }

  // Activity count (weeklyData is "all sports" in split mode)
  datasets.push({
    type: 'line',
    label: 'Activities',
    data: weeklyData.map((w) => w.activity_count),
    borderColor: '#ff3355',
    backgroundColor: 'rgba(255,51,85,0.06)',
    borderWidth: 1.5,
    pointRadius: 0,
    tension: 0.3,
    fill: false,
    yAxisID: 'y2',
  });

  new Chart(ctx, {
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top', labels: { usePointStyle: true, padding: 16 } },
        tooltip: {
          callbacks: {
            label: (item) => {
              if (item.dataset.label === 'Activities') return ` Activities: ${item.parsed.y}`;
              return ` ${item.dataset.label}: ${fmtVal(item.parsed.y)}`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { maxTicksLimit: 12, maxRotation: 45 },
          stacked: isSplit,
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          position: 'left',
          stacked: isSplit,
          title: { display: true, text: yUnit, color: '#888' },
          ticks: { callback: (v) => isTime ? `${v.toFixed(1)}h` : `${v} km` },
        },
        y2: {
          grid: { drawOnChartArea: false },
          position: 'right',
          title: { display: true, text: 'count', color: '#888' },
          ticks: { stepSize: 1, callback: (v) => v },
        },
      },
    },
  });
}
