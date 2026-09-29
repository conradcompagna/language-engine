import { createSection, finalizeCanonicalDocument } from "../canonical.js";
import { htmlStringToSections } from "./html.js";

function xmlText(doc, selector) {
  return doc.querySelector(selector)?.textContent?.trim() || "";
}

function dirname(path) {
  const idx = path.lastIndexOf("/");
  return idx === -1 ? "" : path.slice(0, idx + 1);
}

function joinPath(base, relative) {
  if (!base) return relative;
  if (/^[a-z]+:/i.test(relative)) return relative;
  const stack = base.split("/").filter(Boolean);
  for (const part of relative.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") stack.pop();
    else stack.push(part);
  }
  return stack.join("/");
}

function parseXml(text) {
  return new DOMParser().parseFromString(text, "application/xml");
}

export async function parseEpubFile(file) {
  if (!globalThis.JSZip) throw new Error("EPUB support needs JSZip. Open the app through index.html so CDN dependencies load.");
  const zip = await globalThis.JSZip.loadAsync(await file.arrayBuffer());
  const containerXml = await zip.file("META-INF/container.xml")?.async("text");
  if (!containerXml) throw new Error("Invalid EPUB: missing META-INF/container.xml");
  const container = parseXml(containerXml);
  const opfPath = container.querySelector("rootfile")?.getAttribute("full-path");
  if (!opfPath) throw new Error("Invalid EPUB: missing OPF rootfile");
  const opfText = await zip.file(opfPath)?.async("text");
  if (!opfText) throw new Error(`Invalid EPUB: missing ${opfPath}`);
  const opf = parseXml(opfText);
  const base = dirname(opfPath);

  const metadata = {
    title: xmlText(opf, "metadata > title") || xmlText(opf, "dc\\:title") || file.name,
    creator: xmlText(opf, "metadata > creator") || xmlText(opf, "dc\\:creator"),
    language: xmlText(opf, "metadata > language") || xmlText(opf, "dc\\:language"),
    identifier: xmlText(opf, "metadata > identifier") || xmlText(opf, "dc\\:identifier"),
    format: "EPUB",
    parser: "JSZip + OPF spine + HTML adapter",
    opfPath
  };

  const manifest = new Map();
  for (const item of Array.from(opf.querySelectorAll("manifest > item"))) {
    manifest.set(item.getAttribute("id"), {
      href: item.getAttribute("href"),
      mediaType: item.getAttribute("media-type"),
      properties: item.getAttribute("properties") || ""
    });
  }

  const sections = [];
  for (const itemref of Array.from(opf.querySelectorAll("spine > itemref"))) {
    const idref = itemref.getAttribute("idref");
    const item = manifest.get(idref);
    if (!item || !/html|xhtml/i.test(item.mediaType || item.href)) continue;
    const path = joinPath(base, item.href);
    const raw = await zip.file(path)?.async("text");
    if (!raw) continue;
    const parsedSections = htmlStringToSections(raw, { title: item.href, sourcePath: path });
    for (const section of parsedSections) {
      sections.push(createSection({
        title: section.title || item.href,
        sourcePath: path,
        blocks: section.blocks,
        metadata: { idref, mediaType: item.mediaType }
      }));
    }
  }

  return finalizeCanonicalDocument({
    title: metadata.title || file.name,
    sourceType: "epub",
    fileName: file.name,
    metadata,
    sections
  });
}
