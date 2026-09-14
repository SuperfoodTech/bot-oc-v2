from datetime import datetime
import importlib.util
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_VB_SRC = PROJECT_ROOT / "main-vb" / "src"
sys.path.insert(0, str(MAIN_VB_SRC))


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(module_name, MAIN_VB_SRC / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


worker = _load_module("test_main_vb_worker", "worker.py")
scheduler = _load_module("test_main_vb_scheduler", "scheduler.py")
from core.sheets import MerchantOutlet


WIB = ZoneInfo("Asia/Jakarta")
ALL_DAY_SCHEDULE = {
    day: ["00:00-23:59"]
    for day in ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
}


def outlet(**overrides) -> MerchantOutlet:
    value = MerchantOutlet(
        username="allvbadmin",
        nama_portal="WonderFood",
        store_id="123",
        nama_panjang_outlet="Outlet X",
        status_utama="ON",
        status_aktual="CLOSED",
        regular_hours=ALL_DAY_SCHEDULE,
        shopee_regular_hours=ALL_DAY_SCHEDULE,
        status_langganan="Aktif",
        penangguhan="Tidak",
    )
    for key, item in overrides.items():
        setattr(value, key, item)
    return value


def test_vb_worker_target_group_filter_ignores_trailing_portal_spaces(monkeypatch):
    test_outlet = outlet(nama_portal="WonderFood   ")
    now = datetime(2026, 9, 14, 15, 17, 45, tzinfo=WIB)
    queue = scheduler.build_queue([test_outlet], now)
    selected = scheduler.select_next_group(queue, now)

    assert selected is not None
    assert selected.merchant_key == ("allvbadmin", "WonderFood")

    worker.ACTIVE_SESSIONS.clear()
    monkeypatch.setattr(worker, "ALLOWED_USERNAMES", {"allvbadmin"})
    monkeypatch.setattr(worker.db, "fetch_merchant_outlets_from_db", lambda: [test_outlet])
    monkeypatch.setattr(worker.db, "sync_expired_user_pauses", lambda: None)
    monkeypatch.setattr(worker.db, "record_log", lambda **kwargs: None)
    monkeypatch.setattr(worker.browser, "set_session_file", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker.browser, "get_session", lambda **kwargs: None)

    result = worker.sync_all_stores(
        execute_actions=False,
        default_interval_seconds=30,
        target_groups={selected.merchant_key},
    )

    assert result["total_stores_processed"] == 1
    assert result["processed_merchant_groups"] == [
        {"username": "allvbadmin", "portal_name": "WonderFood"}
    ]
