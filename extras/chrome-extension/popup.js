const $ = (id) => document.getElementById(id);

const els = {
  pageTitle: $("page-title"),
  pageUrl: $("page-url"),
  btnDownload: $("btn-download"),
  status: $("status"),
  statusText: $("status-text"),
  spinner: $("spinner"),
  result: $("result"),
  resultText: $("result-text"),
};

function _bytesToHuman(n) {
  if (typeof n !== "number") return "";
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / (1024 * 1024)).toFixed(2) + " MB";
}

function _setBusy(message) {
  els.status.classList.remove("hidden");
  els.statusText.textContent = message;
  els.result.classList.add("hidden");
  els.btnDownload.disabled = true;
}

function _setIdle() {
  els.status.classList.add("hidden");
  els.btnDownload.disabled = false;
}

function _setResult({ ok, message }) {
  _setIdle();
  els.result.classList.remove("hidden");
  els.result.classList.toggle("error", !ok);
  els.resultText.textContent = message;
}

async function _loadInitial() {
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const t = tabs && tabs[0];
    if (t) {
      els.pageTitle.textContent = t.title || "(untitled)";
      els.pageUrl.textContent = t.url || "";
      const okScheme = /^https?:/i.test(t.url || "");
      if (!okScheme) {
        els.btnDownload.disabled = true;
        els.statusText.textContent = "This page can't be captured (only http/https).";
        els.status.classList.remove("hidden");
        els.spinner.style.display = "none";
      }
    }
  } catch (_) {}
}

async function _capture() {
  _setBusy("Freezing page…");
  try {
    const resp = await chrome.runtime.sendMessage({ type: "le.capture.download" });
    if (!resp || !resp.ok) {
      _setResult({ ok: false, message: (resp && resp.error) || "Unknown error." });
      return;
    }
    const msg = "Saved " + (resp.filename || "snapshot") + " (" + _bytesToHuman(resp.bytes) + ").";
    _setResult({ ok: true, message: msg });
  } catch (e) {
    _setResult({ ok: false, message: (e && e.message) || String(e) });
  }
}

els.btnDownload.addEventListener("click", _capture);

_loadInitial();
