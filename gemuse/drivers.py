"""Driver video: MockDriver (jalan) dan BrowserDriver (stub jujur).

PENTING — batasan jujur:
Muse AI (muse.ai) tidak punya API publik. Repo sejenis di GitHub
(mis. muse2api / muse-opencode) bekerja dengan mengotomasi web chat
muse.ai lewat Chromium + cookie login. Itu rapuh, bisa rusak kapan
saja kalau situs berubah, dan bisa membuat akun kena blokir.

Karena itu driver default di repo ini adalah MockDriver: ia
mensimulasikan job video (queued -> running -> done) dan menulis
file placeholder di ``data/media/`` supaya dashboard, pool, dan
API bisa diuji end-to-end tanpa akun sungguhan.

BrowserDriver di sini sengaja STUB: ia raise NotImplementedError
dengan pesan yang jelas. Jangan klaim repo ini bisa generate video
beneran via web Muse sebelum driver browser sungguhan
diimplementasikan dan diuji terhadap akun nyata.
"""
from __future__ import annotations

import os
import time


class DriverError(Exception):
    """Gagal generate yang generik (masuk cooldown)."""


class RegionBlockedError(DriverError):
    """Akun kena blokir region — video tidak tersedia di wilayah ini."""


class Driver:
    """Interface driver video."""

    name = "base"

    def generate_video(self, account, prompt, aspect_ratio, job_id):
        """Hasilkan video untuk *job_id*. Kembalikan dict info file.

        Harus raise RegionBlockedError / DriverError kalau gagal.
        """
        raise NotImplementedError("driver belum diimplementasikan")


class MockDriver(Driver):
    """Driver simulasi: tidak memanggil Muse sama sekali.

    Menulis file placeholder ``<job_id>.mp4`` (teks biasa, bukan
    video sungguhan) di ``media_dir`` setelah jeda singkat, supaya
    alur job bisa dilihat di dashboard.
    """

    name = "mock"

    def __init__(self, media_dir, delay_seconds=2.0):
        self.media_dir = media_dir
        self.delay_seconds = float(delay_seconds)

    def generate_video(self, account, prompt, aspect_ratio, job_id):
        if getattr(account, "status", "") == "region_blocked":
            raise RegionBlockedError(
                "Video tidak tersedia untuk akun di wilayah ini "
                "(region_blocked). Tambah akun dari wilayah yang didukung."
            )
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        os.makedirs(self.media_dir, exist_ok=True)
        path = os.path.join(self.media_dir, f"{job_id}.mp4")
        content = (
            "GEMUSE MOCK VIDEO — BUKAN VIDEO SUNGGUHAN\n"
            f"job: {job_id}\n"
            f"account: {getattr(account, 'label', '?')}\n"
            f"prompt: {prompt}\n"
            f"aspect_ratio: {aspect_ratio}\n"
            "Dibuat oleh MockDriver untuk pengujian dashboard.\n"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"file": path, "filename": f"{job_id}.mp4", "duration_seconds": 10}


class BrowserDriver(Driver):
    """STUB driver browser asli — belum diimplementasikan.

    Implementasi sungguhan butuh:
    - Chromium / Chrome terpasang dan bisa dikendalikan (CDP),
    - login manual ke muse.ai di browser itu,
    - cookie sesi dari login tersebut (nama cookie yang dipakai repo
      sejenis — BISA BERUBAH sewaktu-waktu, cek ulang di browser:
      ``hatch_sess``, ``hatch_gw``, ``hatch_native_auth_device``),
    - penanganan kuota, antrean, dan error region_blocked dari web.

    Sampai itu ada dan teruji, driver ini sengaja menolak jalan
    daripada pura-pura berhasil.
    """

    name = "browser"

    def __init__(self, media_dir):
        self.media_dir = media_dir

    def generate_video(self, account, prompt, aspect_ratio, job_id):
        raise NotImplementedError(
            "BrowserDriver belum diimplementasikan: generate video beneran "
            "via web muse.ai butuh Chromium + login manual + cookie sesi, "
            "dan belum ada di repo ini. Pakai GEMUSE_DRIVER=mock untuk "
            "pengujian, atau implementasikan driver ini dulu."
        )
