// FitOps — Deep Analysis Page
// Stacked synchronized charts, range selection, segment overlays, scatter, power curve.

const ZONE_COLORS = {
  1: '#00aaff',
  2: '#00ff87',
  3: '#ffcc00',
  4: '#ff8800',
  5: '#ff3355',
  null: '#666',
};

// Shared state
const _da = {
  charts: [],
  map: null,
  hoverMarker: null,
  latlng: null,
  crosshairIdx: null,
  rangeStart: null,
  rangeEnd: null,
  segmentsVisible: false,
  singlePolyline: null,
  segmentPolylines: [],
  rangePolyline: null,
  distLabels: [],
  timeLabels: [],
  xAxisMode: 'distance',
  config: null,
  dragStartX: null,
  dragging: false,
};

// ── Helpers ─────────────────────────────────────────────────────────────────

function _fmtMMSS(seconds) {
  if (seconds == null || isNaN(seconds)) return '—';
  const s = Math.round(Math.abs(seconds));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

function _fmtDuration(seconds) {
  if (seconds == null) return '—';
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

function _mean(arr) {
  const valid = arr.filter(v => v != null && !isNaN(v) && v > 0);
  if (!valid.length) return null;
  return valid.reduce((a, b) => a + b, 0) / valid.length;
}

function _nearestIdx(latlng, lat, lng) {
  let best = 0, bestD = Infinity;
  for (let i = 0; i < latlng.length; i++) {
    const d = (latlng[i][0] - lat) ** 2 + (latlng[i][1] - lng) ** 2;
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

function _percentile(sorted, p) {
  return sorted[Math.floor(sorted.length * p)] ?? null;
}

// ── Main Entry Point ─────────────────────────────────────────────────────────

function initDeepAnalysis(config) {
  _da.config = config;
  const { streams, sportType, isRun, thresholds, dsStep, segments, laps, powerCurve } = config;

  // Build X-axis labels
  const dist = streams.distance || [];
  const time = streams.time || [];

  _da.distLabels = dist.map(d => d != null ? +(d / 1000).toFixed(3) : null);
  _da.timeLabels = time.map(t => t != null ? Math.round(t) : null);

  // Render map
  const latlng = streams.latlng || [];
  if (latlng.length > 1) {
    _daRenderMap(latlng, segments, dsStep);
  }

  // Create stacked charts (pace handled separately as a multi-dataset chart)
  const chartsToCreate = [
    { canvasId: 'da-chart-altitude',  panelId: 'da-panel-altitude',  key: 'altitude',     color: '#4488cc', fill: true,  yLabel: 'm',   reversed: false },
    { canvasId: 'da-chart-heartrate', panelId: 'da-panel-heartrate', key: 'heartrate',    color: '#ff3355', fill: false, yLabel: 'bpm', reversed: false },
    { canvasId: 'da-chart-watts',     panelId: 'da-panel-watts',     key: 'watts',        color: '#aa55ff', fill: false, yLabel: 'W',   reversed: false },
    { canvasId: 'da-chart-cadence',   panelId: 'da-panel-cadence',   key: 'cadence',      color: '#ffaa00', fill: false, yLabel: isRun ? 'spm' : 'rpm', reversed: false, cadence: isRun },
    { canvasId: 'da-chart-grade',     panelId: 'da-panel-grade',     key: 'grade_smooth', color: '#888',    fill: false, yLabel: '%',   reversed: false },
  ];

  for (const cfg of chartsToCreate) {
    const rawData = streams[cfg.key] || [];
    if (!rawData.length) continue;

    const panel = document.getElementById(cfg.panelId);
    if (panel) panel.style.display = '';

    let data = rawData;
    if (cfg.cadence && isRun) {
      data = rawData.map(v => v != null ? v * 2 : null);
    }

    const chart = _daCreateChart(cfg.canvasId, data, cfg, thresholds, segments, dsStep);
    if (chart) _da.charts.push(chart);
  }

  // Pace/Speed chart — multi-dataset with toggles
  const paceChart = _daCreatePaceChart(streams, isRun, thresholds, segments, dsStep);
  if (paceChart) _da.charts.push(paceChart);

  // Scatter plot
  _daRenderScatter(streams, isRun);

  // Power curve
  if (powerCurve && powerCurve.length) {
    const pcPanel = document.getElementById('da-power-curve-panel');
    if (pcPanel) pcPanel.style.display = '';
    _daRenderPowerCurve(powerCurve);
  }

  // Attach mouse events to canvases
  requestAnimationFrame(() => _daAttachRangeEvents());
}

// ── Map ──────────────────────────────────────────────────────────────────────

function _daRenderMap(latlng, segments, dsStep) {
  const container = document.getElementById('da-map');
  if (!container) return;

  _da.latlng = latlng;

  const map = L.map('da-map', { scrollWheelZoom: false, zoomControl: true });
  _da.map = map;

  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '© OpenStreetMap, © CARTO',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(map);

  const singleLine = L.polyline(latlng, { color: '#00ff87', weight: 2, opacity: 0.85 }).addTo(map);
  _da.singlePolyline = singleLine;
  map.fitBounds(singleLine.getBounds(), { padding: [12, 12] });

  L.circleMarker(latlng[0], { radius: 5, color: '#00ff87', fillColor: '#00ff87', fillOpacity: 1, weight: 2 }).addTo(map).bindTooltip('Start');
  L.circleMarker(latlng[latlng.length - 1], { radius: 5, color: '#ff3355', fillColor: '#ff3355', fillOpacity: 1, weight: 2 }).addTo(map).bindTooltip('End');

  _da.hoverMarker = L.circleMarker([0, 0], {
    radius: 5, color: '#fff', fillColor: '#fff', fillOpacity: 1, weight: 2, opacity: 0,
  }).addTo(map);

  // Map hover → sync charts
  const hitPoly = L.polyline(latlng, { color: 'transparent', weight: 20, opacity: 0.001 }).addTo(map);
  hitPoly.on('mousemove', (e) => {
    const idx = _nearestIdx(latlng, e.latlng.lat, e.latlng.lng);
    _daSyncAll(idx);
  });
  hitPoly.on('mouseout', () => {
    _daClearCrosshair();
  });

  // Pre-build segment polylines (hidden initially)
  if (segments && segments.length) {
    for (const seg of segments) {
      if (seg.start_index == null || seg.end_index == null) continue;
      const si = Math.min(Math.round(seg.start_index / dsStep), latlng.length - 1);
      const ei = Math.min(Math.round(seg.end_index / dsStep), latlng.length - 1);
      const color = ZONE_COLORS[seg.actual_zone] || ZONE_COLORS[null];
      const line = L.polyline(latlng.slice(si, ei + 1), { color, weight: 3, opacity: 0.9 });
      _da.segmentPolylines.push(line);
    }
  }
}

// ── Pace / Speed Chart (multi-dataset) ───────────────────────────────────────

function _daCreatePaceChart(streams, isRun, thresholds, segments, dsStep) {
  const canvas = document.getElementById('da-chart-pace');
  if (!canvas) return null;

  const panel = document.getElementById('da-panel-pace');
  const labels = _da.xAxisMode === 'distance' ? _da.distLabels : _da.timeLabels;
  const n = labels.length || 0;

  const datasets = [];
  const allPaceVals = []; // collect all values for percentile Y-axis

  // Primary: velocity_smooth → pace (s/km for run, km/h for cycling)
  if ((streams.velocity_smooth || []).length) {
    const raw = streams.velocity_smooth;
    let paceData;
    if (isRun) {
      paceData = raw.map(v => (v && v > 0.1) ? +(1000 / v).toFixed(1) : null);
    } else {
      paceData = raw.map(v => (v != null && v > 0.1) ? +(v * 3.6).toFixed(2) : null);
    }
    allPaceVals.push(...paceData.filter(v => v != null));
    datasets.push({
      label: isRun ? 'Pace' : 'Speed',
      data: n ? paceData.slice(0, n) : paceData,
      borderColor: '#00aaff',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.2,
      fill: false,
      spanGaps: true,
      _metricKey: 'pace',
    });
  }

  // GAP: grade_adjusted_speed or computed from velocity_smooth + grade_smooth (runs only)
  if (isRun) {
    const gasStream = streams.grade_adjusted_speed || [];
    let gapData = null;
    if (gasStream.length > 0) {
      gapData = gasStream.map(v => (v && v > 0.1) ? +(1000 / v).toFixed(1) : null);
    } else if ((streams.grade_smooth || []).length > 0 && (streams.velocity_smooth || []).length > 0) {
      gapData = streams.velocity_smooth.map((v, i) => {
        if (!v || v <= 0.1) return null;
        const g = streams.grade_smooth[i] || 0;
        const adj = v * (1 + 0.033 * g);
        return adj > 0.1 ? +(1000 / adj).toFixed(1) : null;
      });
    }
    if (gapData) {
      allPaceVals.push(...gapData.filter(v => v != null));
      datasets.push({
        label: 'GAP',
        data: n ? gapData.slice(0, n) : gapData,
        borderColor: '#00ccff',
        borderWidth: 1.5,
        borderDash: [5, 3],
        pointRadius: 0,
        tension: 0.2,
        fill: false,
        spanGaps: true,
        _metricKey: 'gap',
      });
    }
  }

  // WAP: weather-adjusted pace (wap_pace is in s/km)
  if ((streams.wap_pace || []).length > 0) {
    const wapData = isRun
      ? streams.wap_pace.map(v => v > 0 ? +v.toFixed(1) : null)
      : streams.wap_pace.map(v => v > 0 ? +(3600 / v).toFixed(2) : null);
    allPaceVals.push(...wapData.filter(v => v != null));
    datasets.push({
      label: isRun ? 'WAP' : 'WAP Speed',
      data: n ? wapData.slice(0, n) : wapData,
      borderColor: '#ff8800',
      borderWidth: 1.5,
      borderDash: [3, 2],
      pointRadius: 0,
      tension: 0.2,
      fill: false,
      spanGaps: true,
      _metricKey: 'wap',
    });
  }

  // True Pace/Speed (true_pace is in s/km)
  if ((streams.true_pace || []).length > 0) {
    const tpData = isRun
      ? streams.true_pace.map(v => v > 0 ? +v.toFixed(1) : null)
      : streams.true_pace.map(v => v > 0 ? +(3600 / v).toFixed(2) : null);
    allPaceVals.push(...tpData.filter(v => v != null));
    datasets.push({
      label: isRun ? 'True Pace' : 'True Speed',
      data: n ? tpData.slice(0, n) : tpData,
      borderColor: '#00ff87',
      borderWidth: 2,
      borderDash: [4, 2],
      pointRadius: 0,
      tension: 0.2,
      fill: false,
      spanGaps: true,
      _metricKey: 'tp',
    });
  }

  if (!datasets.length) return null;
  if (panel) panel.style.display = '';

  // Percentile-based Y-axis (same logic as charts.js)
  const sorted = [...allPaceVals].sort((a, b) => a - b);
  let yMin, yMax;
  if (isRun) {
    const p95 = _percentile(sorted, 0.95) || 600;
    yMin = 0;
    yMax = p95 * 1.05;
  } else {
    const p5  = _percentile(sorted, 0.05) || 0;
    const p95 = _percentile(sorted, 0.95) || 50;
    yMin = Math.max(0, p5 * 0.9);
    yMax = p95 * 1.1;
  }

  const PACE_DS_COLORS = { pace: '#00aaff', gap: '#00ccff', wap: '#ff8800', tp: '#00ff87' };

  const chart = new Chart(canvas, {
    type: 'line',
    data: { labels: n ? labels.slice(0, n) : _da.distLabels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      layout: { padding: { left: 4, right: 4 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: 'index',
          intersect: false,
          backgroundColor: 'rgba(0,0,0,0.85)',
          titleColor: '#888',
          bodyColor: '#eee',
          titleFont: { size: 10 },
          bodyFont: { size: 11, family: 'ui-monospace, monospace' },
          padding: 8,
          callbacks: {
            title: (items) => {
              if (!items.length) return '';
              const idx = items[0].dataIndex;
              const dl = _da.distLabels[idx];
              const tl = _da.timeLabels[idx];
              const parts = [];
              if (dl != null) parts.push(`${dl} km`);
              if (tl != null) parts.push(_fmtDuration(tl));
              return parts.join(' · ');
            },
            label: (item) => {
              const v = item.raw;
              if (v == null) return null;
              const lbl = item.dataset.label;
              if (isRun) return ` ${lbl}: ${_fmtMMSS(v)}/km`;
              return ` ${lbl}: ${parseFloat(v).toFixed(1)} km/h`;
            },
          },
        },
        daSegmentPlugin: { segments: segments || [], dsStep: dsStep || 1 },
        daCrosshairPlugin: {},
        daRangePlugin: {},
      },
      scales: {
        x: {
          display: false,
          ticks: { maxTicksLimit: 5 },
        },
        y: {
          position: 'left',
          reverse: isRun,
          min: yMin,
          max: yMax,
          grid: { color: 'rgba(255,255,255,0.04)' },
          border: { display: false },
          ticks: isRun
            ? { callback: v => _fmtMMSS(v), maxTicksLimit: 4, color: '#4a4a4a', font: { size: 9 } }
            : { callback: v => `${v.toFixed(0)}`, maxTicksLimit: 4, color: '#4a4a4a', font: { size: 9 } },
        },
      },
    },
    plugins: [daCrosshairPlugin, daSegmentPlugin, daRangePlugin],
  });

  chart._daKey = 'pace';
  chart._daColor = '#00aaff';

  // Build dataset toggle chips inside the panel label
  if (panel && datasets.length > 1) {
    const labelEl = panel.querySelector('.da-chart-label');
    if (labelEl) {
      const toggleWrap = document.createElement('div');
      toggleWrap.style.cssText = 'display:inline-flex;gap:5px;margin-left:8px;flex-wrap:wrap;';
      datasets.forEach((ds, i) => {
        const color = PACE_DS_COLORS[ds._metricKey] || '#888';
        const chip = document.createElement('button');
        chip.textContent = ds.label;
        chip.style.cssText = `background:none;border:1px solid ${color};color:${color};` +
          `font-size:9px;padding:1px 6px;border-radius:3px;cursor:pointer;` +
          `letter-spacing:0.05em;text-transform:uppercase;font-family:inherit;opacity:1;`;
        chip.dataset.dsIdx = i;
        chip.onclick = () => {
          const hidden = chart.isDatasetVisible(i) ? false : true; // toggle
          if (chart.isDatasetVisible(i)) {
            chart.hide(i);
            chip.style.opacity = '0.35';
          } else {
            chart.show(i);
            chip.style.opacity = '1';
          }
        };
        toggleWrap.appendChild(chip);
      });
      labelEl.appendChild(toggleWrap);
    }
  }

  return chart;
}

// ── Stacked Charts (single-dataset) ─────────────────────────────────────────

function _daCreateChart(canvasId, data, cfg, thresholds, segments, dsStep) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;

  const labels = _da.xAxisMode === 'distance' ? _da.distLabels : _da.timeLabels;
  const useLabels = labels.length ? labels : data.map((_, i) => i);
  const n = Math.min(data.length, useLabels.length || data.length);
  const chartData = data.slice(0, n);
  const chartLabels = useLabels.slice(0, n);

  const datasets = [{
    data: chartData,
    borderColor: cfg.color,
    borderWidth: 1.5,
    pointRadius: 0,
    pointHoverRadius: 3,
    tension: 0.2,
    fill: cfg.fill ? { target: 'origin', above: cfg.color + '22' } : false,
    spanGaps: true,
  }];

  // Threshold lines on HR chart
  if (cfg.key === 'heartrate') {
    if (thresholds.lt2) {
      datasets.push({
        data: Array(n).fill(thresholds.lt2),
        borderColor: '#ff3355',
        borderWidth: 1,
        borderDash: [4, 3],
        pointRadius: 0,
        fill: false,
        _isThreshold: true,
      });
    }
    if (thresholds.lt1) {
      datasets.push({
        data: Array(n).fill(thresholds.lt1),
        borderColor: '#ffcc00',
        borderWidth: 1,
        borderDash: [4, 3],
        pointRadius: 0,
        fill: false,
        _isThreshold: true,
      });
    }
  }

  // Compute Y-axis min/max from percentiles for HR chart
  let yOptions = {
    position: 'left',
    reverse: cfg.reversed || false,
    grid: { color: 'rgba(255,255,255,0.04)' },
    border: { display: false },
    ticks: cfg.key === 'velocity_smooth' && _da.config.isRun
      ? { callback: v => _fmtMMSS(v), maxTicksLimit: 4, color: '#4a4a4a', font: { size: 9 } }
      : { maxTicksLimit: 4, color: '#4a4a4a', font: { size: 9 } },
  };

  if (cfg.key === 'heartrate') {
    const hrVals = chartData.filter(v => v != null && v > 0).sort((a, b) => a - b);
    if (hrVals.length) {
      yOptions.min = Math.floor((_percentile(hrVals, 0.02) || hrVals[0]) * 0.92);
      yOptions.suggestedMax = (_percentile(hrVals, 0.98) || hrVals[hrVals.length - 1]) * 1.02;
    }
  }

  const yTicks = cfg.key === 'velocity_smooth' && _da.config.isRun
    ? { callback: v => _fmtMMSS(v), maxTicksLimit: 4, color: '#4a4a4a', font: { size: 9 } }
    : { maxTicksLimit: 4, color: '#4a4a4a', font: { size: 9 } };

  const chart = new Chart(canvas, {
    type: 'line',
    data: { labels: chartLabels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      layout: { padding: { left: 4, right: 4 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: 'index',
          intersect: false,
          backgroundColor: 'rgba(0,0,0,0.85)',
          titleColor: '#888',
          bodyColor: '#eee',
          titleFont: { size: 10 },
          bodyFont: { size: 11, family: 'ui-monospace, monospace' },
          padding: 8,
          callbacks: {
            title: (items) => {
              if (!items.length) return '';
              const idx = items[0].dataIndex;
              const dl = _da.distLabels[idx];
              const tl = _da.timeLabels[idx];
              const parts = [];
              if (dl != null) parts.push(`${dl} km`);
              if (tl != null) parts.push(_fmtDuration(tl));
              return parts.join(' · ');
            },
            label: (item) => {
              if (item.dataset._isThreshold) return null;
              const v = item.raw;
              if (v == null) return null;
              if (cfg.key === 'velocity_smooth' && _da.config.isRun) return ` ${_fmtMMSS(v)}/km`;
              if (cfg.key === 'heartrate') return ` ${Math.round(v)} bpm`;
              if (cfg.key === 'watts') return ` ${Math.round(v)} W`;
              if (cfg.key === 'cadence') return ` ${Math.round(v)} ${_da.config.isRun ? 'spm' : 'rpm'}`;
              if (cfg.key === 'altitude') return ` ${Math.round(v)} m`;
              if (cfg.key === 'grade_smooth') return ` ${v.toFixed(1)}%`;
              return ` ${typeof v === 'number' ? v.toFixed(1) : v} ${cfg.yLabel}`;
            },
            filter: item => !item.dataset._isThreshold,
          },
        },
        daSegmentPlugin: { segments: segments || [], dsStep: dsStep || 1, cfg },
        daCrosshairPlugin: {},
        daRangePlugin: {},
      },
      scales: {
        x: { display: false, ticks: { maxTicksLimit: 5 } },
        y: yOptions,
      },
    },
    plugins: [daCrosshairPlugin, daSegmentPlugin, daRangePlugin],
  });

  chart._daKey = cfg.key;
  chart._daColor = cfg.color;

  return chart;
}

// ── Cross-chart Sync ─────────────────────────────────────────────────────────

// Update ALL charts (crosshair + tooltip) to the given data index.
function _daSyncAll(idx) {
  _da.crosshairIdx = idx;

  for (const c of _da.charts) {
    const acts = c.data.datasets
      .map((_, di) => ({ datasetIndex: di, index: idx }))
      .filter(a => !c.data.datasets[a.datasetIndex]._isThreshold);
    c.tooltip.setActiveElements(acts, { x: 0, y: 0 });
    c.update('none');
  }

  if (_da.latlng && _da.latlng[idx]) {
    _da.hoverMarker.setLatLng(_da.latlng[idx]).setStyle({ opacity: 1, fillOpacity: 1 });
  }
}

function _daClearCrosshair() {
  _da.crosshairIdx = null;
  for (const c of _da.charts) {
    c.tooltip.setActiveElements([], { x: 0, y: 0 });
    c.update('none');
  }
  if (_da.hoverMarker) _da.hoverMarker.setStyle({ opacity: 0, fillOpacity: 0 });
}

// ── Crosshair Plugin ─────────────────────────────────────────────────────────

const daCrosshairPlugin = {
  id: 'daCrosshairPlugin',
  afterDraw(chart) {
    const idx = _da.crosshairIdx;
    if (idx == null) return;
    const meta = chart.getDatasetMeta(0);
    if (!meta || !meta.data[idx]) return;
    const { ctx } = chart;
    const x = meta.data[idx].x;
    const { top, bottom } = chart.chartArea;
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.strokeStyle = 'rgba(255,255,255,0.18)';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();
  },
};

// ── Segment Overlay Plugin ───────────────────────────────────────────────────

const daSegmentPlugin = {
  id: 'daSegmentPlugin',
  beforeDraw(chart) {
    if (!_da.segmentsVisible) return;
    const opts = chart.options.plugins.daSegmentPlugin || {};
    const { segments, dsStep } = opts;
    if (!segments || !segments.length) return;

    const { ctx, chartArea: { top, bottom, left, right } } = chart;
    const xScale = chart.scales.x;

    ctx.save();
    for (const seg of segments) {
      if (seg.start_index == null) continue;
      const si = Math.round(seg.start_index / dsStep);
      const ei = Math.round(seg.end_index / dsStep);
      const color = ZONE_COLORS[seg.actual_zone] || ZONE_COLORS[null];

      const x1 = Math.max(left, xScale.getPixelForValue(si));
      const x2 = Math.min(right, xScale.getPixelForValue(ei));
      if (x2 <= x1) continue;

      ctx.fillStyle = color + '18';
      ctx.fillRect(x1, top, x2 - x1, bottom - top);

      ctx.beginPath();
      ctx.setLineDash([4, 3]);
      ctx.strokeStyle = color + '99';
      ctx.lineWidth = 1;
      ctx.moveTo(x1, top);
      ctx.lineTo(x1, bottom);
      ctx.stroke();
    }

    const last = segments[segments.length - 1];
    if (last && last.end_index != null) {
      const ei = Math.round(last.end_index / dsStep);
      const x2 = Math.min(right, xScale.getPixelForValue(ei));
      const color = ZONE_COLORS[last.actual_zone] || ZONE_COLORS[null];
      ctx.beginPath();
      ctx.setLineDash([4, 3]);
      ctx.strokeStyle = color + '99';
      ctx.lineWidth = 1;
      ctx.moveTo(x2, top);
      ctx.lineTo(x2, bottom);
      ctx.stroke();
    }

    ctx.setLineDash([]);
    ctx.restore();
  },
};

// ── Range Selection Plugin ───────────────────────────────────────────────────

const daRangePlugin = {
  id: 'daRangePlugin',
  afterDraw(chart) {
    if (_da.rangeStart == null || _da.rangeEnd == null) return;
    const { ctx, chartArea: { top, bottom } } = chart;
    const xScale = chart.scales.x;
    const x1 = xScale.getPixelForValue(Math.min(_da.rangeStart, _da.rangeEnd));
    const x2 = xScale.getPixelForValue(Math.max(_da.rangeStart, _da.rangeEnd));
    ctx.save();
    ctx.fillStyle = 'rgba(255,170,0,0.12)';
    ctx.fillRect(x1, top, x2 - x1, bottom - top);
    ctx.strokeStyle = 'rgba(255,170,0,0.4)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x1, top); ctx.lineTo(x1, bottom); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x2, top); ctx.lineTo(x2, bottom); ctx.stroke();
    ctx.restore();
  },
};

// ── Mouse event handling ──────────────────────────────────────────────────────

function _daAttachRangeEvents() {
  // Also clear crosshair if mouse leaves the entire chart area
  document.addEventListener('mouseup', (e) => {
    if (!_da.dragging) return;
    _da.dragging = false;
    // Find which chart (if any) the mouse is over for final index
    // Use the last known rangeEnd
    const si = Math.min(_da.dragStartX ?? 0, _da.rangeEnd ?? 0);
    const ei = Math.max(_da.dragStartX ?? 0, _da.rangeEnd ?? 0);
    if (ei - si < 3) {
      daClearRange();
    } else {
      _da.rangeStart = si;
      _da.rangeEnd = ei;
      _daOnRangeSelected(si, ei);
      _da.charts.forEach(c => c.update('none'));
    }
  });

  for (const chart of _da.charts) {
    const canvas = chart.canvas;

    canvas.addEventListener('mousemove', (e) => {
      const idx = _daCanvasToIdx(e, chart);
      if (_da.dragging) {
        _da.rangeEnd = idx;
        _da.charts.forEach(c => c.update('none'));
      } else {
        _daSyncAll(idx);
      }
    });

    canvas.addEventListener('mouseleave', () => {
      if (!_da.dragging) _daClearCrosshair();
    });

    canvas.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      _da.dragging = true;
      _da.dragStartX = _daCanvasToIdx(e, chart);
      _da.rangeStart = _da.dragStartX;
      _da.rangeEnd = _da.dragStartX;
    });

    canvas.addEventListener('mouseup', (e) => {
      if (!_da.dragging) return;
      _da.dragging = false;
      const endIdx = _daCanvasToIdx(e, chart);
      const si = Math.min(_da.dragStartX, endIdx);
      const ei = Math.max(_da.dragStartX, endIdx);
      if (ei - si < 3) {
        daClearRange();
        return;
      }
      _da.rangeStart = si;
      _da.rangeEnd = ei;
      _daOnRangeSelected(si, ei);
      _da.charts.forEach(c => c.update('none'));
    });
  }
}

function _daCanvasToIdx(e, chart) {
  const rect = chart.canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const xScale = chart.scales.x;
  if (!xScale) return 0;
  const pxPerTick = (xScale.right - xScale.left) / Math.max(1, (chart.data.labels.length - 1));
  const idx = Math.round((x - xScale.left) / pxPerTick);
  return Math.max(0, Math.min(idx, chart.data.labels.length - 1));
}

function daClearRange() {
  _da.rangeStart = null;
  _da.rangeEnd = null;
  _da.charts.forEach(c => c.update('none'));
  const el = document.getElementById('da-range-stats');
  if (el) el.classList.remove('visible');
  if (_da.rangePolyline && _da.map) {
    _da.map.removeLayer(_da.rangePolyline);
    _da.rangePolyline = null;
  }
}

function _daOnRangeSelected(si, ei) {
  const streams = _da.config.streams;
  const latlng = _da.latlng || [];
  const isRun = _da.config.isRun;

  const timeStream  = streams.time || [];
  const hrStream    = streams.heartrate || [];
  const velStream   = streams.velocity_smooth || [];
  const wattsStream = streams.watts || [];
  const altStream   = streams.altitude || [];
  const distStream  = streams.distance || [];

  const durS   = (timeStream[ei] != null && timeStream[si] != null) ? timeStream[ei] - timeStream[si] : null;
  const distM  = (distStream[ei] != null && distStream[si] != null) ? distStream[ei] - distStream[si] : null;
  const avgHR  = _mean(hrStream.slice(si, ei + 1));
  const avgVel = _mean(velStream.slice(si, ei + 1));
  const avgW   = wattsStream.length ? _mean(wattsStream.slice(si, ei + 1)) : null;
  const altSlice = altStream.slice(si, ei + 1).filter(v => v != null);
  let elevGain = null;
  if (altSlice.length > 1) {
    elevGain = 0;
    for (let i = 1; i < altSlice.length; i++) {
      if (altSlice[i] > altSlice[i - 1]) elevGain += altSlice[i] - altSlice[i - 1];
    }
    elevGain = Math.round(elevGain);
  }

  const rows = [];
  if (durS  != null) rows.push(['Duration', _fmtDuration(durS)]);
  if (distM != null) rows.push(['Distance', `${(distM / 1000).toFixed(2)} km`]);
  if (avgHR != null) rows.push(['Avg HR', `${Math.round(avgHR)} bpm`]);
  if (avgVel != null) {
    if (isRun) rows.push(['Avg Pace', `${_fmtMMSS(1000 / avgVel)}/km`]);
    else rows.push(['Avg Speed', `${(avgVel * 3.6).toFixed(1)} km/h`]);
  }
  if (avgW       != null) rows.push(['Avg Power', `${Math.round(avgW)} W`]);
  if (elevGain   != null) rows.push(['Elev Gain', `${elevGain} m`]);

  const body = document.getElementById('da-range-stats-body');
  if (body) {
    body.innerHTML = rows.map(([k, v]) =>
      `<div class="da-range-stat-row"><span>${k}</span><span>${v}</span></div>`
    ).join('');
  }
  const panel = document.getElementById('da-range-stats');
  if (panel) panel.classList.add('visible');

  if (latlng.length && si < latlng.length && ei < latlng.length) {
    if (_da.rangePolyline && _da.map) _da.map.removeLayer(_da.rangePolyline);
    _da.rangePolyline = L.polyline(latlng.slice(si, ei + 1), {
      color: '#ffaa00', weight: 4, opacity: 0.85,
    }).addTo(_da.map);
  }
}

// ── X-Axis Toggle ────────────────────────────────────────────────────────────

function daSetXAxis(mode) {
  _da.xAxisMode = mode;
  document.getElementById('da-xaxis-dist').classList.toggle('active', mode === 'distance');
  document.getElementById('da-xaxis-time').classList.toggle('active', mode === 'time');

  const labels = mode === 'distance' ? _da.distLabels : _da.timeLabels;

  for (const chart of _da.charts) {
    chart.data.labels = labels.slice(0, chart.data.datasets[0].data.length);
    chart.options.scales.x.ticks = mode === 'time'
      ? { callback: v => _fmtDuration(v), maxTicksLimit: 6, color: '#4a4a4a', font: { size: 9 } }
      : { maxTicksLimit: 6, callback: v => `${v}`, color: '#4a4a4a', font: { size: 9 } };
    chart.update('none');
  }
}

// ── Segments Toggle ──────────────────────────────────────────────────────────

function daToggleSegments() {
  _da.segmentsVisible = !_da.segmentsVisible;
  const btn = document.getElementById('da-seg-toggle-btn');
  if (btn) btn.classList.toggle('active', _da.segmentsVisible);

  if (_da.map) {
    if (_da.segmentsVisible) {
      if (_da.singlePolyline) _da.map.removeLayer(_da.singlePolyline);
      _da.segmentPolylines.forEach(p => p.addTo(_da.map));
    } else {
      _da.segmentPolylines.forEach(p => _da.map.removeLayer(p));
      if (_da.singlePolyline) _da.singlePolyline.addTo(_da.map);
    }
  }

  _da.charts.forEach(c => c.update('none'));
}

// ── Segment Legend Hover ─────────────────────────────────────────────────────

function daHighlightSegment(idx, highlight) {
  const line = _da.segmentPolylines[idx];
  if (!line) return;
  line.setStyle(highlight ? { weight: 5, opacity: 1 } : { weight: 3, opacity: 0.9 });
}

// ── Lap Selection ────────────────────────────────────────────────────────────

function daSelectLap(lapIdx) {
  const lap = (_da.config.laps || [])[lapIdx];
  if (!lap || lap.start_idx == null || lap.end_idx == null) return;

  document.querySelectorAll('.da-lap-row').forEach(r => r.classList.remove('da-lap-active'));
  const row = document.getElementById(`da-lap-${lapIdx}`);
  if (row) row.classList.add('da-lap-active');

  _da.rangeStart = lap.start_idx;
  _da.rangeEnd = lap.end_idx;
  _da.charts.forEach(c => c.update('none'));
  _daOnRangeSelected(lap.start_idx, lap.end_idx);
}

// ── Scatter Plot ─────────────────────────────────────────────────────────────

function _daRenderScatter(streams, isRun) {
  const canvas = document.getElementById('da-scatter');
  if (!canvas) return;

  const hrStream    = streams.heartrate || [];
  const wattsStream = streams.watts || [];

  // For runs: prefer true_pace (s/km, already grade+weather adjusted), fall back to velocity_smooth
  let xStream, xIsAlreadyPace;
  if (isRun) {
    if ((streams.true_pace || []).length) {
      xStream = streams.true_pace;
      xIsAlreadyPace = true;  // values are already s/km
    } else {
      xStream = streams.velocity_smooth || [];
      xIsAlreadyPace = false;
    }
  } else {
    xStream = wattsStream;
  }

  if (!hrStream.length || !xStream.length) {
    const panel = canvas.closest('.da-section-panel');
    if (panel) panel.style.display = 'none';
    return;
  }

  const n = Math.min(hrStream.length, xStream.length);
  const points = [];

  for (let i = 0; i < n; i++) {
    const hr = hrStream[i];
    const xv = xStream[i];
    if (!hr || !xv || hr < 30 || hr > 250) continue;

    let xPlot;
    if (isRun) {
      if (xIsAlreadyPace) {
        if (xv <= 0 || xv > 900) continue; // filter stops/outliers (>15 min/km)
        xPlot = +xv.toFixed(1);
      } else {
        if (xv < 0.5) continue;
        xPlot = +(1000 / xv).toFixed(1);
      }
    } else {
      if (xv < 0) continue;
      xPlot = +xv.toFixed(1);
    }

    const t = i / (n - 1);
    const r = Math.round(t * 255);
    const g = Math.round(170 - t * 119);
    const b = Math.round(255 - t * 170);
    points.push({ x: xPlot, y: hr, color: `rgb(${r},${g},${b})` });
  }

  if (!points.length) {
    const panel = canvas.closest('.da-section-panel');
    if (panel) panel.style.display = 'none';
    return;
  }

  new Chart(canvas, {
    type: 'scatter',
    data: {
      datasets: [{
        data: points.map(p => ({ x: p.x, y: p.y })),
        backgroundColor: points.map(p => p.color + 'aa'),
        pointRadius: 2,
        pointHoverRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (item) => {
              const x = item.raw.x;
              const y = item.raw.y;
              const xLabel = isRun
                ? `${xIsAlreadyPace ? 'True Pace' : 'Pace'}: ${_fmtMMSS(x)}/km`
                : `Power: ${Math.round(x)} W`;
              return [`${xLabel}`, `HR: ${Math.round(y)} bpm`];
            },
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: isRun ? (xIsAlreadyPace ? 'True Pace (min/km)' : 'Pace (min/km)') : 'Power (W)', color: '#555', font: { size: 10 } },
          reverse: isRun,
          ticks: {
            callback: v => isRun ? _fmtMMSS(v) : v,
            color: '#4a4a4a',
            font: { size: 9 },
            maxTicksLimit: 6,
          },
          grid: { color: 'rgba(255,255,255,0.04)' },
        },
        y: {
          title: { display: true, text: 'Heart Rate (bpm)', color: '#555', font: { size: 10 } },
          ticks: { color: '#4a4a4a', font: { size: 9 } },
          grid: { color: 'rgba(255,255,255,0.04)' },
        },
      },
    },
  });
}

// ── Power-Duration Curve ──────────────────────────────────────────────────────

function _daRenderPowerCurve(curve) {
  const canvas = document.getElementById('da-power-curve');
  if (!canvas || !curve || !curve.length) return;

  new Chart(canvas, {
    type: 'line',
    data: {
      labels: curve.map(c => c.duration_label),
      datasets: [{
        data: curve.map(c => c.best_watts),
        borderColor: '#aa55ff',
        backgroundColor: '#aa55ff22',
        borderWidth: 2,
        pointRadius: 4,
        pointBackgroundColor: '#aa55ff',
        fill: true,
        tension: 0.2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: item => ` ${item.raw} W` } },
      },
      scales: {
        x: {
          ticks: { color: '#4a4a4a', font: { size: 9 } },
          grid: { color: 'rgba(255,255,255,0.04)' },
        },
        y: {
          ticks: { color: '#4a4a4a', font: { size: 9 } },
          grid: { color: 'rgba(255,255,255,0.04)' },
        },
      },
    },
  });
}
