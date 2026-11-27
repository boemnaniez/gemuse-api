// Popup extension GemuseAPI.
// Membaca cookie muse.ai lalu POST ke server lokal yang diisi pengguna.
// TIDAK ada URL eksternal yang di-hardcode — service URL selalu dari input.
const COOKIE_NAMES = ["hatch_sess", "hatch_gw", "hatch_native_auth_device"];
// Catatan: nama cookie di atas dipakai repo sejenis (muse2api/muse-opencode)
// dan BISA BERUBAH sewaktu-waktu. Kalau login gagal, cek ulang nama
// cookie di DevTools browser (F12 -> Application -> Cookies -> muse.ai).

document.getElementById("send").addEventListener("click", async () => {
  const msg = document.getElementById("msg");
  const label = document.getElementById("label").value.trim();
  const serviceUrl = document.getElementById("service-url").value.trim().replace(/\/$/, "");
  if (!label) { msg.textContent = "Isi label akun dulu."; return; }
  // Service URL yang diizinkan: server lokal, atau Codespaces milikmu sendiri.
  // Codespaces: https://<nama>-8787.app.github.dev (tanpa /dashboard di akhir).
  // URL lain ditolak, supaya cookie tidak terkirim ke server orang lain.
  const isLocal = serviceUrl.startsWith("http://127.0.0.1") || serviceUrl.startsWith("http://localhost");
  let codespacesHost = false;
  try {
    const u = new URL(serviceUrl);
    codespacesHost = u.protocol === "https:" &&
      (u.hostname.endsWith(".app.github.dev") || u.hostname.endsWith(".github.dev"));
  } catch { codespacesHost = false; }
  if (!isLocal && !codespacesHost) {
    msg.textContent = "Demi keamanan, service URL harus server lokal (127.0.0.1 / localhost) atau Codespaces kamu sendiri (*.app.github.dev).";
    return;
  }
  msg.textContent = "Membaca cookie…";
  try {
    const cookies = {};
    for (const name of COOKIE_NAMES) {
      const cookie = await chrome.cookies.get({ url: "https://muse.ai/", name });
      if (cookie && cookie.value) cookies[name] = cookie.value;
    }
    if (!Object.keys(cookies).length) {
      msg.textContent = "Cookie tidak ditemukan. Pastikan kamu sudah login ke muse.ai di browser ini.";
      return;
    }
    const res = await fetch(serviceUrl + "/api/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, service_url: serviceUrl, cookies }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
    msg.textContent = "Berhasil! Akun '" + label + "' ditambahkan ke pool.";
  } catch (err) {
    msg.textContent = "Gagal: " + err.message + " — pastikan server GemuseAPI sedang jalan.";
  }
});
