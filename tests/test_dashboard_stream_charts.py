import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for JS chart tests"
)
def test_mobile_stream_scrubber_is_bounded_to_zoom_range():
    script = r"""
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const range = { min: '0', max: '0', value: '0' };
const wrap = { hidden: false };
const label = { textContent: '' };
const reset = { hidden: true };
const elements = {
  'stream-mobile-scrubber': wrap,
  'stream-scrub-range': range,
  'stream-scrub-label': label,
  'stream-zoom-reset': reset,
};
const context = {
  console,
  setTimeout,
  window: { matchMedia: () => ({ matches: false }) },
  document: { getElementById: (id) => elements[id] || null },
  Chart: Object.assign(function Chart() {}, {
    defaults: { font: {} },
    getChart: () => null,
  }),
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('fitops/dashboard/static/js/charts.js', 'utf8'), context);

const labels = Array.from({ length: 101 }, (_, i) => `T${i}`);
const chart = {
  _isStreamChart: true,
  data: {
    labels,
    datasets: [{ data: labels.map((_, i) => i), yAxisID: 'y' }],
  },
  options: { scales: { x: {}, y: {} } },
  isDatasetVisible: () => true,
  update: () => {},
};

context._syncStreamMobileScrubber(chart, 0);
assert.equal(range.min, '0');
assert.equal(range.max, '100');
assert.equal(range.value, '0');

chart._streamZoomRange = [20, 50];
range.value = '75';
context._syncStreamMobileScrubber(chart);
assert.equal(range.min, '20');
assert.equal(range.max, '50');
assert.equal(range.value, '50');
assert.equal(label.textContent, 'T50');

context._syncStreamMobileScrubber(chart, 10);
assert.equal(range.value, '20');
assert.equal(label.textContent, 'T20');

context._syncStreamMobileScrubber(chart, 35);
assert.equal(range.value, '35');
assert.equal(label.textContent, 'T35');
"""
    subprocess.run(["node", "-e", script], cwd=REPO_ROOT, check=True)


@pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for JS chart tests"
)
def test_stream_zoom_application_updates_mobile_scrubber_bounds():
    script = r"""
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const range = { min: '0', max: '100', value: '90' };
const wrap = { hidden: false };
const label = { textContent: '' };
const reset = { hidden: true };
const elements = {
  'stream-mobile-scrubber': wrap,
  'stream-scrub-range': range,
  'stream-scrub-label': label,
  'stream-zoom-reset': reset,
};
const context = {
  console,
  setTimeout,
  window: { matchMedia: () => ({ matches: false }) },
  document: { getElementById: (id) => elements[id] || null },
  Chart: Object.assign(function Chart() {}, {
    defaults: { font: {} },
    getChart: () => null,
  }),
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('fitops/dashboard/static/js/charts.js', 'utf8'), context);

const labels = Array.from({ length: 101 }, (_, i) => `T${i}`);
let updated = false;
const chart = {
  _isStreamChart: true,
  data: {
    labels,
    datasets: [{ data: labels.map((_, i) => i), yAxisID: 'y' }],
  },
  options: { scales: { x: {}, y: {} } },
  isDatasetVisible: () => true,
  update: () => { updated = true; },
};

context._applyStreamZoomRange(chart, 60, 30);
assert.deepEqual(chart._streamZoomRange, [30, 60]);
assert.equal(chart.options.scales.x.min, 30);
assert.equal(chart.options.scales.x.max, 60);
assert.equal(range.min, '30');
assert.equal(range.max, '60');
assert.equal(range.value, '60');
assert.equal(label.textContent, 'T60');
assert.equal(reset.hidden, false);
assert.equal(updated, true);
"""
    subprocess.run(["node", "-e", script], cwd=REPO_ROOT, check=True)


@pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for JS chart tests"
)
def test_stream_chart_pace_axis_includes_true_pace_series():
    script = r"""
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const elements = {
  'stream-chart': { id: 'stream-chart' },
  'stream-mobile-scrubber': { hidden: false },
  'stream-scrub-range': {
    min: '0',
    max: '0',
    value: '0',
    addEventListener: () => {},
  },
  'stream-scrub-label': { textContent: '' },
  'stream-zoom-reset': { hidden: true },
};
function Chart(ctx, config) {
  this.ctx = ctx;
  this.data = config.data;
  this.options = config.options;
  this.plugins = config.plugins;
  this.update = () => {};
  this.destroy = () => {};
  this.isDatasetVisible = () => true;
  return this;
}
Chart.defaults = { font: {} };
Chart.getChart = () => null;

const context = {
  console,
  setTimeout,
  window: { matchMedia: () => ({ matches: false }) },
  document: { getElementById: (id) => elements[id] || null },
  Chart,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('fitops/dashboard/static/js/charts.js', 'utf8'), context);

const chart = context.renderStreamChart('stream-chart', {
  time: Array.from({ length: 20 }, (_, i) => i),
  velocity_smooth: Array.from({ length: 20 }, () => 1000 / 300),
  true_pace: Array.from({ length: 20 }, (_, i) => i < 10 ? 300 : 900),
}, 'Run', {});

assert(chart.data.datasets.some((ds) => ds.label === 'True Pace'));
assert(chart.options.scales.yPace.max > 900);
"""
    subprocess.run(["node", "-e", script], cwd=REPO_ROOT, check=True)
