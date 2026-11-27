// Service worker extension GemuseAPI.
// Saat ini tidak ada tugas latar yang berjalan terus-menerus.
// File ini dipertahankan supaya manifest V3 valid dan siap dipakai
// kalau nanti perlu keepalive / auto-refresh cookie (dengan izin pengguna).
chrome.runtime.onInstalled.addListener(() => {
  console.log("GemuseAPI extension terpasang. Buka popup untuk mengirim cookie ke server lokal.");
});
