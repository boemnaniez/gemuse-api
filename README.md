# GemuseAPI — Pool Banyak Akun Muse AI ke Satu Dashboard

> Satu "ember" untuk banyak "sumur": tampung beberapa akun Muse AI kamu ke
> dalam satu dashboard, lihat kuota tiap akun, dan biarkan server memilih
> akun yang masih ada kuotanya secara otomatis saat membuat video.

Proyek ini terinspirasi dari reel Facebook tentang **GemuseAPI** — sebuah
dashboard yang menampung banyak akun Muse AI supaya tidak perlu bolak-balik
membuka akun satu per satu.

**Batasan jujur — baca dulu sebelum memakai:**
- Ini proyek **tidak resmi**, **bukan produk Meta**, dan tidak terafiliasi
  dengan Muse AI / muse.ai.
- Muse AI **tidak punya API publik**. Repo sejenis bekerja dengan
  mengotomasi web chat muse.ai lewat browser + cookie login. Cara itu
  rapuh (bisa rusak kalau situs berubah) dan bisa membuat akun kena
  blokir — termasuk **blokir region permanen** seperti yang terlihat di
  video aslinya.
- Repo ini **TIDAK menjanjikan bisa menembus blokir region**. Akun yang
  kena blokir region hanya dicatat sebagai status `region_blocked` dan
  di-skip dari pool.
- Driver default adalah **MockDriver**: ia hanya mensimulasikan job
  video dan menulis file placeholder, supaya dashboard dan API bisa
  diuji tanpa akun sungguhan. **Video beneran belum bisa dibuat** sampai
  `BrowserDriver` diimplementasikan dan diuji terhadap akun nyata
  (lihat `gemuse/drivers.py`).
- Gunakan **akunmu sendiri**, di komputermu sendiri, atas risikomu
  sendiri. **Jangan pernah membagikan cookie** ke orang lain atau ke
  server yang bukan milikmu.

## Fitur

- Dashboard web (vanilla JS, tanpa build) di `http://127.0.0.1:8787/dashboard`
- Tambah / hapus / aktifkan / nonaktifkan akun dari dashboard atau API
- Bar kuota tiap akun (`used_percent`), status: Aktif / Nonaktif /
  Kuota Habis / Cooldown / Blokir Region
- Pool dengan strategi `round_robin` (bergantian) atau `least_used`
  (pilih kuota paling sedikit terpakai)
- Skip otomatis: akun nonaktif, kuota 100%, cooldown, `region_blocked`
- Cooldown 10 menit setelah gagal, lalu otomatis bisa dipakai lagi
- Failover: kalau satu akun gagal, coba akun berikutnya (maks. 3x)
- Buat video via `POST /api/videos` — job berjalan di latar
  (`queued` → `running` → `done` / `failed`), daftar job + media
  terlihat di dashboard
- Extension Chrome (Manifest V3) untuk mengambil cookie muse.ai dan
  mengirimkannya ke server lokal
- Auth opsional: kalau `GEMUSE_ADMIN_KEY` di-set, semua `/api/*`
  butuh header `X-Admin-Key`
- **Stdlib-only**: tidak ada dependensi pip. Cukup `python3`.

## Persyaratan

- Python 3.10+ (diuji di Python 3.12)
- Tidak perlu `pip install` apa pun
- (Opsional, untuk driver browser nanti) Chromium / Chrome

## Cara Install

### Linux / macOS

```bash
git clone https://github.com/boemnaniez/gemuse-api.git
cd gemuse-api
cp .env.example .env   # lalu edit kalau perlu
python3 server.py
# Buka http://127.0.0.1:8787/dashboard
```

### Windows

```powershell
git clone https://github.com/boemnaniez/gemuse-api.git
cd gemuse-api
copy .env.example .env
py server.py
# Buka http://127.0.0.1:8787/dashboard
```

Tidak ada `pip install -r requirements.txt` — file itu sengaja kosong
(stdlib only). Jalankan tes dengan:

```bash
python3 -m unittest discover -s tests -v
```

## Cara Tambah Akun

### Opsi A — lewat extension Chrome (disarankan)

1. Buka `chrome://extensions`, aktifkan **Developer mode**.
2. Klik **Load unpacked**, pilih folder `extension/` di repo ini.
3. Login ke **muse.ai** di Chrome.
4. Klik ikon extension GemuseAPI, isi **label akun** dan **service URL**,
   klik **Ambil Cookie & Kirim ke Server**.
   - Server di laptop sendiri: `http://127.0.0.1:8787`
   - Server di Codespaces: `https://<nama>-8787.app.github.dev`
     (alamat yang sama dengan dashboard, **tanpa** `/dashboard` di akhir;
     contoh punyamu: `https://obscure-waffle-5vpq54gg5p97fvw9-8787.app.github.dev`).
     Extension hanya mau kirim ke localhost atau `*.app.github.dev` /
     `*.github.dev` milikmu sendiri — URL lain ditolak.
5. Akun muncul di dashboard dengan kuotanya.

