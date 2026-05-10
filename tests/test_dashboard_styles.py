from pathlib import Path


def test_mobile_table_styles_include_touch_scroll_polish():
    css = Path("fitops/dashboard/static/css/main.css").read_text()

    assert ".table-wrap::-webkit-scrollbar" in css
    assert "-webkit-overflow-scrolling: touch;" in css
    assert "overscroll-behavior-x: contain;" in css
    assert "scrollbar-gutter: stable both-edges;" in css
    assert "touch-action: pan-x;" in css
    assert ".data-table {\n    width: max-content;" in css
    assert "min-width: 100%;" in css


def test_mobile_chart_fullscreen_uses_landscape_lock():
    base_template = Path("fitops/dashboard/templates/base.html").read_text()
    css = Path("fitops/dashboard/static/css/main.css").read_text()
    activity_detail = Path(
        "fitops/dashboard/templates/activities/detail.html"
    ).read_text()

    assert "orientation.lock('landscape')" in base_template
    assert "orientation.unlock()" in base_template
    assert "webkitRequestFullscreen" in base_template
    assert "webkitfullscreenchange" in base_template
    assert "_syncChartLandscapeFallback(el);" in base_template
    assert "setStreamChartSidewaysMode(chart, true);" in base_template
    assert "setStreamChartSidewaysMode(chart, false);" in base_template
    assert "window.addEventListener('orientationchange'" in base_template
    assert "max-width: 767px" in base_template
    assert "mobile-chart-landscape" in base_template
    assert "(pointer: coarse) and (max-height: 767px)" in css
    assert "data-fs-target" in activity_detail
    assert ".analysis-chart:fullscreen" in css
    assert ".analysis-chart:-webkit-full-screen" in css
    assert "min-height: calc(100vh - 3.5rem);" in css
    assert "left: 0;" in css
    assert "width: 100vw;" in css
    assert "height: 100vh;" in css
    assert "right: 0.75rem;" in css
    assert "transform: rotate(90deg);" in css
    assert "margin-right: 104px;" in css


def test_stream_chart_crosshair_avoids_private_tooltip_state():
    charts_js = Path("fitops/dashboard/static/js/charts.js").read_text()

    assert "ch.tooltip._active" not in charts_js
    assert "ch.getActiveElements()" in charts_js
    assert "if (!ch.chartArea || !ch.scales || !ch.scales.x) return;" in charts_js


def test_chart_static_asset_is_cache_busted():
    base_template = Path("fitops/dashboard/templates/base.html").read_text()

    assert 'src="/static/js/charts.js?v=' in base_template


def test_stream_chart_sideways_mode_swaps_axes_for_mobile_fullscreen():
    charts_js = Path("fitops/dashboard/static/js/charts.js").read_text()

    assert (
        "function setStreamChartSidewaysMode(chart, enabled, preferredKey = null)"
        in charts_js
    )
    assert "chart._sidewaysMode = true;" in charts_js
    assert "chart._sidewaysVisibleKeys = new Set(" in charts_js
    assert "points.push({ x: Number(value), y: labels[i] });" in charts_js
    assert "position: axisIndex % 2 === 0 ? 'top' : 'bottom'" in charts_js
    assert "type: 'category'" in charts_js
    assert "setStreamChartSidewaysMode(c, true, key);" in charts_js
    assert "maxTicksLimit: 6" in charts_js
    assert "minRotation: 90" in charts_js
    assert "maxRotation: 90" in charts_js
    assert "xAxisID: `x${source.yAxisID}`" in charts_js
