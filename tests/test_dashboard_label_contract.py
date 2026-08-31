from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADMIN_TEMPLATE = (PROJECT_ROOT / "src/backend/templates/admin_dashboard.html").read_text()
MITRA_TEMPLATE = (PROJECT_ROOT / "src/backend/templates/user_dashboard.html").read_text()


def test_admin_and_mitra_expose_the_same_runtime_status_concepts():
    admin_labels = [
        "Dinonaktifkan admin",
        "Menunggu bot menutup",
        "Menunggu bot membuka",
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


def test_admin_fallback_handles_schedule_states_with_mitra_labels():
    schedule_branch = "if (stateContext.botPhase === 'WAITING_SCHEDULE')"
    unavailable_branch = "if (stateContext.botPhase === 'SCHEDULE_UNAVAILABLE')"
    admin_start = ADMIN_TEMPLATE.index("function getAdminStatusPresentation")
    admin_end = ADMIN_TEMPLATE.index("function getAdminStatusSubtext", admin_start)
    admin_presentation = ADMIN_TEMPLATE[admin_start:admin_end]

    assert schedule_branch in admin_presentation
    assert unavailable_branch in admin_presentation
    assert "Menunggu jadwal operasional" in admin_presentation
    assert "Status sedang dicek bot" in admin_presentation


def test_admin_toggle_uses_effective_display_state_outside_schedule():
    assert "typeof store?.display_toggle_on === 'boolean'" in ADMIN_TEMPLATE
    assert "if (isAdminToggleDisabled(store, stateContext)) return false;" in ADMIN_TEMPLATE
