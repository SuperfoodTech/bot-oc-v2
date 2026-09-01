from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_BOT_WORKER = (PROJECT_ROOT / "main-bot/src/worker.py").read_text()
MAIN_VB_WORKER = (PROJECT_ROOT / "main-vb/src/worker.py").read_text()
BACKEND_WORKER = (PROJECT_ROOT / "src/backend/worker.py").read_text()
BACKEND_VB_WORKER = (PROJECT_ROOT / "main-vb/src/backend/worker.py").read_text()


REQUIRED_FRAGMENTS = [
    "last_known_regular_hours = (",
    "last_known_schedule_available = any(last_known_regular_hours.values())",
    "current_schedule_fetch_status = str(getattr(outlet, \"schedule_fetch_status\", \"\") or \"\").strip().upper()",
    "shopee_hours = store_status.get_regular_hours(driver, store_id=outlet.store_id)",
    "_mark_schedule_fetch_empty(outlet)",
    "outlet.schedule_fetch_status = \"READY\"",
    "db.update_shopee_regular_hours(outlet.store_id, normalized_hours)",
    "_mark_schedule_fetch_retry(outlet, \"Shopee tidak mengembalikan data jadwal.\")",
    "_mark_schedule_fetch_retry(outlet, \"Response jadwal Shopee tidak valid.\")",
    "except store_status.StoreIdentityMismatch as identity_err:",
    "current_schedule_fetch_status != \"FETCHED_EMPTY\"",
    "Store identity mismatch saat fetch jadwal: {identity_err}",
    "_mark_schedule_fetch_retry(outlet, str(hours_err))",
    "_mark_schedule_fetch_retry(outlet, \"Sesi browser belum siap untuk fetch jadwal.\")",
    "if not schedule_identity_valid or not live_identity_valid:",
    "decision = evaluate_outlet_status(",
    "require_regular_schedule=True,",
]


def assert_schedule_fetch_contract(content: str) -> None:
    for fragment in REQUIRED_FRAGMENTS:
        assert fragment in content
    assert "WAITING_SCHEDULE_FETCH" not in content
    assert "schedule_fetch_valid" not in content
    assert content.index("shopee_hours = store_status.get_regular_hours(driver, store_id=outlet.store_id)") < content.index("decision = evaluate_outlet_status(")


def test_main_and_vb_daemons_fetch_schedule_before_decision_with_same_guardrails():
    for content in (MAIN_BOT_WORKER, MAIN_VB_WORKER):
        assert_schedule_fetch_contract(content)


def test_backend_fallback_workers_match_schedule_fetch_guardrails_too():
    for content in (BACKEND_WORKER, BACKEND_VB_WORKER):
        assert_schedule_fetch_contract(content)
