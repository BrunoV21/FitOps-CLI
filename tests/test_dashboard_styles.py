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


def test_mobile_sidebar_layers_above_leaflet_maps():
    css = Path("fitops/dashboard/static/css/main.css").read_text()

    assert "z-index: 1100;" in css
    assert "z-index: 1200;" in css
    assert "z-index: 1210;" in css
    assert "body.sidebar-open .sidebar { transform: translateX(0); }" in css


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
    assert "setStreamChartSidewaysMode(chart, false);" in base_template
    assert "setStreamChartSidewaysMode(chart, true);" not in base_template
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
    assert "flex-direction: row;" in css
    assert "overflow-x: auto;" in css
    assert "min-width: max-content;" in css
    assert "width: 100% !important;" in css


def test_stream_chart_crosshair_avoids_private_tooltip_state():
    charts_js = Path("fitops/dashboard/static/js/charts.js").read_text()

    assert "ch.tooltip._active" not in charts_js
    assert "ch.getActiveElements()" in charts_js
    assert "if (!ch.chartArea || !ch.scales || !ch.scales.x) return;" in charts_js


def test_chart_static_asset_is_cache_busted():
    base_template = Path("fitops/dashboard/templates/base.html").read_text()

    assert 'src="/static/js/charts.js?v=' in base_template


def test_stream_chart_sideways_mode_still_supports_manual_metric_toggles():
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


def test_activity_stream_chart_supports_range_zoom():
    charts_js = Path("fitops/dashboard/static/js/charts.js").read_text()
    activity_detail = Path(
        "fitops/dashboard/templates/activities/detail.html"
    ).read_text()
    css = Path("fitops/dashboard/static/css/main.css").read_text()

    assert "const streamRangeZoomPlugin = {" in charts_js
    assert "id: 'streamRangeZoom'" in charts_js
    assert "_applyStreamZoomRange(chart, state.clickStart, idx);" in charts_js
    assert "_applyStreamZoomRange(chart, state.dragStart, end);" in charts_js
    assert "type === 'dblclick'" in charts_js
    assert "_clearStreamZoomSelectionState(state);" in charts_js
    assert "state.clickCurrent = idx;" in charts_js
    assert "_drawStreamZoomSelection(chart, state.clickStart, state.clickCurrent" in charts_js
    assert "_updateStreamZoomYRanges(chart);" in charts_js
    assert "chart.options.scales.x.min = lo;" in charts_js
    assert "chart.options.scales.x.max = hi;" in charts_js
    assert "resetStreamZoom()" in charts_js
    assert "streamRangeZoomPlugin" in charts_js
    assert "'dblclick'" in charts_js
    assert "'mousedown'" in charts_js
    assert "'touchmove'" in charts_js
    assert 'id="stream-zoom-reset"' in activity_detail
    assert "touch-action: none;" in css



def test_dashboard_design_tokens_cover_legacy_template_aliases():
    css = Path("fitops/dashboard/static/css/main.css").read_text()

    for token in [
        "--bg-secondary:",
        "--bg-card:",
        "--bg-panel:",
        "--bg-hover:",
        "--surface-1:",
        "--surface-2:",
        "--surface-3:",
        "--border-color:",
        "--text-secondary:",
        "--accent-green:",
        "--accent-primary-rgb:",
    ]:
        assert token in css

    for selector in [
        ".stats-grid",
        ".stat-card",
        ".stat-value",
        ".stat-label",
        ".panel-meta",
        ".text-muted",
        ".text-dim",
        ".alert-amber",
    ]:
        assert selector in css


def test_mobile_metric_grids_do_not_clip_values():
    css = Path("fitops/dashboard/static/css/main.css").read_text()

    assert (
        ".panel-metric { font-size: 22px; white-space: normal; "
        "overflow: visible; overflow-wrap: anywhere; }"
    ) in css
    assert ".grid-3 { grid-template-columns: 1fr; }" in css
    assert "@media (max-width: 480px)" in css
    assert ".grid-2,\n  .grid-4,\n  .stats-grid" in css


