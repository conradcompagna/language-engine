import { parseHtmlString } from "./html.js";

function basicMarkdown(md) {
  const lines = md.replace(/\r\n?/g, "\n").split("\n");
  return lines.map(line => {
    if (/^#{1,6}\s+/.test(line)) {
      const level = line.match(/^#+/)[0].length;
      return `<h${level}>${line.replace(/^#{1,6}\s+/, "")}</h${level}>`;
    }
    if (!line.trim()) return "";
    return `<p>${line}</p>`;
  }).join("\n");
}

export async function parseMarkdownFile(file) {
  const md = await file.text();
  const html = globalThis.marked?.parse ? globalThis.marked.parse(md) : basicMarkdown(md);
  const doc = parseHtmlString(html, { title: file.name, fileName: file.name });
  doc.sourceType = "markdown";
  doc.metadata.format = "Markdown";
  doc.metadata.parser = globalThis.marked?.parse ? "marked + HTML adapter" : "basic markdown adapter";
  return doc;
}
