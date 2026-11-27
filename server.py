#!/usr/bin/env python3
"""GemuseAPI — server dashboard pool akun Muse AI (stdlib-only).

Jalankan:  python3 server.py
Buka:      http://127.0.0.1:8787/dashboard

Konfigurasi via environment atau file .env di root repo:
  GEMUSE_HOST=127.0.0.1
  GEMUSE_PORT=8787
  GEMUSE_ADMIN_KEY=           # kalau di-set, semua /api/* butuh X-Admin-Key
  GEMUSE_DRIVER=mock          # mock | browser (browser masih stub)
  GEMUSE_STRATEGY=round_robin # round_robin | least_used

Route:
  GET  /                    -> redirect /dashboard
  GET  /dashboard           -> static/index.html
  GET  /static/<file>       -> file statis
  GET  /api/health
  GET  /api/accounts
  POST /api/accounts
  DELETE /api/accounts/{id}
  POST /api/accounts/{id}/enable
  POST /api/accounts/{id}/disable
  POST /api/accounts/{id}/quota
  POST /api/videos
  GET  /api/videos
  GET  /api/videos/{id}
  GET  /api/media

Cookie mentah TIDAK PERNAH ditulis ke log maupun ke respons API
(respons hanya menampilkan "***" sebagai placeholder nama cookie).
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from gemuse.drivers import BrowserDriver, DriverError, MockDriver, RegionBlockedError
from gemuse.pool import Account, AccountPool
from gemuse.store import load_accounts, load_jobs, save_accounts, save_jobs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MEDIA_DIR = os.path.join(DATA_DIR, "media")
STATIC_DIR = os.path.join(BASE_DIR, "static")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
JOBS_FILE = os.path.join(DATA_DIR, "jobs.json")


def load_dotenv(path):
    """Muat .env sederhana (KEY=VALUE) ke os.environ kalau belum ada."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    except FileNotFoundError:
        pass


load_dotenv(os.path.join(BASE_DIR, ".env"))

HOST = os.environ.get("GEMUSE_HOST", "127.0.0.1")
PORT = int(os.environ.get("GEMUSE_PORT", "8787"))
ADMIN_KEY = os.environ.get("GEMUSE_ADMIN_KEY", "")
DRIVER_NAME = os.environ.get("GEMUSE_DRIVER", "mock").lower()
STRATEGY = os.environ.get("GEMUSE_STRATEGY", "round_robin")
if STRATEGY not in ("round_robin", "least_used"):
    STRATEGY = "round_robin"

os.makedirs(MEDIA_DIR, exist_ok=True)

# State global (dijaga lock karena ThreadingHTTPServer).
_lock = threading.Lock()
pool = AccountPool.from_list(load_accounts(ACCOUNTS_FILE), strategy=STRATEGY)
jobs = load_jobs(JOBS_FILE)


def get_driver():
    if DRIVER_NAME == "browser":
        return BrowserDriver(MEDIA_DIR)
    return MockDriver(MEDIA_DIR)


DRIVER = get_driver()


def persist_accounts():
    with _lock:
        save_accounts(ACCOUNTS_FILE, [a.to_dict(redact_cookies=False) for a in pool.accounts])


def persist_jobs():
    with _lock:
        save_jobs(JOBS_FILE, jobs)


