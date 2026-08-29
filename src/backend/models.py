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
    nama_portal: Optional[str] = ""
    account_username: str
    nama_pemilik: Optional[str] = ""
    paket: Optional[str] = "3 Bulan"
    tanggal_mulai_layanan: Optional[str] = ""
    tanggal_berakhir_layanan: Optional[str] = ""
    vercel_link: Optional[str] = ""
    vercel_password: Optional[str] = ""
    google_email: Optional[str] = ""
    special_hours: Optional[str] = ""
    vercel_status: str
    shopee_status: str
    shopee_regular_hours: Dict = Field(default_factory=dict)
    subscription_status: str
    is_suspended: bool
    alasan_penangguhan: Optional[str] = ""
    pause_until: Optional[str] = None
    last_synced_at: Optional[str] = None
    last_action: Optional[str] = "no change"
    last_toggle_action_raw: Optional[str] = None
    last_toggle_reason: Optional[str] = ""
    last_toggle_at: Optional[str] = None


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
    store_id: str = Field(..., min_length=1)
    nama_panjang_outlet: str = Field(..., min_length=1)
    username: str = "auto7313"
    phone: str = ""
    password: str = "Auto@7313"
    dashboard_password: str = "Master@123"
    paket: str = "3_MONTHS"
    tanggal_mulai_layanan: str = ""
    tanggal_berakhir_layanan: str = ""
    operating_hours: Dict[str, str] = Field(default_factory=dict)
    special_hours: str = ""
    google_email: Optional[str] = Field(default=None, description="Email Google Mitra")


class AdminBotControlRequest(BaseModel):
    action: str = Field(..., description="'start', 'pause', 'sync', 'stop'")


class AdminSuspendRequest(BaseModel):
    store_id: str = Field(..., description="Target Store ID")
    penangguhan: str = Field(..., description="'Ya' atau 'Tidak'")
    alasan_penangguhan: Optional[str] = Field(default="", description="Alasan penangguhan jika Ya")


class AdminRenewRequest(BaseModel):
    store_id: str = Field(..., description="Target Store ID")
    new_expiry_date: str = Field(..., description="Tanggal berakhir layanan baru (YYYY-MM-DD)")


class AdminEditOutletRequest(BaseModel):
    store_id: str = Field(..., description="Target Store ID")
    nama_pemilik: Optional[str] = Field(default=None, description="Nama pemilik/mitra")
    nama_portal: Optional[str] = Field(default=None, description="Nama merchant/portal Shopee")
    nama_panjang_outlet: Optional[str] = Field(default=None, description="Nama outlet")
    paket: Optional[str] = Field(default=None, description="Paket: 3_MONTHS, 6_MONTHS, 12_MONTHS")
    dashboard_password: Optional[str] = Field(default=None, description="Passcode dashboard")
    google_email: Optional[str] = Field(default=None, description="Email Google Mitra")


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AdminAccountUpdateRequest(BaseModel):
    username: Optional[str] = Field(default=None, min_length=1)
    password: Optional[str] = Field(default=None, min_length=1)
    google_email: Optional[str] = Field(default=None, description="Email Google Admin")


class AdminAccountCreateRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    google_email: Optional[str] = Field(default=None, description="Email Google Admin")


# ── USER LINK / DASHBOARD MODELS ──────────────────────────────────────────────

class UserLoginRequest(BaseModel):
    passcode: str = Field(..., description="Vercel passcode/kata sandi user")
    slug: Optional[str] = Field(default=None, description="Slug link dashboard mitra")


class UserPauseRequest(BaseModel):
    store_id: str = Field(..., description="Target Store ID")
    duration_type: str = Field(..., description="'30_min', '60_min', legacy 'rest_of_day' (24 jam), or 'custom'")
    custom_until: Optional[str] = Field(default=None, description="Target pause end time in local ISO format when duration_type is custom")
    custom_minutes: Optional[int] = Field(default=None, description="Legacy custom pause duration in minutes")
