/*
 * background.js — service worker for Language Engine Capture.
 *
 * The popup sends messages here; this worker injects freeze.js into the
 * active tab, collects the resulting HTML, and triggers a local download.
 */

async function _activeTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const t = tabs && tabs[0];
  if (!t) throw new Error("No active tab.");
  if (!/^https?:/i.test(t.url || "")) {
    throw new Error("Cannot capture this page (only http/https URLs are supported).");
  }
  return t;
}

async function _installResourceFetchBridge(tabId, allFrames) {
  await chrome.scripting.executeScript({
    target: { tabId, allFrames: !!allFrames },
    world: "ISOLATED",
    func: () => {
      const REQUEST_EVENT = "le:resource-fetch-request";
      const RESPONSE_EVENT = "le:resource-fetch-response";
      if (document.documentElement) {
        document.documentElement.setAttribute("data-le-resource-fetch-bridge", "1");
      }
      if (window.__languageEngineResourceFetchBridgeInstalled) return;
      window.__languageEngineResourceFetchBridgeInstalled = true;

      document.addEventListener(REQUEST_EVENT, async (event) => {
        const detail = event && event.detail;
        if (!detail || !detail.id || !detail.url) return;
        let response;
        try {
          response = await chrome.runtime.sendMessage({
            type: "le.resource.fetch",
            id: detail.id,
            url: detail.url,
            responseType: detail.responseType || "dataUrl",
          });
        } catch (e) {
          response = { ok: false, error: (e && e.message) || String(e) };
        }
        try {
          document.dispatchEvent(new CustomEvent(RESPONSE_EVENT, {
            detail: Object.assign({ id: detail.id }, response || { ok: false, error: "No bridge response." }),
          }));
        } catch (_) {}
      });
    },
  });
}

async function _installResourceFetchBridgeBestEffort(tabId) {
  try {
    await _installResourceFetchBridge(tabId, true);
  } catch (_) {
    try { await _installResourceFetchBridge(tabId, false); } catch (_) {}
  }
}

async function _captureActiveTab() {
  const tab = await _activeTab();

  await _installResourceFetchBridgeBestEffort(tab.id);

  // Inject into every frame so cross-origin frames can snapshot themselves;
  // the top frame receives those frame snapshots in a second pass and embeds
  // them as inert srcdoc iframes where the iframe src can be matched.
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      files: ["freeze.js"],
      world: "MAIN",
    });
  } catch (_) {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: false },
      files: ["freeze.js"],
      world: "MAIN",
    });
  }

  const frameSnapshotsByUrl = {};
  try {
    const framePass = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: async (freezeOpts) => {
        if (window.top === window) return { ok: true, skippedTop: true };
        if (typeof window.__languageEngineFreezeDom !== "function") {
          return { ok: false, error: "Freezer not initialized in frame." };
        }
        return await window.__languageEngineFreezeDom(freezeOpts);
      },
      args: [{}],
      world: "MAIN",
    });

    for (const item of framePass || []) {
      const result = item && item.result;
      if (!result || !result.ok || result.skippedTop || !result.result) continue;
      const capture = result.result;
      if (!capture.html || !capture.url) continue;
      if (!frameSnapshotsByUrl[capture.url]) frameSnapshotsByUrl[capture.url] = [];
      frameSnapshotsByUrl[capture.url].push({ html: capture.html, url: capture.url });
    }
  } catch (_) {
    // Frame capture is best-effort; the top document capture still proceeds.
  }

  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id, allFrames: false },
    func: async (freezeOpts) => {
      if (typeof window.__languageEngineFreezeDom !== "function") {
        return { ok: false, error: "Freezer not initialized in page." };
      }
      return await window.__languageEngineFreezeDom(freezeOpts);
    },
    args: [{ frameSnapshotsByUrl }],
    world: "MAIN",
  });

  const result = results && results[0] && results[0].result;
  if (!result || !result.ok) {
    const err = (result && result.error) || "Capture failed in page context.";
    throw new Error(err);
  }
  return { tab, capture: result.result };
}

