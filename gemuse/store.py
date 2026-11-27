"""Penyimpanan JSON atomik untuk akun dan job.

Semua data disimpan di ``data/`` (di-gitignore). Penulisan memakai
file sementara + ``os.replace`` supaya file tidak rusak kalau proses
mati di tengah jalan. Cookie TIDAK pernah ditulis ke log.
"""
from __future__ import annotations

import json
import os
import tempfile


def load_json(path, default):
    """Muat JSON dari *path*, kembalikan *default* kalau file tidak ada/rusak."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError):
        return default
    return data if data is not None else default


def save_json_atomic(path, data):
    """Simpan *data* sebagai JSON secara atomik."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_accounts(path):
    """Muat daftar akun (list of dict)."""
    data = load_json(path, [])
    return data if isinstance(data, list) else []


def save_accounts(path, accounts):
    save_json_atomic(path, list(accounts))


def load_jobs(path):
    data = load_json(path, [])
    return data if isinstance(data, list) else []


def save_jobs(path, jobs):
    save_json_atomic(path, list(jobs))
