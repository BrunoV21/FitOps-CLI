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
