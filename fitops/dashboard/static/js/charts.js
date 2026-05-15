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
 * Resample a time-indexed value stream to uniform distance intervals via linear interpolation.
 * @param {number[]} distStream - cumulative distance in meters at each time sample
 * @param {(number|null)[]} valueStream - values at each time sample
 * @param {number} stepMeters - desired spacing in meters between output samples
 * @returns {(number|null)[]}
 */
function _resampleAtDist(distStream, valueStream, stepMeters) {
  const n = Math.min(distStream.length, valueStream.length);
  if (n === 0 || stepMeters <= 0) return [];
  const totalDist = distStream[n - 1];
  const result = [];
  let j = 0;
  for (let d = 0; d <= totalDist + 1e-9; d += stepMeters) {
    // Advance j so distStream[j] is the last index <= d
    while (j < n - 1 && distStream[j + 1] <= d) j++;
    const d0 = distStream[j];
    const d1 = j + 1 < n ? distStream[j + 1] : d0;
    const v0 = valueStream[j];
    const v1 = j + 1 < n ? valueStream[j + 1] : v0;
    if (v0 == null || v1 == null) {
      result.push(null);
    } else if (d1 <= d0) {
      result.push(v0);
    } else {
      result.push(v0 + (v1 - v0) * ((d - d0) / (d1 - d0)));
    }
  }
  return result;
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

function _streamMetricTooltip(label, value, isRun) {
  if (value === null || value === undefined) return null;
  if (label === 'Heart Rate') return ` HR: ${Math.round(value)} bpm`;
  if (label === 'Pace')        return ` Pace: ${_fmtMMSS(value)}/km`;
  if (label === 'Speed')       return ` Speed: ${value.toFixed(1)} km/h`;
  if (label === 'GAP')         return ` GAP: ${_fmtMMSS(value)}/km`;
  if (label === 'WAP')         return ` WAP: ${_fmtMMSS(value)}/km`;
  if (label === 'WAP Speed')   return ` WAP: ${value.toFixed(1)} km/h`;
  if (label === 'True Pace')   return ` True Pace: ${_fmtMMSS(value)}/km`;
  if (label === 'True Speed')  return ` True Speed: ${value.toFixed(1)} km/h`;
  if (label === 'Altitude')    return ` Alt: ${Math.round(value)} m`;
  if (label === 'Cadence')     return ` Cadence: ${Math.round(value)} ${isRun ? 'spm' : 'rpm'}`;
  if (label === 'Power')       return ` Power: ${Math.round(value)} W`;
  return ` ${label}: ${value}`;
}

function _streamMetricUnit(label, isRun) {
  if (label === 'Heart Rate') return 'bpm';
  if (['Pace', 'GAP', 'WAP', 'True Pace'].includes(label)) return 'min/km';
  if (['Speed', 'WAP Speed', 'True Speed'].includes(label)) return 'km/h';
  if (label === 'Altitude') return 'm';
  if (label === 'Cadence') return isRun ? 'spm' : 'rpm';
  if (label === 'Power') return 'W';
  return label;
}

function _formatStreamTick(label, value) {
  if (['Pace', 'GAP', 'WAP', 'True Pace'].includes(label)) return _fmtMMSS(value);
  if (['Speed', 'WAP Speed', 'True Speed'].includes(label)) return Number(value).toFixed(1);
  return Number(value).toFixed(0);
}

function _getStreamAxisMode() {
  const btnDist = document.getElementById('xaxis-distance');
  return btnDist && btnDist.classList.contains('active') ? 'distance' : 'time';
}

function _streamLabelsForAxis(chart, mode) {
  return mode === 'distance' && chart._distLabels ? chart._distLabels : chart._timeLabels;
}

function _streamDataForAxis(ds, mode) {
  return mode === 'distance' && ds._distData ? ds._distData : ds._timeData;
}

function _syncStreamToggleButtons(chart, activeKey = null) {
  const container = document.getElementById('metric-toggles');
  if (!container || !chart) return;
  container.querySelectorAll('button[data-metric-key]').forEach((btn) => {
    const key = btn.dataset.metricKey;
    const datasets = chart._sidewaysMode && chart._normalStreamConfig
      ? chart._normalStreamConfig.datasets
      : chart.data.datasets;
    const dsIndex = datasets.findIndex(ds => ds._metricKey === key);
    const isActive = chart._sidewaysMode
      ? chart._sidewaysVisibleKeys && chart._sidewaysVisibleKeys.has(key)
      : (dsIndex >= 0 && chart.isDatasetVisible(dsIndex));
    const color = btn.dataset.metricColor || '#888';
    btn.style.background = isActive ? color + '18' : 'transparent';
    btn.style.color = isActive ? color : '#888';
    btn.style.borderColor = isActive ? color : '#444';
    btn.dataset.active = isActive ? '1' : '0';
  });
}

function _makeSidewaysScale(source, normalScales, axisIndex, totalAxes, isRun) {
  const original = normalScales[source.yAxisID] || {};
  const scale = {
    ...original,
    type: 'linear',
    axis: 'x',
    position: axisIndex % 2 === 0 ? 'top' : 'bottom',
    grid: {
      ...(original.grid || {}),
      drawOnChartArea: axisIndex === 0,
      color: axisIndex === 0 ? 'rgba(255,255,255,0.04)' : 'rgba(255,255,255,0.015)',
    },
    title: {
      ...(original.title || {}),
      display: true,
      text: `${source.label} (${_streamMetricUnit(source.label, isRun)})`,
      color: source.borderColor || (original.title && original.title.color) || '#888',
      font: { size: 10, family: 'ui-monospace, monospace' },
    },
      ticks: {
        ...(original.ticks || {}),
        color: source.borderColor || (original.ticks && original.ticks.color) || '#888',
        font: { size: 10, family: 'ui-monospace, monospace' },
        minRotation: 90,
        maxRotation: 90,
        maxTicksLimit: 6,
        callback: v => _formatStreamTick(source.label, v),
      },
  };
  if (source.yAxisID === 'yPace' && isRun) scale.reverse = true;
  if (scale.display === false) scale.display = true;
  if (axisIndex > 1 || totalAxes > 3) {
    scale.title.display = axisIndex < 2;
  }
  return scale;
}

function _buildSidewaysDataset(source, labels, axisMode) {
  const values = _streamDataForAxis(source, axisMode) || [];
  const points = [];
  const n = Math.min(labels.length, values.length);
  for (let i = 0; i < n; i += 1) {
    const value = values[i];
    if (value === null || value === undefined || Number.isNaN(Number(value))) continue;
    points.push({ x: Number(value), y: labels[i] });
  }
  if (!points.length) return null;
  return {
    label: source.label,
    data: points,
    borderColor: source.borderColor,
    backgroundColor: source.backgroundColor || source.borderColor,
    borderWidth: source.borderWidth || 1.5,
    borderDash: source.borderDash || [],
    pointRadius: 0,
    tension: source.tension || 0.2,
    fill: false,
    parsing: false,
    xAxisID: `x${source.yAxisID}`,
    _metricKey: source._metricKey,
    _sourceLabel: source.label,
  };
}

function _streamChartIndexAtPixel(chart, xPixel) {
  if (!chart || !chart.scales || !chart.scales.x) return null;
  const labels = chart.data && chart.data.labels ? chart.data.labels : [];
  if (!labels.length) return null;
  const raw = chart.scales.x.getValueForPixel(xPixel);
  const idx = Number.isFinite(raw) ? Math.round(raw) : labels.indexOf(raw);
  if (!Number.isFinite(idx) || idx < 0) return null;
  return Math.max(0, Math.min(labels.length - 1, idx));
}

function _streamChartEventInArea(chart, event) {
  if (!chart || !chart.chartArea || !event) return false;
  const { left, right, top, bottom } = chart.chartArea;
  return event.x >= left && event.x <= right && event.y >= top && event.y <= bottom;
}

function _captureStreamScaleBounds(scales) {
  const out = {};
  for (const [id, scale] of Object.entries(scales || {})) {
    out[id] = {
      min: scale.min,
      max: scale.max,
      suggestedMin: scale.suggestedMin,
      suggestedMax: scale.suggestedMax,
    };
  }
  return out;
}

function _restoreStreamScaleBounds(scale, bounds) {
  if (!scale || !bounds) return;
  ['min', 'max', 'suggestedMin', 'suggestedMax'].forEach((key) => {
    if (bounds[key] === undefined) {
      delete scale[key];
    } else {
      scale[key] = bounds[key];
    }
  });
}

function _syncStreamZoomResetButton(chart) {
  const btn = document.getElementById('stream-zoom-reset');
  if (!btn) return;
  btn.hidden = !(chart && chart._streamZoomRange);
}

function _isCoarseStreamPointer(event = null) {
  const nativeEvent = event && event.native ? event.native : event;
  if (nativeEvent && nativeEvent.type && nativeEvent.type.startsWith('touch')) return true;
  return !!(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
}

function _setStreamChartActiveIndex(chart, idx) {
  if (!chart || idx === null || idx === undefined) return;
  const labels = chart.data && chart.data.labels ? chart.data.labels : [];
  if (!labels.length) return;
  const safeIdx = Math.max(0, Math.min(labels.length - 1, Number(idx)));
  if (!Number.isFinite(safeIdx)) return;

  const active = chart.data.datasets
    .map((_, datasetIndex) => ({ datasetIndex, index: safeIdx }))
    .filter((item) => !chart.data.datasets[item.datasetIndex]._isThreshold && chart.isDatasetVisible(item.datasetIndex));
  if (typeof chart.setActiveElements === 'function') chart.setActiveElements(active);
  if (chart.tooltip && typeof chart.tooltip.setActiveElements === 'function') {
    const x = chart.scales && chart.scales.x ? chart.scales.x.getPixelForValue(safeIdx) : 0;
    chart.tooltip.setActiveElements(active, { x, y: chart.chartArea ? chart.chartArea.top : 0 });
  }

  const ll = _activitySync.latlng;
  if (_activitySync.hoverMarker && ll && ll[safeIdx]) {
    _activitySync.hoverMarker.setLatLng(ll[safeIdx]).setStyle({ opacity: 1, fillOpacity: 1 });
  }
  _syncStreamMobileScrubber(chart, safeIdx);
  chart.update('none');
}

function _syncStreamMobileScrubber(chart, activeIdx = null) {
  const wrap = document.getElementById('stream-mobile-scrubber');
  const input = document.getElementById('stream-scrub-range');
  const label = document.getElementById('stream-scrub-label');
  if (!wrap || !input || !label || !chart) return;

  const labels = chart.data && chart.data.labels ? chart.data.labels : [];
  const max = Math.max(0, labels.length - 1);
  input.max = String(max);
  if (activeIdx !== null && activeIdx !== undefined) {
    input.value = String(Math.max(0, Math.min(max, Number(activeIdx))));
  } else if (Number(input.value) > max) {
    input.value = String(max);
  }
  label.textContent = labels[Number(input.value)] || '0:00';
  wrap.hidden = labels.length < 2;
}

function initStreamMobileScrubber(chart) {
  const input = document.getElementById('stream-scrub-range');
  if (!input || !chart) return;
  _syncStreamMobileScrubber(chart, 0);
  input.addEventListener('input', () => {
    _setStreamChartActiveIndex(chart, Number(input.value));
  });
}

function _streamPointValue(point) {
  if (point === null || point === undefined) return null;
  const value = typeof point === 'object' ? point.y : point;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function _updateStreamZoomYRanges(chart) {
  if (!chart || !chart._streamZoomRange || !chart._streamOriginalScaleBounds) return;
  const [start, end] = chart._streamZoomRange;
  const lo = Math.min(start, end);
  const hi = Math.max(start, end);
  const scales = chart.options.scales || {};

  for (const [scaleId, scale] of Object.entries(scales)) {
    if (scaleId === 'x') continue;
    _restoreStreamScaleBounds(scale, chart._streamOriginalScaleBounds[scaleId]);

    const values = [];
    chart.data.datasets.forEach((ds, dsIndex) => {
      if (!ds.yAxisID || ds.yAxisID !== scaleId || ds._isThreshold) return;
      if (!chart.isDatasetVisible(dsIndex)) return;
      const data = ds.data || [];
      for (let i = lo; i <= hi && i < data.length; i += 1) {
        const value = _streamPointValue(data[i]);
        if (value !== null) values.push(value);
      }
    });
    if (!values.length) continue;

    let min = Math.min(...values);
    let max = Math.max(...values);
    const span = Math.max(1, max - min);
    const pad = span * 0.08;
    min -= pad;
    max += pad;
    if (scaleId !== 'yHR') min = Math.max(0, min);
    scale.min = min;
    scale.max = max;
    delete scale.suggestedMin;
    delete scale.suggestedMax;
  }
}

function _applyStreamZoomRange(chart, start, end) {
  if (!chart || chart._sidewaysMode || !chart.options.scales || !chart.options.scales.x) return;
  const labels = chart.data.labels || [];
  if (!labels.length) return;
  const lo = Math.max(0, Math.min(start, end));
  const hi = Math.min(labels.length - 1, Math.max(start, end));
  if (hi - lo < 2) return;

  if (!chart._streamOriginalScaleBounds) {
    chart._streamOriginalScaleBounds = _captureStreamScaleBounds(chart.options.scales);
  }
  chart._streamZoomRange = [lo, hi];
  chart.options.scales.x.min = lo;
  chart.options.scales.x.max = hi;
  _updateStreamZoomYRanges(chart);
  _syncStreamZoomResetButton(chart);
  chart.update('none');
}

function _clearStreamZoom(chart, shouldUpdate = true) {
  if (!chart || !chart.options.scales) return;
  if (chart._streamOriginalScaleBounds) {
    for (const [scaleId, scale] of Object.entries(chart.options.scales)) {
      _restoreStreamScaleBounds(scale, chart._streamOriginalScaleBounds[scaleId]);
    }
  } else if (chart.options.scales.x) {
    delete chart.options.scales.x.min;
    delete chart.options.scales.x.max;
  }
  chart._streamZoomRange = null;
  if (chart._streamZoomState) {
    chart._streamZoomState.dragging = false;
    chart._streamZoomState.dragStart = null;
    chart._streamZoomState.dragCurrent = null;
    chart._streamZoomState.clickStart = null;
    chart._streamZoomState.clickCurrent = null;
  }
  _syncStreamZoomResetButton(chart);
  if (shouldUpdate) chart.update('none');
}

function resetStreamZoom() {
  _clearStreamZoom(window._activeStreamChart);
}

function _clearStreamZoomSelectionState(state) {
  if (!state) return;
  state.dragging = false;
  state.dragStart = null;
  state.dragCurrent = null;
  state.moved = false;
  state.clickStart = null;
  state.clickCurrent = null;
}

function _drawStreamZoomSelection(chart, start, end, fillStyle, strokeStyle) {
  if (!chart || !chart.scales || !chart.scales.x || start === null || end === null) return;
  const { ctx, chartArea } = chart;
  if (!chartArea) return;
  const x0 = chart.scales.x.getPixelForValue(start);
  const x1 = chart.scales.x.getPixelForValue(end);
  if (!Number.isFinite(x0) || !Number.isFinite(x1)) return;
  const left = Math.max(chartArea.left, Math.min(x0, x1));
  const right = Math.min(chartArea.right, Math.max(x0, x1));
  ctx.save();
  ctx.fillStyle = fillStyle;
  ctx.strokeStyle = strokeStyle;
  ctx.lineWidth = 1;
  ctx.fillRect(left, chartArea.top, Math.max(1, right - left), chartArea.bottom - chartArea.top);
  ctx.strokeRect(left, chartArea.top, Math.max(1, right - left), chartArea.bottom - chartArea.top);
  ctx.restore();
}

const streamRangeZoomPlugin = {
  id: 'streamRangeZoom',
  afterEvent(chart, args) {
    if (!chart._isStreamChart || chart._sidewaysMode || !args || !args.event) return;
    const event = args.event;
    const type = event.type;
    const state = chart._streamZoomState || (chart._streamZoomState = {
      dragging: false,
      dragStart: null,
      dragCurrent: null,
      moved: false,
      clickStart: null,
      clickCurrent: null,
      justDragged: false,
    });
    const inArea = _streamChartEventInArea(chart, event);
    const idx = _streamChartIndexAtPixel(chart, event.x);

    if (type === 'dblclick') {
      _clearStreamZoomSelectionState(state);
      _clearStreamZoom(chart);
      args.changed = true;
      return;
    }

    if ((type === 'mousedown' || type === 'touchstart') && inArea && idx !== null) {
      if (state.clickStart !== null) {
        state.clickCurrent = idx;
        args.changed = true;
        return;
      }
      state.dragging = true;
      state.dragStart = idx;
      state.dragCurrent = idx;
      state.moved = false;
      args.changed = true;
      return;
    }

    if ((type === 'mousemove' || type === 'touchmove') && state.dragging && idx !== null) {
      state.dragCurrent = idx;
      state.moved = Math.abs(state.dragCurrent - state.dragStart) >= 2;
      args.changed = true;
      return;
    }

    if ((type === 'mousemove' || type === 'touchmove') && state.clickStart !== null && inArea && idx !== null) {
      state.clickCurrent = idx;
      args.changed = true;
      return;
    }

    if ((type === 'mouseup' || type === 'touchend') && state.dragging) {
      const end = idx !== null ? idx : state.dragCurrent;
      if (state.moved && end !== null) {
        _applyStreamZoomRange(chart, state.dragStart, end);
        state.justDragged = true;
        setTimeout(() => { state.justDragged = false; }, 0);
      }
      state.dragging = false;
      state.dragStart = null;
      state.dragCurrent = null;
      state.moved = false;
      args.changed = true;
      return;
    }

    if (type === 'click' && inArea && idx !== null) {
      if (_isCoarseStreamPointer(event)) {
        _clearStreamZoomSelectionState(state);
        _setStreamChartActiveIndex(chart, idx);
        args.changed = true;
        return;
      }
      if (state.justDragged) return;
      if (state.clickStart === null) {
        state.clickStart = idx;
        state.clickCurrent = idx;
      } else {
        _applyStreamZoomRange(chart, state.clickStart, idx);
        state.clickStart = null;
        state.clickCurrent = null;
      }
      args.changed = true;
    }
  },
  afterDraw(chart) {
    if (!chart._isStreamChart || chart._sidewaysMode) return;
    const state = chart._streamZoomState;
    if (!state) return;
    if (state.dragging && state.dragStart !== null && state.dragCurrent !== null) {
      _drawStreamZoomSelection(chart, state.dragStart, state.dragCurrent, 'rgba(0,255,135,0.10)', 'rgba(0,255,135,0.55)');
    } else if (state.clickStart !== null && state.clickCurrent !== null) {
      _drawStreamZoomSelection(chart, state.clickStart, state.clickCurrent, 'rgba(0,255,135,0.14)', 'rgba(0,255,135,0.70)');
    }
  },
};

function setStreamChartSidewaysMode(chart, enabled, preferredKey = null) {
  if (!chart || !chart._isStreamChart) return;

  if (!chart._normalStreamConfig) {
    chart._normalStreamConfig = {
      labels: chart.data.labels,
      datasets: chart.data.datasets,
      scales: chart.options.scales,
      interaction: chart.options.interaction,
      onHover: chart.options.onHover,
      tooltip: chart.options.plugins.tooltip,
    };
  }

  if (!enabled) {
    const normal = chart._normalStreamConfig;
    chart._sidewaysMode = false;
    chart.data.labels = normal.labels;
    chart.data.datasets = normal.datasets;
    if (chart._sidewaysVisibleKeys) {
      normal.datasets.forEach((ds, i) => {
        if (!ds._metricKey || ds._isThreshold) return;
        chart.setDatasetVisibility(i, chart._sidewaysVisibleKeys.has(ds._metricKey));
        ds.hidden = !chart._sidewaysVisibleKeys.has(ds._metricKey);
      });
    }
    chart.options.scales = normal.scales;
    chart.options.interaction = normal.interaction;
    chart.options.onHover = normal.onHover;
    chart.options.plugins.tooltip = normal.tooltip;
    _syncStreamToggleButtons(chart);
    chart.update('none');
    return;
  }

  const normal = chart._normalStreamConfig;
  const normalDatasets = normal.datasets || [];
  const metricDatasets = normalDatasets.filter(ds => ds._metricKey && !ds._isThreshold);
  if (!metricDatasets.length) return;

  if (!chart._sidewaysMode) {
    chart._sidewaysVisibleKeys = new Set(
      metricDatasets
        .filter((ds, i) => {
          const normalIndex = normalDatasets.indexOf(ds);
          return chart.isDatasetVisible(normalIndex);
        })
        .map(ds => ds._metricKey)
    );
  }
  if (preferredKey) {
    if (chart._sidewaysVisibleKeys.has(preferredKey)) {
      chart._sidewaysVisibleKeys.delete(preferredKey);
    } else {
      chart._sidewaysVisibleKeys.add(preferredKey);
    }
  }
  if (!chart._sidewaysVisibleKeys.size) {
    const fallback = metricDatasets[0];
    chart._sidewaysVisibleKeys.add(fallback._metricKey);
  }

  const axisMode = _getStreamAxisMode();
  const labels = _streamLabelsForAxis(chart, axisMode) || [];
  const selectedSources = metricDatasets.filter(ds => chart._sidewaysVisibleKeys.has(ds._metricKey));
  const sidewaysDatasets = selectedSources
    .map(ds => _buildSidewaysDataset(ds, labels, axisMode))
    .filter(Boolean);
  if (!sidewaysDatasets.length) return;

  chart._sidewaysMode = true;
  chart.data.labels = labels;
  chart.data.datasets = sidewaysDatasets;
  chart.options.onHover = null;
  chart.options.interaction = { mode: 'index', axis: 'y', intersect: false };
  chart.options.plugins.tooltip = {
    callbacks: {
      title: (items) => items && items[0] ? `${axisMode === 'distance' ? 'Distance' : 'Time'}: ${items[0].raw.y}` : '',
      label: (item) => _streamMetricTooltip(item.dataset._sourceLabel || item.dataset.label, item.raw.x, chart._isRunSport),
    },
  };
  const uniqueAxisSources = [];
  for (const source of selectedSources) {
    if (!uniqueAxisSources.find(ds => ds.yAxisID === source.yAxisID)) uniqueAxisSources.push(source);
  }
  const sidewaysScales = {};
  uniqueAxisSources.forEach((source, i) => {
    sidewaysScales[`x${source.yAxisID}`] = _makeSidewaysScale(source, normal.scales, i, uniqueAxisSources.length, chart._isRunSport);
  });
  chart.options.scales = {
    ...sidewaysScales,
    y: {
      type: 'category',
      labels,
      reverse: true,
      title: {
        display: true,
        text: axisMode === 'distance' ? 'Distance (km)' : 'Time',
        color: '#888',
        font: { size: 10, family: 'ui-monospace, monospace' },
      },
      grid: { color: 'rgba(255,255,255,0.04)' },
      ticks: {
        color: '#888',
        font: { size: 10, family: 'ui-monospace, monospace' },
        maxTicksLimit: 6,
      },
    },
  };
  _syncStreamToggleButtons(chart);
  chart.update('none');
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
  const existingChart = Chart.getChart(ctx);
  if (existingChart) existingChart.destroy();

  const RUN_SPORTS = new Set(['Run', 'TrailRun', 'VirtualRun', 'Walk', 'Hike']);
  const isRun = RUN_SPORTS.has(sportType);

  // X-axis label arrays
  // Distance labels are built at uniform distance intervals so that the chart
  // compresses fast sections and expands slow ones (true distance-axis behaviour).
  // Time labels stay at 1-sample-per-second (uniform time).
  const rawDistStream = streams.distance || [];
  let distLabels = null;
  let _distStep = 0;
  if (rawDistStream.length > 0) {
    const totalDistM = rawDistStream[rawDistStream.length - 1];
    // Target ~1000 display points; clamp to at least 10 m per step.
    _distStep = Math.max(10, Math.round(totalDistM / 1000));
    distLabels = [];
    for (let d = 0; d <= totalDistM + 1e-9; d += _distStep) {
      distLabels.push((d / 1000).toFixed(2));
    }
  }
  const timeLabels = (streams.time || []).map(s => _fmtMMSS(s));
  // Default to time mode.
  const xLabels = timeLabels.length > 0 ? timeLabels : (distLabels ?? []);

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
    const altVals = streams.altitude.filter(v => v != null && v > -9999);
    scales.yAlt = { display: false, position: 'right' };
    if (altVals.length) {
      scales.yAlt.min = Math.min(...altVals) * 0.9;
      scales.yAlt.suggestedMax = Math.max(...altVals) * 1.05;
    }
  }

  // Heart Rate
  if ((streams.heartrate || []).length > 0) {
    const hrVals = streams.heartrate.filter(v => v && v > 0);
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
      ticks: { color: '#ff3355', font: { size: 10, family: 'ui-monospace, monospace' } },
    };
    if (hrVals.length) {
      scales.yHR.min = Math.floor(Math.min(...hrVals) * 0.88);
      scales.yHR.suggestedMax = Math.max(...hrVals) * 1.02;
    }

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
    const cadVals = cadData.filter(v => v && v > 0);
    scales.yCad = { display: false, position: 'right' };
    if (cadVals.length) {
      scales.yCad.min = Math.min(...cadVals) * 0.85;
      scales.yCad.suggestedMax = Math.max(...cadVals) * 1.05;
    }
  }

  // Power (hidden by default) — Strava cycling watts or estimated running power
  const _pwrStream = streams.watts || streams.power || [];
  if (_pwrStream.length > 0) {
    datasets.push({
      label: 'Power',
      data: _pwrStream,
      borderColor: '#aa55ff',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.2,
      yAxisID: 'yPwr',
      fill: false,
      hidden: true,
      _metricKey: 'pwr',
    });
    const pwrVals = _pwrStream.filter(v => v && v > 0);
    scales.yPwr = { display: false, position: 'right', min: 0 };
    if (pwrVals.length) {
      scales.yPwr.suggestedMax = Math.max(...pwrVals) * 1.05;
    }
  }

  // ── Build per-dataset time / distance data arrays ──────────────────────────
  // Datasets were built with time-indexed (1/sec) arrays. When a distance stream
  // is present we also compute distance-resampled arrays so that toggling the
  // x-axis actually reshapes the traces (fast → compressed, slow → expanded).
  if (distLabels && rawDistStream.length > 0) {
    for (const ds of datasets) {
      if (ds._isThreshold) {
        // Constant threshold lines — resize to match each axis's label count.
        const val = ds.data[0];
        ds._timeData = Array(timeLabels.length).fill(val);
        ds._distData = Array(distLabels.length).fill(val);
      } else {
        ds._timeData = ds.data.slice();
        ds._distData = _resampleAtDist(rawDistStream, ds.data, _distStep);
      }
      // Start in time mode (matches the default xLabels = timeLabels).
      ds.data = ds._timeData;
    }
  } else {
    for (const ds of datasets) {
      ds._timeData = ds.data;
      ds._distData = null;
    }
  }

  const crosshairPlugin = {
    id: 'crosshair',
    afterDraw(ch) {
      const active = typeof ch.getActiveElements === 'function'
        ? ch.getActiveElements()
        : (ch.tooltip && typeof ch.tooltip.getActiveElements === 'function'
          ? ch.tooltip.getActiveElements()
          : []);
      if (!active || !active.length) return;
      if (!ch.chartArea || !ch.scales || !ch.scales.x) return;
      const { ctx, chartArea: { top, bottom }, scales: { x } } = ch;
      const xPos = x.getPixelForValue(active[0].index);
      if (!Number.isFinite(xPos)) return;
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
    plugins: [crosshairPlugin, streamRangeZoomPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      events: ['mousemove', 'mouseout', 'click', 'dblclick', 'mousedown', 'mouseup', 'touchstart', 'touchmove', 'touchend'],
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
        _syncStreamMobileScrubber(window._activeStreamChart, idx);
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
              return _streamMetricTooltip(ds.label, v, isRun);
            },
          },
        },
      },
      scales,
    },
  });

  // Store label arrays for x-axis toggle
  chart._distLabels = distLabels && distLabels.length > 0 ? distLabels : null;
  chart._timeLabels = timeLabels.length > 0 ? timeLabels : null;
  chart._isStreamChart = true;
  chart._isRunSport = isRun;
  window._activeStreamChart = chart;
  _activitySync.chart = chart;
  _syncStreamZoomResetButton(chart);
  initStreamMobileScrubber(chart);

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
  if (!container) return;
  container.innerHTML = '';

  const _isRun = new Set(['Run', 'TrailRun', 'VirtualRun', 'Walk', 'Hike']).has(sportType);
  const METRICS = [
    { key: 'hr',   label: 'HR',                      color: '#ff3355', defaultOn: true  },
    { key: 'pace', label: _isRun ? 'Pace' : 'Speed', color: '#00aaff', defaultOn: true  },
    { key: 'gap',  label: 'GAP',                      color: '#00ccff', defaultOn: true  },
    { key: 'wap',  label: _isRun ? 'WAP' : 'WAP Speed',        color: '#ff8800', defaultOn: true  },
    { key: 'tp',   label: _isRun ? 'True Pace' : 'True Speed', color: '#00ff87', defaultOn: true  },
    { key: 'alt',  label: 'Altitude',                color: '#4488cc', defaultOn: true  },
    { key: 'cad',  label: 'Cadence',                 color: '#ffaa00', defaultOn: false },
    { key: 'pwr',  label: 'Power',                   color: '#aa55ff', defaultOn: false },
  ];

  METRICS.forEach(({ key, label, color, defaultOn }) => {
    if (!available[key]) return;

    const btn = document.createElement('button');
    btn.textContent = label;
    btn.dataset.metricKey = key;
    btn.dataset.metricColor = color;
    btn.dataset.active = defaultOn ? '1' : '0';
    btn.style.cssText = `
      padding: 3px 10px;
      border-radius: 3px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      cursor: pointer;
      transition: all 0.1s;
      font-family: ui-monospace, monospace;
      border: 1px solid ${defaultOn ? color : '#444'};
      background: ${defaultOn ? color + '18' : 'transparent'};
      color: ${defaultOn ? color : '#888'};
    `;

    const setActive = (active) => {
      btn.style.background = active ? color + '18' : 'transparent';
      btn.style.color = active ? color : '#888';
      btn.style.borderColor = active ? color : '#444';
      btn.dataset.active = active ? '1' : '0';
    };

    btn.addEventListener('click', () => {
      const c = window._activeStreamChart || chart;
      if (!c) {
        setActive(btn.dataset.active !== '1');
        return;
      }
      if (c._sidewaysMode) {
        setStreamChartSidewaysMode(c, true, key);
        return;
      }
      const dsIndex = c.data.datasets.findIndex(ds => ds._metricKey === key);
      if (dsIndex === -1) {
        setActive(btn.dataset.active !== '1');
        return;
      }
      const nextVisible = !c.isDatasetVisible(dsIndex);
      c.setDatasetVisibility(dsIndex, nextVisible);
      _updateStreamZoomYRanges(c);
      c.update('none');
      setActive(nextVisible);
    });

    container.appendChild(btn);
  });
}


