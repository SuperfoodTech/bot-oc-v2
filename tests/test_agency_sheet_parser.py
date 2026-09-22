import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core import sheets


class _DummyResponse:
    def __init__(self, text: str):
        self.content = text.encode("utf-8")

    def raise_for_status(self):
        return None


def test_fetch_merchant_outlets_maps_nama_listing(monkeypatch: pytest.MonkeyPatch):
    csv_text = """Nama Pemilik,Nomor HP,Status Bot,Paket,Tanggal Mulai Layanan,Tanggal Berakhir Layanan,Akses Username,Akses Kata Sandi,Nama Portal,Store ID,Nama Listing,Vercel Kata Sandi
Amir,6281111111111,Aktif,3 Bulan,2026-09-01,2026-12-01,auto7313,Auto@7313,KEBAB BABA AMIR_,1176061,Kebab Baba Amir - Darmo,2026
"""

    monkeypatch.setattr(sheets.requests, "get", lambda *args, **kwargs: _DummyResponse(csv_text))

    rows = sheets.fetch_merchant_outlets("https://example.com/fake.csv")

    assert len(rows) == 1
    assert rows[0].store_id == "1176061"
    assert rows[0].nama_portal == "KEBAB BABA AMIR_"
    assert rows[0].nama_panjang_outlet == "Kebab Baba Amir - Darmo"