def parse_cookies(raw):
    """Terima cookies sebagai dict, string header 'a=1; b=2', atau
    list ala EditThisCookie [{'name':..,'value':..}]. Kembalikan dict."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, list):
        out = {}
        for item in raw:
            if isinstance(item, dict) and "name" in item:
                out[str(item["name"])] = str(item.get("value", ""))
        return out
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}
        # Coba JSON dulu (EditThisCookie / dict JSON).
        try:
            parsed = json.loads(raw)
            return parse_cookies(parsed)
        except (json.JSONDecodeError, ValueError):
            pass
        out = {}
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                out[k.strip()] = v.strip()
        return out
    return {}


def find_job(job_id):
    for job in jobs:
        if job.get("id") == job_id:
            return job
    return None


def run_video_job(job):
    """Jalankan satu job di thread latar: queued -> running -> done/failed.

    Failover: kalau akun pertama gagal (bukan region_blocked), coba
    akun berikutnya yang masih usable, maksimal 3 percobaan.
    """
    attempts = 0
    last_error = None
    while attempts < 3:
        attempts += 1
        account = pool.pick()
        if account is None:
            job["status"] = "failed"
            job["error"] = "Tidak ada akun yang bisa dipakai di pool (503: no usable account)"
            job["updated_at"] = time.time()
            persist_jobs()
            return
        job["account_id"] = account.id
        job["account_label"] = account.label
        job["status"] = "running"
        job["updated_at"] = time.time()
        persist_jobs()
        try:
            result = DRIVER.generate_video(account, job["prompt"], job.get("aspect_ratio", "9:16"), job["id"])
        except RegionBlockedError as exc:
            pool.mark_failure(account.id, error_type="region_blocked")
            persist_accounts()
            last_error = str(exc)
            # Region-blocked tidak dicoba ulang ke akun itu, tapi
            # failover ke akun lain masih boleh dicoba.
            continue
        except NotImplementedError as exc:
            job["status"] = "failed"
            job["error"] = str(exc)
            job["updated_at"] = time.time()
            persist_jobs()
            return
        except DriverError as exc:
            pool.mark_failure(account.id)
            persist_accounts()
            last_error = str(exc)
            continue
        except Exception as exc:  # noqa: BLE001 - jangan matikan thread tanpa status
            pool.mark_failure(account.id)
            persist_accounts()
            last_error = str(exc)
            continue
        # Sukses.
        pool.mark_success(account.id)
        persist_accounts()
        job["status"] = "done"
        job["file"] = result.get("filename")
        job["updated_at"] = time.time()
        persist_jobs()
        return
    job["status"] = "failed"
    job["error"] = last_error or "Gagal setelah 3 percobaan"
    job["updated_at"] = time.time()
    persist_jobs()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # -- util ---------------------------------------------------------
    def log_message(self, fmt, *args):
        # Log ringkas tanpa body (body bisa berisi cookie).
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, status, text, content_type="text/html; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def check_auth(self):
        """Kalau ADMIN_KEY di-set, /api/* butuh header X-Admin-Key."""
        if not ADMIN_KEY:
            return True
        return self.headers.get("X-Admin-Key") == ADMIN_KEY

    def serve_static(self, filename):
        # Cegah path traversal.
        safe = os.path.basename(filename)
        path = os.path.join(STATIC_DIR, safe)
        if not os.path.isfile(path):
            self.send_json(404, {"error": "file tidak ditemukan"})
            return
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
        }
        ext = os.path.splitext(safe)[1].lower()
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # -- routing ------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/dashboard")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/dashboard":
            index = os.path.join(STATIC_DIR, "index.html")
            with open(index, encoding="utf-8") as f:
                self.send_text(200, f.read())
            return
        if path.startswith("/static/"):
            self.serve_static(unquote(path[len("/static/"):]))
            return
        if path.startswith("/api/"):
            if not self.check_auth():
                self.send_json(401, {"error": "butuh header X-Admin-Key yang benar"})
                return
            self.handle_api_get(path)
            return
        self.send_json(404, {"error": "route tidak ditemukan"})

    def handle_api_get(self, path):
        if path == "/api/health":
            self.send_json(200, {
                "status": "ok",
                "driver": DRIVER.name,
                "strategy": pool.strategy,
                "accounts": len(pool.accounts),
                "usable_accounts": len(pool.usable()),
                "jobs": len(jobs),
            })
            return
        if path == "/api/accounts":
            self.send_json(200, {"accounts": pool.to_list()})
            return
        if path == "/api/videos":
            self.send_json(200, {"jobs": list(jobs)})
            return
        if path.startswith("/api/videos/"):
            job_id = unquote(path[len("/api/videos/"):])
            job = find_job(job_id)
            if job is None:
                self.send_json(404, {"error": "job tidak ditemukan"})
                return
            self.send_json(200, {"job": job})
            return
        if path == "/api/media":
            files = sorted(os.listdir(MEDIA_DIR)) if os.path.isdir(MEDIA_DIR) else []
            self.send_json(200, {"media": files})
            return
        self.send_json(404, {"error": "route tidak ditemukan"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            self.send_json(404, {"error": "route tidak ditemukan"})
            return
        if not self.check_auth():
            self.send_json(401, {"error": "butuh header X-Admin-Key yang benar"})
            return
        body = self.read_json_body()

        if path == "/api/accounts":
            label = (body.get("label") or "").strip()
            if not label:
                self.send_json(400, {"error": "label wajib diisi"})
                return
            cookies = parse_cookies(body.get("cookies"))
            if not cookies:
                self.send_json(400, {"error": "cookies wajib diisi (dict / raw Cookie header / JSON EditThisCookie)"})
                return
            account = Account(
                label=label,
                service_url=(body.get("service_url") or "").strip(),
                cookies=cookies,
            )
            pool.add(account)
            persist_accounts()
            self.send_json(201, {"account": account.to_dict()})
            return

        if path.startswith("/api/accounts/"):
            rest = path[len("/api/accounts/"):]
            parts = rest.split("/")
            account_id = unquote(parts[0])
            action = parts[1] if len(parts) > 1 else ""
            account = pool.get(account_id)
            if account is None:
                self.send_json(404, {"error": "akun tidak ditemukan"})
                return
            if action == "enable":
                pool.set_enabled(account_id, True)
                persist_accounts()
                self.send_json(200, {"account": account.to_dict()})
                return
            if action == "disable":
                pool.set_enabled(account_id, False)
                persist_accounts()
                self.send_json(200, {"account": account.to_dict()})
                return
            if action == "quota":
                # Mock: kuota dibaca dari status tersimpan. Driver browser
                # sungguhan akan membaca Settings -> Usage di sini.
                self.send_json(200, {
                    "account": account.to_dict(),
                    "quota": {
                        "used_percent": account.used_percent,
                        "status": account.status,
                        "source": "mock" if DRIVER.name == "mock" else "browser",
                        "note": "Kuota mock = nilai tersimpan. Driver browser membaca Settings -> Usage.",
                    },
                })
                return
            self.send_json(404, {"error": "route tidak ditemukan"})
            return

        if path == "/api/videos":
            prompt = (body.get("prompt") or "").strip()
            if not prompt:
                self.send_json(400, {"error": "prompt wajib diisi"})
                return
            aspect = body.get("aspect_ratio") or "9:16"
            if aspect not in ("9:16", "16:9", "1:1"):
                self.send_json(400, {"error": "aspect_ratio harus 9:16, 16:9, atau 1:1"})
                return
            if not pool.usable():
                self.send_json(503, {"error": "no usable account in pool — tidak ada akun yang bisa dipakai"})
                return
            job = {
                "id": uuid.uuid4().hex[:12],
                "prompt": prompt,
                "aspect_ratio": aspect,
                "status": "queued",
                "account_id": None,
                "account_label": None,
                "file": None,
                "error": None,
                "created_at": time.time(),
                "updated_at": time.time(),
            }
            with _lock:
                jobs.append(job)
            persist_jobs()
            threading.Thread(target=run_video_job, args=(job,), daemon=True).start()
            self.send_json(201, {"job": job})
            return

        self.send_json(404, {"error": "route tidak ditemukan"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            self.send_json(404, {"error": "route tidak ditemukan"})
            return
        if not self.check_auth():
            self.send_json(401, {"error": "butuh header X-Admin-Key yang benar"})
            return
        if path.startswith("/api/accounts/"):
            account_id = unquote(path[len("/api/accounts/"):].split("/")[0])
            if pool.remove(account_id):
                persist_accounts()
                self.send_json(200, {"deleted": account_id})
                return
            self.send_json(404, {"error": "akun tidak ditemukan"})
            return
        self.send_json(404, {"error": "route tidak ditemukan"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"GemuseAPI jalan di http://{HOST}:{PORT}/dashboard", flush=True)
    print(f"driver={DRIVER.name} strategy={pool.strategy} akun={len(pool.accounts)}", flush=True)
    print("Tekan Ctrl+C untuk berhenti.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBerhenti.", flush=True)


if __name__ == "__main__":
    main()
