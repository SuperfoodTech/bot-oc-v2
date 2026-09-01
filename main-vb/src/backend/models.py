"""
models.py
=========
Pydantic data schemas for Admin & User Link API requests and responses.
"""

from typing import Optional, List, Dict
from pydantic import BaseModel, Field


# ── GENERAL & LEGACY MODELS ───────────────────────────────────────────────────

class ToggleRequest(BaseModel):
    store_id: str = Field(..., description="Target Shopee Store ID")
    status: str = Field(..., description="'ON' or 'OFF'")
    pause_duration_minutes: Optional[int] = Field(default=1440, description="Pause duration in minutes if status is OFF")


class StoreStatusResponse(BaseModel):
    store_id: str
    store_name: str
    merchant_name: str
    account_username: str
    nama_pemilik: Optional[str] = ""
    paket: Optional[str] = "3 Bulan"
    tanggal_mulai_layanan: Optional[str] = ""
    tanggal_berakhir_layanan: Optional[str] = ""
    vercel_link: Optional[str] = ""
    vercel_password: Optional[str] = ""
    vercel_status: str
    shopee_status: str
    shopee_regular_hours: Dict = Field(default_factory=dict)
    subscription_status: str
    is_suspended: bool
    alasan_penangguhan: Optional[str] = ""
    pause_until: Optional[str] = None
    timezone: Optional[str] = "Asia/Jakarta"
    last_synced_at: Optional[str] = None
    desired_state: Optional[str] = None
    live_state: Optional[str] = None
    bot_phase: Optional[str] = None
    schedule_available: Optional[bool] = None
    schedule_fetch_status: Optional[str] = None
    schedule_fetch_attempted_at: Optional[str] = None
    schedule_fetch_succeeded_at: Optional[str] = None
    schedule_fetch_error: Optional[str] = None
    within_operating_schedule: Optional[bool] = None
    display_toggle_on: Optional[bool] = None
    display_toggle_disabled: Optional[bool] = None
    display_toggle_reason: Optional[str] = None
    display_status_bucket: Optional[str] = None
    display_status_label: Optional[str] = None
    display_status_tone: Optional[str] = None
    display_note: Optional[str] = None


class SyncResponse(BaseModel):
    success: bool
    total_stores_processed: int
    actions_taken: List[Dict[str, str]]
    message: str


class AutomationLogResponse(BaseModel):
    id: int
    timestamp: str
    store_id: str
    store_name: str
    action: str
    target_state: str
    reason: str


# ── ADMIN DASHBOARD MODELS ────────────────────────────────────────────────────

class AdminGenerateLinkRequest(BaseModel):
    nama_pemilik: str = Field(..., description="Nama pemilik/mitra")
    passcode: Optional[str] = Field(default="Master@00@", description="Passcode untuk autentikasi user link")


class AdminCreateOutletRequest(BaseModel):
    nama_pemilik: str = Field(..., min_length=1)
    nama_portal: str = Field(..., min_length=1)
    # Merchant ID eksternal tidak lagi diinput saat onboarding.
    # Nilai lama tetap kompatibel dan akan disimpan kosong bila tidak tersedia.
    merchant_id: str = ""
    store_id: str = Field(..., min_length=1)
    nama_panjang_outlet: str = Field(..., min_length=1)
    ownership_type: str = ""
    phone: str = ""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    dashboard_password: str = Field(..., min_length=8)
    paket: str = Field(default="3_MONTHS")
    tanggal_mulai_layanan: str = Field(..., description="YYYY-MM-DD")
    tanggal_berakhir_layanan: str = Field(..., description="YYYY-MM-DD")
    operating_hours: Dict[str, str] = Field(default_factory=dict)
    special_hours: str = ""


class AdminSuspendRequest(BaseModel):
    store_id: str = Field(..., description="Target Store ID")
    penangguhan: str = Field(..., description="'Ya' atau 'Tidak'")
    alasan_penangguhan: Optional[str] = Field(default="", description="Alasan penangguhan jika Ya")


class AdminRenewRequest(BaseModel):
    store_id: str = Field(..., description="Target Store ID")
    new_expiry_date: str = Field(..., description="Tanggal berakhir layanan baru (YYYY-MM-DD)")


# ── USER LINK / DASHBOARD MODELS ──────────────────────────────────────────────

class UserLoginRequest(BaseModel):
    passcode: str = Field(..., description="Vercel passcode/kata sandi user")


class UserPauseRequest(BaseModel):
    store_id: str = Field(..., description="Target Store ID")
    duration_type: str = Field(..., description="'30_min', '60_min', 'rest_of_day', or 'custom'")
    custom_minutes: Optional[int] = Field(default=120, description="Custom pause duration in minutes if duration_type is custom")
