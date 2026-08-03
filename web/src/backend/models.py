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
    subscription_status: str
    is_suspended: bool
    alasan_penangguhan: Optional[str] = ""
    pause_until: Optional[str] = None
    last_synced_at: Optional[str] = None


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
