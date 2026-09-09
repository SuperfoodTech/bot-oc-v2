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


def test_mitra_recent_activity_has_scrollable_card_container():
    assert ".mobile-wrapper.is-dashboard-view .history-list {" in STYLES
    assert "max-height: 380px;" in STYLES
    assert "overflow-y: auto;" in STYLES
    assert "overscroll-behavior: contain;" in STYLES
    assert "logs.slice(0, 5)" not in MITRA_TEMPLATE
    assert "logs.forEach(" in MITRA_TEMPLATE


def test_mitra_dashboard_keeps_account_summary_above_outlet_list():
    assert 'class="section-heading mitra-section-heading"' in MITRA_TEMPLATE
    assert 'id="outletsList"' in MITRA_TEMPLATE
    assert 'class="card-box mitra-account-summary"' in MITRA_TEMPLATE
    assert MITRA_TEMPLATE.index('class="card-box mitra-account-summary"') < MITRA_TEMPLATE.index('class="section-heading mitra-section-heading"')
    assert MITRA_TEMPLATE.index('class="card-box mitra-account-summary"') < MITRA_TEMPLATE.index('id="outletsList"')
    assert 'onclick="scrollToAccountNotice()"' not in MITRA_TEMPLATE
    assert 'aria-label="Buka otomatis untuk ${storeName}"' in MITRA_TEMPLATE
    assert 'id="accountPasscode"' in MITRA_TEMPLATE
    assert 'Kata Sandi:' in MITRA_TEMPLATE
    assert 'id="accountOutletCount"' in MITRA_TEMPLATE
    assert '${automationDetailMarkup}' not in MITRA_TEMPLATE
    assert '.mobile-wrapper.is-dashboard-view .mitra-account-summary #subBadge' in STYLES
    assert 'background: #16a34a;' in STYLES


def test_mitra_dashboard_3_state_toggle_contract():
    assert "function getMitraToggleState(outlet, stateContext" in MITRA_TEMPLATE
    assert "state-${toggleState}" in MITRA_TEMPLATE
    assert ".mobile-wrapper.is-dashboard-view .switch-toggle.state-open" in STYLES
    assert ".mobile-wrapper.is-dashboard-view .switch-toggle.state-paused" in STYLES
    assert ".mobile-wrapper.is-dashboard-view .switch-toggle.state-closed" in STYLES
    assert "<strong>Buka otomatis</strong>" not in MITRA_TEMPLATE
    assert "mitra-outlet-toggle-row" not in MITRA_TEMPLATE


def test_user_schedule_preview_uses_shopee_weekday_contract():
    assert "1: 'Minggu'" in MITRA_TEMPLATE
    assert "7: 'Sabtu'" in MITRA_TEMPLATE
    assert "shopeeDayNames[Number(day.weekday)]" in MITRA_TEMPLATE
    assert "replace(/:/g, '.')" not in MITRA_TEMPLATE
    assert "replace(/\\./g, ':')" in MITRA_TEMPLATE


def test_admin_today_operating_hours_stacks_multi_slots_without_orphaned_timezone():
    template = (PROJECT_ROOT / "src/backend/templates/admin_dashboard.html").read_text()

    assert "function renderTodayOperatingHoursMarkup" in template
    assert "<span class=\"operating-meta\"><span class=\"operating-timezone\">${escapeHtml(timezoneLabel)}</span></span>" in template
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


def test_admin_outlet_table_uses_global_desktop_scroll_region():
    dashboard_template = (PROJECT_ROOT / "src/backend/templates/admin_dashboard.html").read_text()

    assert ".admin-shell .admin-main > .desktop-wrapper.is-global-scroll-active {" in STYLES
    assert ".admin-shell .admin-main > .desktop-wrapper.is-global-scroll-active #paneOutlets.active .outlet-content-layout {" in STYLES
    assert ".admin-shell .admin-main > .desktop-wrapper.is-global-scroll-active #paneOutlets .table-card.outlet-section {" in STYLES
    assert ".admin-shell .admin-main > .desktop-wrapper.is-global-scroll-active #paneOutlets .table-card.outlet-section .table-scroll {" in STYLES
    assert "overflow-y: visible;" in STYLES
    assert "scrollbar-gutter: stable;" in STYLES
    assert "overscroll-behavior: contain;" in STYLES
    assert "function syncDesktopWrapperScrollState" in dashboard_template
    assert "syncDesktopWrapperScrollState(initialTab);" in dashboard_template
    assert 'class="admin-breadcrumb" hidden' in dashboard_template
    assert "breadcrumbVisible: false" in dashboard_template
    assert ".admin-shell .admin-main #adminTable tbody td:nth-child(1) .admin-table-owner-cell {" in STYLES
    assert "justify-content: center;" in STYLES


