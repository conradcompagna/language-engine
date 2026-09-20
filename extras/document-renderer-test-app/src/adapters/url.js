import { parseHtmlString } from "./html.js";

function assertHttpUrl(value) {
  let parsed;
  try {
    parsed = new URL(String(value || "").trim());
  } catch {
    throw new Error("Enter a valid http:// or https:// URL.");
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("Only http:// and https:// URLs are supported.");
  }
  return parsed.toString();
}

function contentTypeLooksHtml(contentType = "") {
  return /text\/html|application\/xhtml\+xml|application\/xml|text\/xml/i.test(contentType);
}

function titleFromHtml(html, fallbackUrl) {
  const m = String(html || "").match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const raw = m ? m[1].replace(/\s+/g, " ").trim() : "";
  if (raw) return raw.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
  try { return new URL(fallbackUrl).hostname; } catch { return "URL import"; }
}

function absolutizeUrl(rawValue, baseUrl) {
  if (!rawValue || /^(data:|blob:|mailto:|tel:|javascript:)/i.test(rawValue)) return rawValue;
  try { return new URL(rawValue, baseUrl).toString(); } catch { return rawValue; }
}

function absolutizeSrcset(value, baseUrl) {
  return String(value || "")
    .split(",")
    .map(part => {
      const trimmed = part.trim();
      if (!trimmed) return trimmed;
      const pieces = trimmed.split(/\s+/);
      pieces[0] = absolutizeUrl(pieces[0], baseUrl);
      return pieces.join(" ");
    })
    .join(", ");
}

export function normalizeRemoteHtml(html, baseUrl) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(String(html || ""), "text/html");

  // Drop code and hidden viewer sludge before canonicalization.
  doc.querySelectorAll("script, noscript, iframe, object, embed, style").forEach(el => el.remove());
  doc.querySelectorAll("[hidden], [aria-hidden='true']").forEach(el => el.remove());

  for (const el of Array.from(doc.querySelectorAll("[src], [href], [poster], [srcset]"))) {
    if (el.hasAttribute("src")) el.setAttribute("src", absolutizeUrl(el.getAttribute("src"), baseUrl));
    if (el.hasAttribute("href")) el.setAttribute("href", absolutizeUrl(el.getAttribute("href"), baseUrl));
    if (el.hasAttribute("poster")) el.setAttribute("poster", absolutizeUrl(el.getAttribute("poster"), baseUrl));
    if (el.hasAttribute("srcset")) el.setAttribute("srcset", absolutizeSrcset(el.getAttribute("srcset"), baseUrl));
  }

  const base = doc.createElement("base");
  base.href = baseUrl;
  doc.head.prepend(base);
  return "<!doctype html>\n" + doc.documentElement.outerHTML;
}

async function fetchThroughLocalProxy(url) {
  const response = await fetch(`/api/fetch-url?url=${encodeURIComponent(url)}`);
  if (!response.ok) {
    const message = await response.text().catch(() => "");
    throw new Error(message || `URL fetch failed with HTTP ${response.status}.`);
  }
  return response.json();
}

async function fetchDirect(url) {
  const response = await fetch(url, { mode: "cors" });
  if (!response.ok) throw new Error(`URL fetch failed with HTTP ${response.status}.`);
  const contentType = response.headers.get("content-type") || "";
  return { url, finalUrl: response.url || url, contentType, html: await response.text(), via: "browser-cors" };
}

export async function parseUrl(url) {
  const requestedUrl = assertHttpUrl(url);
  let payload;
  try {
    payload = await fetchThroughLocalProxy(requestedUrl);
  } catch (proxyErr) {
    // Useful when this prototype is hosted without the local Node dev proxy.
    try {
      payload = await fetchDirect(requestedUrl);
    } catch (directErr) {
      throw new Error(`Could not fetch URL. Local proxy says: ${proxyErr.message}. Browser fetch says: ${directErr.message}`);
    }
  }

  const contentType = payload.contentType || "";
  if (contentType && !contentTypeLooksHtml(contentType)) {
    throw new Error(`URL returned ${contentType}; this importer expects HTML/XHTML pages.`);
  }

  const finalUrl = payload.finalUrl || payload.url || requestedUrl;
  const normalizedHtml = normalizeRemoteHtml(payload.html, finalUrl);
  const title = titleFromHtml(normalizedHtml, finalUrl);
  const doc = parseHtmlString(normalizedHtml, { title, fileName: finalUrl });
  doc.sourceType = "url-html";
  doc.fileName = finalUrl;
  doc.metadata = {
    ...doc.metadata,
    format: "Remote HTML",
    requestedUrl,
    finalUrl,
    contentType: contentType || "unknown",
    fetchMode: payload.via || "local proxy",
    sandboxedReaderImport: true,
    linksAreRenderedAsInertMetadata: true,
    textRunsReceiveCanonicalCharacterOffsets: true,
    fetchedAt: new Date().toISOString()
  };
  return doc;
}
