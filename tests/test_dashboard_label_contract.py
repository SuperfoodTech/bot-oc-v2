from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADMIN_TEMPLATE = (PROJECT_ROOT / "src/backend/templates/admin_dashboard.html").read_text()
MITRA_TEMPLATE = (PROJECT_ROOT / "src/backend/templates/user_dashboard.html").read_text()


def test_admin_and_mitra_expose_the_same_runtime_status_concepts():
    admin_labels = [
        "Dinonaktifkan admin",
        "Menunggu bot menutup",
        "Menunggu bot membuka",
        "Menunggu fetch jadwal",
        "Gagal fetch jadwal, bot akan coba lagi",
        "Jadwal Shopee belum diatur",
        "Menunggu jadwal operasional",
        "Otomatisasi nonaktif",
        "Tutup sementara",
        "Sedang buka",
        "Status sedang dicek bot",
    ]
    mitra_labels = [
        "Sedang Tutup • Dinonaktifkan admin",
        "Sedang Buka • Menunggu bot menutup",
        "Sedang Tutup • Menunggu bot membuka",
        "Menunggu fetch jadwal",
        "Gagal fetch jadwal, bot akan coba lagi",
        "Jadwal Shopee belum diatur",
        "Sedang Tutup • Di luar jadwal",
        "Sedang Tutup • Otomatisasi nonaktif",
        "Tutup Sementara",
        "Sedang Buka",
        "Status sedang dicek bot",
    ]

    for label in admin_labels:
        assert label in ADMIN_TEMPLATE
    for label in mitra_labels:
        assert label in MITRA_TEMPLATE


def test_admin_fallback_handles_split_schedule_fetch_states():
    schedule_branch = "if (stateContext.botPhase === 'WAITING_SCHEDULE')"
    not_fetched_branch = "if (stateContext.botPhase === 'NOT_FETCHED_YET')"
    retry_branch = "if (stateContext.botPhase === 'FETCH_RETRYING')"
    empty_branch = "if (stateContext.botPhase === 'FETCHED_EMPTY')"
    admin_start = ADMIN_TEMPLATE.index("function getAdminStatusPresentation")
    admin_end = ADMIN_TEMPLATE.index("function getAdminStatusSubtext", admin_start)
    admin_presentation = ADMIN_TEMPLATE[admin_start:admin_end]

    assert schedule_branch in admin_presentation
    assert not_fetched_branch in admin_presentation
    assert retry_branch in admin_presentation
    assert empty_branch in admin_presentation
    assert "Menunggu jadwal operasional" in admin_presentation
    assert "Menunggu fetch jadwal" in admin_presentation
    assert "Gagal fetch jadwal, bot akan coba lagi" in admin_presentation
    assert "Jadwal Shopee belum diatur" in admin_presentation


def test_admin_toggle_uses_effective_display_state_outside_schedule():
    assert "typeof store?.display_toggle_on === 'boolean'" in ADMIN_TEMPLATE
    assert "if (stateContext.botPhase === 'NOT_FETCHED_YET' || stateContext.botPhase === 'FETCH_RETRYING' || stateContext.botPhase === 'FETCHED_EMPTY') return stateContext.desiredState === 'OPEN';" in ADMIN_TEMPLATE


def test_admin_rest_of_day_information_is_dynamic_for_agency_and_vb():
    assert "Sesi pertama besok" not in ADMIN_TEMPLATE
    assert 'id="adminRestOfDayMeta"' in ADMIN_TEMPLATE
    assert 'id="vbRestOfDayMeta"' in ADMIN_TEMPLATE
    assert "function updateAdminRestOfDayMeta()" in ADMIN_TEMPLATE
    assert "function updateVbRestOfDayMeta()" in ADMIN_TEMPLATE
    assert "Preview outlet pertama: buka kembali" in ADMIN_TEMPLATE
    assert "new Date(Date.now() + 24 * 60 * 60 * 1000)" not in ADMIN_TEMPLATE


def test_mitra_rest_of_day_copy_is_dynamic_and_not_tomorrow_first_session():
    assert "sesi pertama besok" not in MITRA_TEMPLATE.casefold()
    assert 'id="pauseRestOfDayMeta"' in MITRA_TEMPLATE
    assert "function buildPauseSuccessMessage" in MITRA_TEMPLATE
    assert "function updatePauseRestOfDayMeta()" in MITRA_TEMPLATE
    assert "Permintaan tutup sementara Sepanjang Hari tersimpan." in MITRA_TEMPLATE
    assert "Buka kembali pada sesi operasional outlet berikutnya." in MITRA_TEMPLATE


def test_mitra_login_caption_is_single_line_and_nowrap_contract():
    css_content = (PROJECT_ROOT / "src/backend/static/css/styles.css").read_text()
    assert '<p class="card-subtitle">Gunakan kata sandi dari Admin untuk mengakses Bot Anda.</p>' in MITRA_TEMPLATE
    assert "#loginSection .mitra-login-copy .card-subtitle" in css_content
    assert "white-space: nowrap;" in css_content
    assert "max-width: 340px;" not in css_content
    assert "max-width: 304px;" not in css_content


def test_mitra_account_summary_name_and_outlet_capitalization_contract():
    mitra_html = (PROJECT_ROOT / "src/backend/templates/user_dashboard.html").read_text()
    assert "document.getElementById('mitraName').textContent = `Mitra ${data.nama_pemilik}`;" not in mitra_html
    assert "document.getElementById('mitraName').textContent = data.nama_pemilik || '';" in mitra_html
    assert "return `${safeTotal} Outlet`;" in mitra_html
    assert "0 Outlet" in mitra_html


def test_history_logs_ux_writing_contract():
    mitra_html = (PROJECT_ROOT / "src/backend/templates/user_dashboard.html").read_text()
    admin_html = (PROJECT_ROOT / "src/backend/templates/admin_dashboard.html").read_text()

    expected_phrases = [
        "Outlet dibuka oleh Admin",
        "Outlet dibuka oleh Merchant",
        "Bot berhasil membuka outlet",
        "Outlet ditutup oleh Admin",
        "Outlet ditutup oleh Merchant",
        "Bot berhasil menutup outlet",
        "Store ID ${escapeHtml(l.store_id)}",
    ]

    for phrase in expected_phrases:
        assert phrase in mitra_html, f"Phrase '{phrase}' missing in user_dashboard.html"
        assert phrase in admin_html, f"Phrase '{phrase}' missing in admin_dashboard.html"