def test_admin_filter_dropdown_search_contract():
    dashboard_template = (PROJECT_ROOT / "src/backend/templates/admin_dashboard.html").read_text()

    assert "const SEARCHABLE_IDS = new Set(['ownerFilter', 'outletFilter', 'storeIdFilter'" in dashboard_template
    assert "custom-filter-search-box" in dashboard_template
    assert "custom-filter-search" in dashboard_template
    assert "custom-filter-options-scroll" in dashboard_template
    assert ".custom-filter-search-box {" in STYLES
    assert ".custom-filter-search {" in STYLES
    assert ".custom-filter-options-scroll {" in STYLES
    assert ".custom-filter-empty {" in STYLES


def test_admin_outlet_table_8_columns_and_link_mitra_contract():
    tab_template = (PROJECT_ROOT / "src/backend/templates/admin_tab_operasional.html").read_text()
    dashboard_template = (PROJECT_ROOT / "src/backend/templates/admin_dashboard.html").read_text()

    # Verify table headers in admin_tab_operasional.html
    assert "<th>Owner</th>" in tab_template
    assert "<th>Merchant</th>" in tab_template
    assert "<th>Store ID</th>" in tab_template
    assert "<th>Outlet</th>" in tab_template
    assert "<th>Jam Operasional</th>" in tab_template
    assert "<th>Link</th>" in tab_template
    assert "<th>Link Mitra</th>" in tab_template
    assert "<th>Toggle</th>" in tab_template
    assert "<th>Status</th>" not in tab_template
    assert "<th>Action</th>" not in tab_template
    assert "<th>Periode Layanan</th>" not in tab_template
    assert '<td colspan="8"' in tab_template

    # Verify admin_dashboard.html logic
    assert "function getShopeeFoodStoreUrl(storeId)" in dashboard_template
    assert "function getAdminToggleState(store, stateContext" in dashboard_template
    assert "admin-table-shopeefood-link" in dashboard_template
    assert "admin-table-mitra-link" in dashboard_template
    assert "Lihat di ShopeeFood" in dashboard_template
    assert "Link Mitra" in dashboard_template
    assert "state-${toggleState}" in dashboard_template
    assert '<td colspan="8"' in dashboard_template

    # Verify drawer no longer contains the moved CTA
    assert 'class="btn-primary outlet-detail-mitra-full-btn"' not in dashboard_template

    # Verify toggle column 8 is never hidden with display: none
    assert ".data-table th:nth-child(8),\n  .data-table td:nth-child(8) {\n    display: none;\n  }" not in STYLES

    # Verify 3-state toggle, ShopeeFood link, and Link Mitra styles
    assert ".switch-toggle.admin-table-toggle.state-open" in STYLES
    assert ".switch-toggle.admin-table-toggle.state-paused" in STYLES
    assert ".switch-toggle.admin-table-toggle.state-closed" in STYLES
    assert ".admin-table-shopeefood-link {" in STYLES
    assert ".admin-table-mitra-link {" in STYLES


def test_admin_filter_toolbar_adaptive_layout_contract():
    assert "grid-template-columns: repeat(6, minmax(0, 1fr)) auto;" in STYLES
    assert ".custom-filter-trigger {" in STYLES
    assert "text-overflow: ellipsis;" in STYLES
    assert ".custom-filter {" in STYLES
    assert "gap: 8px;" in STYLES
    assert ".admin-main .outlet-filter-toolbar .reset-filter-button {" in STYLES




