// Dashboard GemuseAPI — vanilla JS, tanpa build.
// Semua teks Indonesia. Cookie tidak pernah ditampilkan di halaman.
const api = {
  async get(path) {
    const r = await fetch(path);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
    return data;
  },
  async del(path) {
    const r = await fetch(path, { method: "DELETE" });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
    return data;
  },
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function statusLabel(acc) {
  if (!acc.enabled) return "Nonaktif";
  if (acc.status === "region_blocked") return "Blokir Region";
  if (acc.used_percent >= 100) return "Kuota Habis";
  if (acc.cooldown_until && acc.cooldown_until * 1000 > Date.now()) return "Cooldown";
  return "Aktif";
}

async function loadHealth() {
  try {
    const h = await api.get("/api/health");
    document.getElementById("health").textContent =
      `Server OK • driver: ${h.driver} • strategi: ${h.strategy} • akun: ${h.accounts} (bisa dipakai: ${h.usable_accounts}) • job: ${h.jobs}`;
  } catch (e) {
    document.getElementById("health").textContent = "Server tidak bisa dihubungi: " + e.message;
  }
}

async function loadAccounts() {
  const wrap = document.getElementById("accounts");
  const empty = document.getElementById("accounts-empty");
  try {
    const { accounts } = await api.get("/api/accounts");
    empty.style.display = accounts.length ? "none" : "";
    wrap.innerHTML = accounts.map((acc) => {
      const pct = Math.max(0, Math.min(100, Number(acc.used_percent) || 0));
      const status = statusLabel(acc);
      return `<article class="card">
        <h3>${esc(acc.label)}</h3>
        <p class="muted">ID: ${esc(acc.id)} • Status: <strong>${esc(status)}</strong></p>
        <div class="bar"><div class="bar-fill" style="width:${pct}%"></div></div>
        <p>Kuota terpakai: ${pct}%</p>
        <div class="row">
          <button data-act="toggle" data-id="${esc(acc.id)}" data-enabled="${acc.enabled}">${acc.enabled ? "Nonaktifkan" : "Aktifkan"}</button>
          <button data-act="quota" data-id="${esc(acc.id)}">Cek Kuota</button>
          <button data-act="delete" data-id="${esc(acc.id)}">Hapus</button>
        </div>
        <p class="msg" id="msg-${esc(acc.id)}"></p>
      </article>`;
    }).join("");
  } catch (e) {
    empty.textContent = "Gagal memuat akun: " + e.message;
  }
}

async function loadJobs() {
  const wrap = document.getElementById("jobs");
  try {
    const { jobs } = await api.get("/api/videos");
    if (!jobs.length) { wrap.innerHTML = "<p class='muted'>Belum ada job.</p>"; return; }
    wrap.innerHTML = jobs.slice().reverse().map((j) => `
      <article class="card">
        <p><strong>${esc(j.id)}</strong> — ${esc(j.status)}</p>
        <p>${esc(j.prompt)}</p>
        <p class="muted">Rasio: ${esc(j.aspect_ratio)} • Akun: ${esc(j.account_label || "-")} • File: ${esc(j.file || "-")}</p>
        ${j.error ? `<p class="error">Error: ${esc(j.error)}</p>` : ""}
      </article>`).join("");
  } catch (e) {
    wrap.innerHTML = "<p class='error'>Gagal memuat job: " + esc(e.message) + "</p>";
  }
}

async function loadMedia() {
  const ul = document.getElementById("media");
  try {
    const { media } = await api.get("/api/media");
    ul.innerHTML = media.length
      ? media.map((f) => `<li>${esc(f)}</li>`).join("")
      : "<li class='muted'>Belum ada file media.</li>";
  } catch (e) {
    ul.innerHTML = "<li class='error'>Gagal memuat media.</li>";
  }
}

async function refreshAll() {
  await Promise.all([loadHealth(), loadAccounts(), loadJobs(), loadMedia()]);
}

document.getElementById("accounts").addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button[data-act]");
  if (!btn) return;
  const id = btn.dataset.id;
  const msgEl = document.getElementById("msg-" + id);
  try {
    if (btn.dataset.act === "delete") {
      if (!confirm("Hapus akun ini dari pool?")) return;
      await api.del("/api/accounts/" + encodeURIComponent(id));
    } else if (btn.dataset.act === "toggle") {
      const action = btn.dataset.enabled === "true" ? "disable" : "enable";
      await api.post(`/api/accounts/${encodeURIComponent(id)}/${action}`);
    } else if (btn.dataset.act === "quota") {
      const data = await api.post(`/api/accounts/${encodeURIComponent(id)}/quota`);
      if (msgEl) msgEl.textContent = `Kuota: ${data.quota.used_percent}% • status: ${data.quota.status} (${data.quota.source})`;
      return;
    }
    await refreshAll();
  } catch (e) {
    if (msgEl) msgEl.textContent = "Gagal: " + e.message;
    else alert("Gagal: " + e.message);
  }
});

document.getElementById("add-account-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const msg = document.getElementById("add-account-msg");
  const label = form.label.value.trim();
  const service_url = form.service_url.value.trim();
  const raw = form.cookies.value.trim();
  let cookies = raw;
  try { cookies = JSON.parse(raw); } catch { /* biarkan string mentah, server yang parse */ }
  try {
    await api.post("/api/accounts", { label, service_url, cookies });
    msg.textContent = "Akun ditambahkan.";
    form.reset();
    await refreshAll();
  } catch (e) {
    msg.textContent = "Gagal: " + e.message;
  }
});

document.getElementById("create-video-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const msg = document.getElementById("create-video-msg");
  try {
    const { job } = await api.post("/api/videos", {
      prompt: form.prompt.value.trim(),
      aspect_ratio: form.aspect_ratio.value,
    });
    msg.textContent = "Job dibuat: " + job.id + " (" + job.status + ")";
    form.reset();
    await refreshAll();
  } catch (e) {
    msg.textContent = "Gagal: " + e.message;
  }
});

document.getElementById("refresh-btn").addEventListener("click", refreshAll);

refreshAll();
setInterval(() => { loadJobs(); loadMedia(); loadHealth(); }, 5000);