// Chrome's chrome.downloads API rejects filenames that contain path
// separators, control chars, reserved Windows names, leading dots, trailing
// dots/spaces, or that exceed 255 bytes when UTF-8 encoded. Right-to-left
// scripts (Persian, Arabic, Hebrew) routinely include zero-width joiners and
// bidi control marks that also cause "Invalid filename" rejections.
function _safeFilename(title, url) {
  let base = _sanitizeFilenameBase(title);
  if (!base) {
    try {
      const u = new URL(url || "");
      base = _sanitizeFilenameBase(u.hostname + u.pathname.replace(/\/+$/, ""));
    } catch (_) { /* ignore */ }
  }
  if (!base) base = "captured-page";
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  // Reserve room for "_" + stamp + ".html" (≈ 26 bytes ASCII).
  const suffix = "_" + stamp + ".html";
  base = _truncateUtf8(base, 200 - suffix.length);
  if (!base) base = "captured-page";
  return base + suffix;
}

function _sanitizeFilenameBase(raw) {
  let s = String(raw == null ? "" : raw);
  // Strip bidi controls, zero-width chars, BOM, ideographic spaces.
  s = s.replace(/[\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFEFF\u3000]/g, "");
  // Replace path separators and chars Windows forbids with underscore.
  s = s.replace(/[\\/:*?"<>|]+/g, "_");
  // Collapse runs of whitespace into a single underscore.
  s = s.replace(/\s+/g, "_");
  // Strip leading dots (hidden file on *nix; rejected by Chrome) and any
  // trailing dots/spaces (rejected on Windows).
  s = s.replace(/^\.+/, "").replace(/[. ]+$/, "");
  // Defuse Windows reserved device names.
  if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.|$)/i.test(s)) {
    s = "_" + s;
  }
  return s.trim();
}

function _truncateUtf8(s, maxBytes) {
  if (!s) return s;
  // TextEncoder is available in MV3 service workers.
  const enc = new TextEncoder();
  const encoded = enc.encode(s);
  if (encoded.length <= maxBytes) return s;
  // Trim characters off the end until we fit. Decoding a partial cut would
  // yield replacement chars, so step character-by-character instead.
  let out = s;
  while (out.length && enc.encode(out).length > maxBytes) {
    out = out.slice(0, -1);
  }
  return out.replace(/[. ]+$/, "");
}

function _arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer || new ArrayBuffer(0));
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode.apply(null, chunk);
  }
  return btoa(binary);
}

async function _fetchResourceForPage(msg) {
  const url = String((msg && msg.url) || "");
  const responseType = (msg && msg.responseType) || "dataUrl";
  if (!/^(https?:|data:)/i.test(url)) {
    return { ok: false, error: "Unsupported resource URL." };
  }

  let lastError = "";
  for (const credentials of ["include", "omit"]) {
    try {
      const resp = await fetch(url, { credentials, redirect: "follow" });
      if (!resp || !resp.ok) {
        lastError = "Fetch failed" + (resp ? ": HTTP " + resp.status : ".");
        continue;
      }
      const contentType = resp.headers.get("content-type") || "";
      if (responseType === "text") {
        return { ok: true, text: await resp.text(), contentType };
      }
      const buffer = await resp.arrayBuffer();
      return {
        ok: true,
        dataUrl: "data:" + (contentType || "application/octet-stream") + ";base64," + _arrayBufferToBase64(buffer),
        contentType,
      };
    } catch (e) {
      lastError = (e && e.message) || String(e);
    }
  }
  return { ok: false, error: lastError || "Fetch failed." };
}

async function _downloadHtml(capture) {
  // Service workers can't use URL.createObjectURL on Blobs in MV3; use a data URL instead.
  const utf8 = unescape(encodeURIComponent(capture.html));
  const b64 = btoa(utf8);
  const dataUrl = "data:text/html;base64," + b64;
  const filename = _safeFilename(capture.title, capture.url);
  const downloadId = await chrome.downloads.download({
    url: dataUrl,
    filename,
  });
  return { downloadId, filename };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      if (msg && msg.type === "le.resource.fetch") {
        sendResponse(await _fetchResourceForPage(msg));
        return;
      }
      if (msg && msg.type === "le.capture.download") {
        const { capture } = await _captureActiveTab();
        const dl = await _downloadHtml(capture);
        sendResponse({
          ok: true,
          downloadId: dl.downloadId,
          filename: dl.filename,
          bytes: capture.bytes,
          title: capture.title,
          sourceUrl: capture.url,
        });
        return;
      }
      sendResponse({ ok: false, error: "Unknown message type." });
    } catch (e) {
      sendResponse({ ok: false, error: (e && e.message) || String(e) });
    }
  })();
  return true; // keep the channel open for async sendResponse
});
