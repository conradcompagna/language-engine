import { createSection, finalizeCanonicalDocument } from "../canonical.js";
import { htmlStringToSections } from "./html.js";

function xmlText(doc, selector) {
  return doc.querySelector(selector)?.textContent?.trim() || "";
}

async function extractDocxMetadata(arrayBuffer, fileName) {
  const metadata = { format: "DOCX", parser: "docx-preview preferred, mammoth fallback" };
  if (!globalThis.JSZip) return metadata;
  try {
    const zip = await globalThis.JSZip.loadAsync(arrayBuffer.slice(0));
    const core = await zip.file("docProps/core.xml")?.async("text");
    if (core) {
      const xml = new DOMParser().parseFromString(core, "application/xml");
      metadata.title = xmlText(xml, "title") || xmlText(xml, "dc\\:title");
      metadata.creator = xmlText(xml, "creator") || xmlText(xml, "dc\\:creator");
      metadata.subject = xmlText(xml, "subject") || xmlText(xml, "dc\\:subject");
      metadata.description = xmlText(xml, "description") || xmlText(xml, "dc\\:description");
      metadata.created = xmlText(xml, "created") || xmlText(xml, "dcterms\\:created");
      metadata.modified = xmlText(xml, "modified") || xmlText(xml, "dcterms\\:modified");
    }
    const app = await zip.file("docProps/app.xml")?.async("text");
    if (app) {
      const xml = new DOMParser().parseFromString(app, "application/xml");
      metadata.application = xmlText(xml, "Application");
      metadata.pages = xmlText(xml, "Pages");
      metadata.words = xmlText(xml, "Words");
    }
  } catch (err) {
    metadata.metadataWarning = String(err.message || err);
  }
  if (!metadata.title) metadata.title = fileName;
  return metadata;
}

async function renderWithDocxPreview(arrayBuffer) {
  if (!globalThis.docx?.renderAsync) return null;
  const container = document.createElement("div");
  container.className = "docx-preview-source";
  container.style.position = "fixed";
  container.style.left = "-100000px";
  container.style.top = "0";
  container.style.width = "900px";
  document.body.appendChild(container);
  try {
    await globalThis.docx.renderAsync(arrayBuffer.slice(0), container, undefined, {
      className: "docx",
      inWrapper: false,
      ignoreWidth: false,
      ignoreHeight: false,
      ignoreFonts: false,
      breakPages: true,
      renderHeaders: true,
      renderFooters: true,
      renderFootnotes: true,
      renderEndnotes: true
    });
    const html = container.innerHTML;
    container.remove();
    return html;
  } catch (err) {
    container.remove();
    console.warn("docx-preview failed; falling back to mammoth", err);
    return null;
  }
}

async function renderWithMammoth(arrayBuffer) {
  if (!globalThis.mammoth?.convertToHtml) throw new Error("DOCX support needs docx-preview or mammoth loaded from index.html.");
  const result = await globalThis.mammoth.convertToHtml({ arrayBuffer }, {
    includeDefaultStyleMap: true,
    convertImage: globalThis.mammoth.images.imgElement(async image => ({ src: await image.read("dataUri") }))
  });
  return result.value;
}

export async function parseDocxFile(file) {
  const arrayBuffer = await file.arrayBuffer();
  const metadata = await extractDocxMetadata(arrayBuffer, file.name);
  let html = await renderWithDocxPreview(arrayBuffer);
  metadata.visualRenderer = html ? "docx-preview" : "mammoth";
  if (!html) html = await renderWithMammoth(arrayBuffer);

  const parsedSections = htmlStringToSections(html, { title: metadata.title || file.name, sourcePath: file.name });
  const sections = parsedSections.map((s, index) => createSection({
    title: s.title || `${file.name} section ${index + 1}`,
    sourcePath: file.name,
    blocks: s.blocks,
    metadata: { adapter: metadata.visualRenderer }
  }));

  return finalizeCanonicalDocument({
    title: metadata.title || file.name,
    sourceType: "docx",
    fileName: file.name,
    metadata,
    sections
  });
}
