"""Account pool: pilih akun Muse AI yang masih bisa dipakai.

Strategi:
- ``round_robin`` — bergantian secara adil.
- ``least_used`` — pilih akun dengan ``used_percent`` paling kecil.

Akun di-skip kalau:
- dinonaktifkan (``enabled=False``),
- ``used_percent`` sudah 100 (kuota habis),
- sedang cooldown (baru gagal, 10 menit),
- status ``region_blocked`` (akun kena blokir region permanen —
  ini TIDAK dijanjikan bisa ditembus, hanya dicatat sebagai status).

Setelah gagal, akun masuk cooldown 10 menit lalu otomatis bisa
dipakai lagi (kecuali region_blocked). Failover: kalau akun yang
dipilih gagal di tengah jalan, panggil ``mark_failure`` lalu
``pick()`` lagi untuk akun berikutnya.
"""
from __future__ import annotations

import time
import uuid

COOLDOWN_SECONDS = 10 * 60  # 10 menit


class Account:
    """Satu akun Muse AI di dalam pool."""

    def __init__(self, account_id=None, label="", service_url="", cookies=None,
                 enabled=True, status="active", used_percent=0,
                 last_used=0, cooldown_until=0, failed_count=0,
                 created_at=None):
        self.id = account_id or uuid.uuid4().hex[:12]
        self.label = label or self.id
        self.service_url = service_url or ""
        # cookies: dict nama -> nilai. Jangan pernah di-log mentah.
        self.cookies = dict(cookies or {})
        self.enabled = bool(enabled)
        self.status = status  # active | region_blocked
        self.used_percent = float(used_percent)
        self.last_used = float(last_used or 0)
        self.cooldown_until = float(cooldown_until or 0)
        self.failed_count = int(failed_count or 0)
        self.created_at = float(created_at or time.time())

    def is_usable(self, now=None):
        """True kalau akun boleh dipilih sekarang."""
        now = time.time() if now is None else now
        if not self.enabled:
            return False
        if self.status == "region_blocked":
            return False
        if self.used_percent >= 100:
            return False
        if self.cooldown_until > now:
            return False
        return True

    def to_dict(self, redact_cookies=True):
        """Serialisasi untuk JSON. Cookie selalu di-redact di output API."""
        cookies = self.cookies
        if redact_cookies:
            cookies = {k: "***" for k in cookies} if cookies else {}
        return {
            "id": self.id,
            "label": self.label,
            "service_url": self.service_url,
            "cookies": cookies,
            "enabled": self.enabled,
            "status": self.status,
            "used_percent": self.used_percent,
            "last_used": self.last_used,
            "cooldown_until": self.cooldown_until,
            "failed_count": self.failed_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            account_id=data.get("id"),
            label=data.get("label", ""),
            service_url=data.get("service_url", ""),
            cookies=data.get("cookies") or {},
            enabled=data.get("enabled", True),
            status=data.get("status", "active"),
            used_percent=data.get("used_percent", 0),
            last_used=data.get("last_used", 0),
            cooldown_until=data.get("cooldown_until", 0),
            failed_count=data.get("failed_count", 0),
            created_at=data.get("created_at"),
        )


class AccountPool:
    """Kumpulan akun + logika pemilihan dan failover."""

    def __init__(self, accounts=None, strategy="round_robin"):
        self.accounts = list(accounts or [])
        if strategy not in ("round_robin", "least_used"):
            raise ValueError("strategy harus 'round_robin' atau 'least_used'")
        self.strategy = strategy
        self._rr_index = 0

    # -- CRUD ---------------------------------------------------------
    def add(self, account):
        self.accounts.append(account)
        return account

    def remove(self, account_id):
        before = len(self.accounts)
        self.accounts = [a for a in self.accounts if a.id != account_id]
        return len(self.accounts) < before

    def get(self, account_id):
        for a in self.accounts:
            if a.id == account_id:
                return a
        return None

    def usable(self, now=None):
        now = time.time() if now is None else now
        return [a for a in self.accounts if a.is_usable(now)]

    # -- Pemilihan ----------------------------------------------------
    def pick(self, now=None):
        """Pilih satu akun yang bisa dipakai, atau None kalau tidak ada."""
        now = time.time() if now is None else now
        candidates = self.usable(now)
        if not candidates:
            return None
        if self.strategy == "least_used":
            # Kuota paling sedikit terpakai; kalau seri, yang paling
            # lama tidak dipakai duluan.
            return min(candidates, key=lambda a: (a.used_percent, a.last_used))
        # round_robin: putar pointer di atas daftar akun yang usable.
        account = candidates[self._rr_index % len(candidates)]
        self._rr_index = (self._rr_index + 1) % max(len(candidates), 1)
        # Catat pemakaian supaya least_used / urutan tetap konsisten.
        account.last_used = now
        return account

    # -- Hasil pemakaian ----------------------------------------------
    def mark_success(self, account_id, used_percent=None, now=None):
        account = self.get(account_id)
        if account is None:
            return None
        now = time.time() if now is None else now
        account.last_used = now
        account.failed_count = 0
        if used_percent is not None:
            account.used_percent = max(0.0, min(100.0, float(used_percent)))
        return account

    def mark_failure(self, account_id, error_type=None, now=None):
        """Tandai gagal. Region-blocked = status permanen (sampai
        pengguna mengubah manual). Gagal lain = cooldown 10 menit."""
        account = self.get(account_id)
        if account is None:
            return None
        now = time.time() if now is None else now
        account.failed_count += 1
        if error_type == "region_blocked":
            account.status = "region_blocked"
            account.cooldown_until = 0
        else:
            account.cooldown_until = now + COOLDOWN_SECONDS
        return account

    def set_enabled(self, account_id, enabled):
        account = self.get(account_id)
        if account is None:
            return None
        account.enabled = bool(enabled)
        return account

    def to_list(self):
        return [a.to_dict() for a in self.accounts]

    @classmethod
    def from_list(cls, data, strategy="round_robin"):
        accounts = [Account.from_dict(d) for d in (data or [])]
        return cls(accounts, strategy=strategy)
