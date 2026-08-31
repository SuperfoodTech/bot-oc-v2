from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STYLES = (PROJECT_ROOT / "src/backend/static/css/styles.css").read_text()
MITRA_TEMPLATE = (PROJECT_ROOT / "src/backend/templates/user_dashboard.html").read_text()


def test_schedule_rows_can_wrap_without_overflowing_their_panel():
    assert ".outlet-schedule-row span" in STYLES
    assert ".admin-schedule-row span" in STYLES
    assert STYLES.count("overflow-wrap: anywhere;") >= 2
    assert STYLES.count("min-width: 0;") >= 2


def test_schedule_day_column_keeps_a_stable_width():
    assert "flex: 0 0 70px;" in STYLES
    assert "flex-basis: 74px;" in STYLES


def test_mitra_recent_activity_uses_a_two_row_grid_without_a_fake_chevron():
    assert ".mobile-wrapper.is-dashboard-view .history-item {" in STYLES
    assert "grid-template-columns: auto minmax(0, 1fr);" in STYLES
    assert '"role body"' in STYLES
    assert '". time"' in STYLES
    assert ".mobile-wrapper.is-dashboard-view .history-item > .history-time" in STYLES
    assert ".mobile-wrapper.is-dashboard-view .history-item > .mitra-history-body" in STYLES
    assert ".history-chevron" not in STYLES
    assert "grid-template-columns: 58px 82px minmax(0, 1fr) 18px;" not in STYLES


def test_mitra_dashboard_prioritizes_outlet_list_over_account_summary():
    assert 'class="section-heading mitra-section-heading"' in MITRA_TEMPLATE
    assert 'id="outletsList"' in MITRA_TEMPLATE
    assert 'class="card-box mitra-account-summary"' in MITRA_TEMPLATE
    assert MITRA_TEMPLATE.index('id="outletsList"') < MITRA_TEMPLATE.index('class="card-box mitra-account-summary"')
    assert 'onclick="scrollToAccountNotice()"' not in MITRA_TEMPLATE
    assert 'aria-label="Buka otomatis untuk ${storeName}"' in MITRA_TEMPLATE


def test_user_schedule_preview_uses_shopee_weekday_contract():
    assert "1: 'Minggu'" in MITRA_TEMPLATE
    assert "7: 'Sabtu'" in MITRA_TEMPLATE
    assert "shopeeDayNames[Number(day.weekday)]" in MITRA_TEMPLATE


def test_admin_today_operating_hours_stacks_multi_slots_without_orphaned_timezone():
    template = (PROJECT_ROOT / "src/backend/templates/admin_dashboard.html").read_text()

    assert "function renderTodayOperatingHoursMarkup" in template
    assert "<span class=\"operating-meta\"><span class=\"operating-day\">${safeDayLabel}</span><span class=\"operating-timezone\">${escapeHtml(timezoneLabel)}</span></span>" in template
    assert "${ranges.join(' · ')} ${timezoneLabel}" not in template


def test_admin_today_operating_hours_has_meta_row_styles():
    assert ".today-operating-hours .operating-meta" in STYLES
    assert ".today-operating-hours .operating-timezone" in STYLES


def test_vb_dashboard_uses_schedule_drawer_without_detail_panel_markup():
    tab_template = (PROJECT_ROOT / "src/backend/templates/admin_tab_vb.html").read_text()
    dashboard_template = (PROJECT_ROOT / "src/backend/templates/admin_dashboard.html").read_text()

    assert 'id="vbScheduleDrawer"' in tab_template
    assert 'id="vbScheduleDrawerBackdrop"' in tab_template
    assert 'id="vbResultsSummary"' in tab_template
    assert 'id="vbFilterDisclosure"' in tab_template
    assert 'id="vbQuickActions"' in tab_template
    assert 'id="vbBulkToolbar"' in tab_template
    assert 'id="vbInlineSearchInput"' in tab_template
    assert 'class="vb-empty-state"' in dashboard_template
    assert 'aria-label="${isExpanded ? \'Sembunyikan\' : \'Tampilkan\'} Store ID grup' in dashboard_template
    assert "function runVbBulkOpen()" in dashboard_template
    assert "function openVbBulkPauseModal()" in dashboard_template
    assert "class=\"vb-brand-select\"" in dashboard_template
    assert '<span>Live Buka</span>' in dashboard_template
    assert '<span>Perlu cek</span>' in dashboard_template
    assert '<span>Live Tutup</span>' in dashboard_template
    assert 'class="vb-store-status"' in dashboard_template
    assert "openVbScheduleDrawer(" in dashboard_template
    assert "resetVbFilters()" in tab_template
    assert "shopee_regular_hours: outlet?.shopee_regular_hours || {}" in dashboard_template
    assert "os.shopee_regular_hours, os.timezone" in (PROJECT_ROOT / "src/backend/vb.py").read_text()


def test_vb_dashboard_styles_define_scrollable_page_and_right_drawer():
    assert ".vb-page-shell" in STYLES
    assert ".vb-stat-grid" in STYLES
    assert ".vb-schedule-drawer" in STYLES
    assert ".vb-store-table-head" in STYLES


def test_admin_agency_has_bulk_actions_below_filter():
    tab_template = (PROJECT_ROOT / "src/backend/templates/admin_tab_operasional.html").read_text()
    dashboard_template = (PROJECT_ROOT / "src/backend/templates/admin_dashboard.html").read_text()

    assert 'id="adminQuickActions"' in tab_template
    assert 'id="adminBulkToolbar"' in tab_template
    assert 'id="adminBulkOpenButton"' in tab_template
    assert 'id="adminBulkPauseButton"' in tab_template
    assert "function toggleAdminBulkSelectionMode()" in dashboard_template
    assert "function openAdminBulkPauseModal()" in dashboard_template