Extension membaca cookie ini dari `muse.ai` (nama dari repo sejenis,
**bisa berubah** — cek ulang di DevTools kalau gagal):
`hatch_sess`, `hatch_gw`, `hatch_native_auth_device`.

### Opsi B — lewat dashboard / API

Tempel cookies sebagai JSON dict, raw header `nama=nilai; nama2=nilai2`,
atau JSON ala EditThisCookie ke form **Tambah Akun**, atau:

```bash
curl -X POST http://127.0.0.1:8787/api/accounts \
  -H 'Content-Type: application/json' \
  -d '{"label":"Akun 1","service_url":"http://127.0.0.1:8787","cookies":{"hatch_sess":"...","hatch_gw":"..."}}'
```

Respons tidak pernah menampilkan isi cookie — hanya `***`.

Contoh isi `data/accounts.json` ada di `accounts.example.json`
(cookie di contoh itu `REDACTED`, jangan dipakai apa adanya).

## Cara Generate Video

Dari dashboard: isi **prompt** dan pilih rasio, klik **Buat Video**.
Server memilih akun yang masih bisa dipakai, lalu menjalankan job di latar.

Via API:

```bash
curl -X POST http://127.0.0.1:8787/api/videos \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Sopir angkot menyelamatkan anak kecil yang mengejar bola","aspect_ratio":"9:16"}'

curl http://127.0.0.1:8787/api/videos
curl http://127.0.0.1:8787/api/videos/<job_id>
curl http://127.0.0.1:8787/api/media
```

Dengan driver `mock`, file yang dihasilkan adalah placeholder teks
bernama `<job_id>.mp4` di `data/media/` — **bukan video sungguhan**.
Itu sengaja, supaya alurnya bisa diuji tanpa akun.

## API

Semua respons JSON. Kalau `GEMUSE_ADMIN_KEY` di-set, kirim header
`X-Admin-Key: <kunci>` di setiap request `/api/*`.

| Method | Route | Keterangan |
|---|---|---|
| GET | `/` | Redirect ke `/dashboard` |
| GET | `/dashboard` | Dashboard web |
| GET | `/api/health` | Status server, driver, jumlah akun |
| GET | `/api/accounts` | Daftar akun (cookie di-redact) |
| POST | `/api/accounts` | Tambah akun `{label, service_url, cookies}` |
| DELETE | `/api/accounts/{id}` | Hapus akun |
| POST | `/api/accounts/{id}/enable` | Aktifkan akun |
| POST | `/api/accounts/{id}/disable` | Nonaktifkan akun |
| POST | `/api/accounts/{id}/quota` | Lihat kuota akun |
| POST | `/api/videos` | Buat video `{prompt, aspect_ratio}` |
| GET | `/api/videos` | Daftar job |
| GET | `/api/videos/{id}` | Satu job |
| GET | `/api/media` | Daftar file di `data/media/` |

Rasio yang diterima: `9:16`, `16:9`, `1:1`.
Kalau tidak ada akun yang bisa dipakai: `503 no usable account in pool`.

## Konfigurasi (.env)

```env
GEMUSE_HOST=127.0.0.1
GEMUSE_PORT=8787
GEMUSE_ADMIN_KEY=
GEMUSE_DRIVER=mock
GEMUSE_STRATEGY=round_robin
```

- `GEMUSE_DRIVER`: `mock` (default, simulasi) atau `browser`
  (stub — belum diimplementasikan, akan error jelas kalau dipakai).
- `GEMUSE_STRATEGY`: `round_robin` atau `least_used`.
- `GEMUSE_ADMIN_KEY`: kosong = tanpa auth (hanya untuk lokal).
  Isi dengan string acak kalau server bisa diakses orang lain.

## Struktur Repo

```
gemuse-api/
├── server.py            # HTTP server stdlib (ThreadingHTTPServer)
├── gemuse/
│   ├── __init__.py
│   ├── pool.py          # Account + AccountPool (round_robin / least_used)
│   ├── store.py         # Load/save JSON atomik
│   └── drivers.py       # MockDriver (jalan) + BrowserDriver (stub)
├── static/              # Dashboard: index.html, app.js, style.css
├── extension/           # Extension Chrome MV3 (popup + background)
├── tests/
│   └── test_pool.py     # Tes pool (unittest stdlib)
├── accounts.example.json
├── .env.example
├── requirements.txt     # Kosong — stdlib only
└── data/                # Dibuat saat jalan; di-gitignore (berisi cookie!)
```

## Keamanan

- Server default hanya bind `127.0.0.1` — tidak bisa diakses dari
  internet. Jangan ubah ke `0.0.0.0` tanpa auth + TLS.
- `data/accounts.json` berisi cookie login — file itu ada di
  `.gitignore`. **Jangan pernah commit / push / kirim** file itu.
- Cookie tidak pernah ditulis ke log server dan tidak pernah muncul
  di respons API.

## Lisensi

MIT — lihat `LICENSE`. Copyright 2026 boemnaniez.