def test_notes_use_shared_button_contract():
    for template_path in [
        "fitops/dashboard/templates/notes/create.html",
        "fitops/dashboard/templates/notes/detail.html",
        "fitops/dashboard/templates/notes/list.html",
    ]:
        template = Path(template_path).read_text()
        assert 'class="btn-primary"' not in template
        assert 'class="btn-secondary"' not in template
        assert 'class="btn-danger"' not in template

    notes_list = Path("fitops/dashboard/templates/notes/list.html").read_text()
    assert 'class="empty-state"' in notes_list


def test_mobile_identity_and_filter_markup_are_clean():
    base_template = Path("fitops/dashboard/templates/base.html").read_text()
    activity_list = Path("fitops/dashboard/templates/activities/list.html").read_text()
    workout_simulate = Path(
        "fitops/dashboard/templates/workouts/simulate.html"
    ).read_text()

    assert "replace('_', ' ') | title" in base_template
    assert "race_sessions" not in Path(
        "fitops/dashboard/templates/race/sessions.html"
    ).read_text()
    assert "race_sessions" not in Path(
        "fitops/dashboard/templates/race/session_create.html"
    ).read_text()
    assert "race_sessions" not in Path(
        "fitops/dashboard/templates/race/session_detail.html"
    ).read_text()
    assert "flex-wrap:wrap;" in activity_list
    assert 'style="flex:1 1 150px;"' in activity_list
    assert '<div id="course-picker" {% if' not in workout_simulate
    assert '<div id="activity-picker" {% if' not in workout_simulate
    assert 'id="course-picker" style="margin-bottom:1rem;{% if' in workout_simulate
    assert 'id="activity-picker" style="margin-bottom:1rem;{% if' in workout_simulate


def test_deep_analysis_chart_supports_click_range_preview_and_double_click_clear():
    deep_analysis_js = Path("fitops/dashboard/static/js/deep-analysis.js").read_text()
    activity_analysis = Path(
        "fitops/dashboard/templates/activities/analysis.html"
    ).read_text()

    assert "clickStartX: null" in deep_analysis_js
    assert "clickCurrentX: null" in deep_analysis_js
    assert "startDragOrPrepareSecondClick" in deep_analysis_js
    assert "updateSelectionPreview" in deep_analysis_js
    assert "_da.rangeStart = _da.clickStartX;" in deep_analysis_js
    assert "_da.rangeEnd = idx;" in deep_analysis_js
    assert "handleClickSelection" in deep_analysis_js
    assert "clearRangeFromDoubleClick" in deep_analysis_js
    assert "canvas.addEventListener('click'" in deep_analysis_js
    assert "canvas.addEventListener('dblclick'" in deep_analysis_js
    assert "daClearRange();" in deep_analysis_js
    assert '/static/js/deep-analysis.js?v=' in activity_analysis


def test_deep_analysis_sidebar_uses_summary_stat_pairs():
    activity_analysis = Path(
        "fitops/dashboard/templates/activities/analysis.html"
    ).read_text()
    css = Path("fitops/dashboard/static/css/main.css").read_text()

    assert "{% for stat in deep_summary_stats %}" in activity_analysis
    assert "{{ stat.label }}" in activity_analysis
    assert "{{ stat.value }}" in activity_analysis
    assert "{{ stat.unit }}" in activity_analysis
    assert "stat.description" in activity_analysis
    assert 'data-tip="{{ stat.description }}"' in activity_analysis
    assert "da-metric-value--compact" in activity_analysis
    assert ".da-metric-value--compact" in css
    assert ".da-metric-label .da-tip" in css
    assert ".da-metric-label .da-tip::after" in css
    assert ".da-metric-cell:nth-child(even) .da-tip::after" in css
    assert "z-index: 2000;" in css
    assert "box-shadow: 0 10px 30px rgba(0,0,0,0.32);" in css
