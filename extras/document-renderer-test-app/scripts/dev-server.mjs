import http from "node:http";
import { createReadStream, existsSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const port = Number(process.env.PORT || 4173);
const types = new Map([
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".pdf", "application/pdf"],
  [".epub", "application/epub+zip"],
  [".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
]);

function safeResolve(urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0]);
  const rel = decoded === "/" ? "index.html" : decoded.replace(/^\/+/, "");
  const full = path.resolve(root, rel);
  if (!full.startsWith(root)) return null;
  return full;
}

function sendText(res, status, body, headers = {}) {
  res.writeHead(status, { "Content-Type": "text/plain; charset=utf-8", ...headers });
  res.end(body);
}

async function fetchUrlForImport(req, res) {
  const current = new URL(req.url || "/", `http://localhost:${port}`);
  const rawUrl = current.searchParams.get("url") || "";
  let target;
  try {
    target = new URL(rawUrl);
  } catch {
    sendText(res, 400, "Invalid URL.");
    return;
  }
  if (!["http:", "https:"].includes(target.protocol)) {
    sendText(res, 400, "Only http:// and https:// URLs are supported.");
    return;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const upstream = await fetch(target.toString(), {
      redirect: "follow",
      signal: controller.signal,
      headers: {
        "user-agent": "CanonicalDocumentRendererPrototype/0.2 (+local-dev)",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.8,text/xml;q=0.8,*/*;q=0.5"
      }
    });
    const contentType = upstream.headers.get("content-type") || "";
    if (!upstream.ok) {
      sendText(res, upstream.status, `Remote server returned HTTP ${upstream.status}.`);
      return;
    }
    if (contentType && !/text\/html|application\/xhtml\+xml|application\/xml|text\/xml/i.test(contentType)) {
      sendText(res, 415, `Remote URL returned ${contentType}; expected HTML/XHTML.`);
      return;
    }

    const html = await upstream.text();
    if (Buffer.byteLength(html, "utf8") > 8 * 1024 * 1024) {
      sendText(res, 413, "Remote HTML is larger than 8 MB; refusing in prototype.");
      return;
    }

    res.writeHead(200, {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*"
    });
    res.end(JSON.stringify({
      url: target.toString(),
      finalUrl: upstream.url || target.toString(),
      contentType,
      html,
      via: "local-dev-proxy"
    }));
  } catch (err) {
    sendText(res, 502, err.name === "AbortError" ? "URL fetch timed out." : (err.message || String(err)));
  } finally {
    clearTimeout(timer);
  }
}

const server = http.createServer(async (req, res) => {
  if ((req.url || "").startsWith("/api/fetch-url")) {
    await fetchUrlForImport(req, res);
    return;
  }

  const full = safeResolve(req.url || "/");
  if (!full) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }
  let target = full;
  if (existsSync(target) && statSync(target).isDirectory()) target = path.join(target, "index.html");
  if (!existsSync(target)) {
    res.writeHead(404);
    res.end("Not found");
    return;
  }
  const ext = path.extname(target).toLowerCase();
  res.writeHead(200, { "Content-Type": types.get(ext) || "application/octet-stream" });
  createReadStream(target).pipe(res);
});

server.listen(port, () => {
  console.log(`Canonical Document Renderer running at http://localhost:${port}`);
  console.log(`URL import proxy active at http://localhost:${port}/api/fetch-url?url=...`);
});