/**
 * Switch stream chart x-axis between distance and time.
 * @param {'distance'|'time'} mode
 */
function setXAxis(mode) {
  // Always update button visual state first — regardless of chart availability.
  const btnDist = document.getElementById('xaxis-distance');
  const btnTime = document.getElementById('xaxis-time');
  if (btnDist && btnTime) {
    btnDist.classList.toggle('active', mode === 'distance');
    btnTime.classList.toggle('active', mode === 'time');
  }

  const chart = window._activeStreamChart;
  if (!chart) return;

  if (chart._sidewaysMode) {
    setStreamChartSidewaysMode(chart, true);
    return;
  }

  const labels = mode === 'distance' ? chart._distLabels : chart._timeLabels;
  if (!labels) return;

  _clearStreamZoom(chart, false);
  chart.data.labels = labels;

  // Swap each dataset's data array to match the new axis mode so the trace
  // shape actually changes (distance mode compresses fast sections).
  for (const ds of chart.data.datasets) {
    if (mode === 'distance' && ds._distData) {
      ds.data = ds._distData;
    } else if (mode === 'time' && ds._timeData) {
      ds.data = ds._timeData;
    }
  }

  chart.update();
  _syncStreamMobileScrubber(chart, 0);
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

  const DAY_SIZE = 14;
  const DAY_GAP = 2;
  const CELL = DAY_SIZE + DAY_GAP;
  const LABEL_H = 20;
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

  container.style.minWidth = (svgW + DOW_LABEL_W) + 'px';
  container.innerHTML = svg;

  // Scroll wrapper to show most-recent (rightmost) end
  requestAnimationFrame(() => {
    const scrollEl = container.closest('.heatmap-scroll');
    if (scrollEl) scrollEl.scrollLeft = scrollEl.scrollWidth;
  });

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
      maintainAspectRatio: false,
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
      maintainAspectRatio: false,
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
      maintainAspectRatio: false,
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
      maintainAspectRatio: false,
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
