from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STYLES = (PROJECT_ROOT / "src/backend/static/css/styles.css").read_text()


def test_schedule_rows_can_wrap_without_overflowing_their_panel():
    assert ".outlet-schedule-row span" in STYLES
    assert ".admin-schedule-row span" in STYLES
    assert STYLES.count("overflow-wrap: anywhere;") >= 2
    assert STYLES.count("min-width: 0;") >= 2


def test_schedule_day_column_keeps_a_stable_width():
    assert "flex: 0 0 70px;" in STYLES
    assert "flex-basis: 74px;" in STYLES


def test_user_schedule_preview_uses_shopee_weekday_contract():
    template = (PROJECT_ROOT / "src/backend/templates/user_dashboard.html").read_text()
    assert "1: 'Minggu'" in template
    assert "7: 'Sabtu'" in template
    assert "shopeeDayNames[Number(day.weekday)]" in template
