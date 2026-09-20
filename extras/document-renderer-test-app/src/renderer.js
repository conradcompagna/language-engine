import { sectionToHtml, getDocumentStats } from "./canonical.js";
import { tokensForRange } from "./annotator.js";

export const DEFAULT_RENDER_OPTIONS = {
  pageWidth: 760,
  pageHeight: 980,
  pageGap: 48,
  marginTop: 58,
  marginRight: 66,
  marginBottom: 66,
  marginLeft: 66,
  fontFamily: "Georgia, 'Times New Roman', serif",
  fontSize: 18,
  lineHeight: 1.62,
  direction: "ltr",
  writingMode: "horizontal-tb"
};

function sleepFrame() {
  return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}

function pageMetrics(options) {
  const pageWidth = Math.round(Number(options.pageWidth) || DEFAULT_RENDER_OPTIONS.pageWidth);
  const pageHeight = Math.round(Number(options.pageHeight) || DEFAULT_RENDER_OPTIONS.pageHeight);
  const marginTop = Math.round(Number(options.marginTop) || 0);
  const marginRight = Math.round(Number(options.marginRight) || 0);
  const marginBottom = Math.round(Number(options.marginBottom) || 0);
  const marginLeft = Math.round(Number(options.marginLeft) || 0);
  const pageGap = Math.round(Number(options.pageGap) || 0);
  const contentWidth = Math.max(120, pageWidth - marginLeft - marginRight);
  const contentHeight = Math.max(120, pageHeight - marginTop - marginBottom);

  // The actual CSS columns are content columns, not whole-page columns. The visible
  // page is a real page box around that content column. This prevents the classic
  // drift bug where the app jumps by full page width while the browser laid out a
  // narrower content column because padding/margins were included in the flow.
  const columnGap = marginLeft + marginRight + pageGap;
  const columnStep = contentWidth + columnGap;
  return { pageWidth, pageHeight, pageGap, marginTop, marginRight, marginBottom, marginLeft, contentWidth, contentHeight, columnGap, columnStep };
}

function collectTextNodes(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      return node.nodeValue?.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
  });
  const nodes = [];
  let n;
  while ((n = walker.nextNode())) nodes.push(n);
  return nodes;
}

function collectAllRenderableTextNodes(root) {
  const skipTags = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "IFRAME", "OBJECT", "EMBED", "CANVAS", "SVG"]);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      if (skipTags.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
      if (parent.closest?.(".reader-text-run")) return NodeFilter.FILTER_REJECT;
      return node.nodeValue ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
  });
  const nodes = [];
  let n;
  while ((n = walker.nextNode())) nodes.push(n);
  return nodes;
}

function nearestBlock(node) {
  let el = node.parentElement;
  while (el && !el.dataset?.blockId) el = el.parentElement;
  return el;
}

function nearestTextRun(node) {
  let el = node.parentElement;
  while (el && !el.classList?.contains("reader-text-run")) el = el.parentElement;
  return el;
}

function removeDangerousAttributes(el) {
  for (const attr of Array.from(el.attributes || [])) {
    const name = attr.name.toLowerCase();
    const value = String(attr.value || "");
    if (name.startsWith("on")) el.removeAttribute(attr.name);
    if ((name === "href" || name === "src") && /^javascript:/i.test(value.trim())) el.removeAttribute(attr.name);
  }
}

function neutralizeInteractiveContent(root) {
  root.querySelectorAll("script, noscript, iframe, object, embed").forEach(el => el.remove());
  root.querySelectorAll("*").forEach(removeDangerousAttributes);

  root.querySelectorAll("a").forEach(anchor => {
    const span = document.createElement("span");
    span.className = ["reader-inert-link", anchor.className].filter(Boolean).join(" ");
    const href = anchor.getAttribute("href") || "";
    if (href) {
      span.dataset.href = href;
      span.title = "Link disabled in reader sandbox: " + href;
    }
    const style = anchor.getAttribute("style");
    if (style) span.setAttribute("style", style);
    span.setAttribute("role", "link");
    span.setAttribute("aria-disabled", "true");
    while (anchor.firstChild) span.appendChild(anchor.firstChild);
    anchor.replaceWith(span);
  });

  root.querySelectorAll("form").forEach(form => {
    const wrapper = document.createElement("div");
    wrapper.className = "reader-inert-form";
    wrapper.textContent = form.textContent?.trim() || "[form removed]";
    form.replaceWith(wrapper);
  });

  root.querySelectorAll("button, input, select, textarea").forEach(control => {
    const span = document.createElement("span");
    span.className = "reader-inert-control";
    span.textContent = control.value || control.textContent || control.getAttribute("aria-label") || "";
    control.replaceWith(span);
  });
}

function makeTextRun(text, canonicalStart, canonicalEnd) {
  const span = document.createElement("span");
  span.className = "reader-text-run";
  span.dataset.canonicalStart = String(canonicalStart);
  span.dataset.canonicalEnd = String(canonicalEnd);
  span.textContent = text;
  return span;
}

function wrapTextNodesWithCanonicalOffsets(root, doc) {
  const blocks = Array.from(root.querySelectorAll("[data-block-id][data-canonical-start][data-canonical-end]"));
  for (const blockEl of blocks) {
    const blockStart = Number(blockEl.dataset.canonicalStart || 0);
    const blockEnd = Number(blockEl.dataset.canonicalEnd || blockStart);
    const blockText = doc.canonicalText.slice(blockStart, blockEnd);
    let cursor = 0;

    for (const node of collectAllRenderableTextNodes(blockEl)) {
      const raw = node.nodeValue || "";
      if (!raw) continue;
      const fragment = document.createDocumentFragment();
      const parts = raw.match(/\s+|\S+/g) || [raw];

      for (const part of parts) {
        if (!part) continue;
        const exactAtCursor = blockText.startsWith(part, cursor) ? cursor : -1;
        const found = exactAtCursor >= 0 ? exactAtCursor : blockText.indexOf(part, cursor);

        if (found >= 0) {
          fragment.appendChild(makeTextRun(part, blockStart + found, blockStart + found + part.length));
          cursor = found + part.length;
        } else if (/^\s+$/.test(part)) {
          fragment.appendChild(document.createTextNode(part));
        } else {
          const unknown = document.createElement("span");
          unknown.className = "reader-text-run reader-text-unmapped";
          unknown.dataset.canonicalStart = "-1";
          unknown.dataset.canonicalEnd = "-1";
          unknown.textContent = part;
          fragment.appendChild(unknown);
        }
      }
      node.replaceWith(fragment);
    }
  }
}

function prepareReaderFlow(flow, doc) {
  neutralizeInteractiveContent(flow);
  wrapTextNodesWithCanonicalOffsets(flow, doc);
  flow.addEventListener("click", event => {
    const inert = event.target?.closest?.(".reader-inert-link");
    if (inert) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);
}

function flowTextRange(flow) {
  const range = document.createRange();
  range.selectNodeContents(flow);
  return range;
}

function measuredPageCount(flow, metrics) {
  // For N content columns: scrollWidth ~= N*contentWidth + (N-1)*columnGap.
  // So N ~= (scrollWidth + columnGap) / columnStep. We keep this integer and do
  // not use it as a transform distance. The transform distance is the explicit
  // columnStep used by CSS itself.
  const raw = (flow.scrollWidth + metrics.columnGap) / metrics.columnStep;
  return Math.max(1, Math.round(raw));
}

function collectWordBoxes(flow, metrics) {
  const flowRect = flow.getBoundingClientRect();
  const nodes = collectTextNodes(flow);
  const perBlockOffsets = new Map();
  const words = [];

  for (const node of nodes) {
    const block = nearestBlock(node);
    if (!block) continue;
    const blockId = block.dataset.blockId;
    const blockStart = Number(block.dataset.canonicalStart || 0);
    const seen = perBlockOffsets.get(blockId) || 0;
    const run = nearestTextRun(node);
    const runStart = Number(run?.dataset?.canonicalStart ?? NaN);
    const textBase = Number.isFinite(runStart) && runStart >= 0 ? runStart : blockStart + seen;
    const text = node.nodeValue || "";
    const re = /\S+/g;
    let m;
    while ((m = re.exec(text))) {
      const range = document.createRange();
      range.setStart(node, m.index);
      range.setEnd(node, m.index + m[0].length);
      const rect = Array.from(range.getClientRects()).find(r => r.width > 0 && r.height > 0);
      range.detach();
      if (!rect) continue;

      const xInFlow = rect.left - flowRect.left;
      const yInFlow = rect.top - flowRect.top;
      const pageIndex = Math.max(0, Math.floor((xInFlow + 0.5) / metrics.columnStep));
      words.push({
        text: m[0],
        canonicalStart: textBase + m.index,
        canonicalEnd: textBase + m.index + m[0].length,
        pageIndex,
        x: metrics.marginLeft + xInFlow - pageIndex * metrics.columnStep,
        y: metrics.marginTop + yInFlow,
        width: rect.width,
        height: rect.height,
        blockId
      });
    }
    perBlockOffsets.set(blockId, seen + text.length);
  }
  return words;
}

function rangesFromWordBoxes(words, pageCount, fallbackStart, fallbackEnd) {
  const pages = Array.from({ length: pageCount }, (_, pageIndex) => ({
    pageIndex,
    canonicalStart: Infinity,
    canonicalEnd: -Infinity,
    words: []
  }));
  for (const word of words) {
    const page = pages[word.pageIndex];
    if (!page) continue;
    page.words.push(word);
    page.canonicalStart = Math.min(page.canonicalStart, word.canonicalStart);
    page.canonicalEnd = Math.max(page.canonicalEnd, word.canonicalEnd);
  }

  let last = fallbackStart;
  for (const page of pages) {
    if (page.canonicalStart === Infinity) {
      page.canonicalStart = last;
      page.canonicalEnd = last;
    } else {
      page.canonicalStart = Math.max(fallbackStart, page.canonicalStart);
      page.canonicalEnd = Math.min(fallbackEnd, page.canonicalEnd);
      last = page.canonicalEnd;
    }
  }
  return pages;
}

function applyFlowGeometry(flow, metrics, options) {
  flow.dir = options.direction || "ltr";
  flow.style.width = `${metrics.contentWidth}px`;
  flow.style.height = `${metrics.contentHeight}px`;
  flow.style.columnWidth = `${metrics.contentWidth}px`;
  flow.style.columnGap = `${metrics.columnGap}px`;
  flow.style.padding = "0";
  flow.style.fontFamily = options.fontFamily;
  flow.style.fontSize = `${options.fontSize}px`;
  flow.style.lineHeight = options.lineHeight;
  flow.style.writingMode = options.writingMode || "horizontal-tb";
}

export async function renderReflowableSection({ container, doc, sectionIndex = 0, tokens = [], options = DEFAULT_RENDER_OPTIONS }) {
  const section = doc.sections[sectionIndex];
  if (!section) throw new Error("No section to render");

  const metrics = pageMetrics(options);
  container.innerHTML = "";
  container.classList.add("isolated-page-host");

  // Hidden measuring document. The flow itself is the content box, not the page
  // box. This makes CSS's actual column width equal to the measured jump size.
  const measureShell = document.createElement("div");
  measureShell.className = "page-shell measure-shell";
  measureShell.style.width = `${metrics.pageWidth}px`;
  measureShell.style.height = `${metrics.pageHeight}px`;

  const measureContentClip = document.createElement("div");
  measureContentClip.className = "page-content-clip measure-content-clip";
  measureContentClip.style.left = `${metrics.marginLeft}px`;
  measureContentClip.style.top = `${metrics.marginTop}px`;
  measureContentClip.style.width = `${metrics.contentWidth}px`;
  measureContentClip.style.height = `${metrics.contentHeight}px`;

  const flow = document.createElement("div");
  flow.className = "reader-flow measure-flow";
  applyFlowGeometry(flow, metrics, options);
  flow.innerHTML = sectionToHtml(section);
  prepareReaderFlow(flow, doc);

  measureContentClip.appendChild(flow);
  measureShell.appendChild(measureContentClip);
  container.appendChild(measureShell);
  await sleepFrame();

  const pageCountByScroll = measuredPageCount(flow, metrics);
  const wordBoxes = collectWordBoxes(flow, metrics);
  const maxWordPage = wordBoxes.reduce((max, word) => Math.max(max, word.pageIndex), 0);
  const pageCount = Math.max(1, pageCountByScroll, maxWordPage + 1);
  const pageRanges = rangesFromWordBoxes(wordBoxes, pageCount, section.canonicalStart, section.canonicalEnd);
  const pages = pageRanges.map(page => ({
    ...page,
    pageStep: metrics.columnStep,
    columnStep: metrics.columnStep,
    columnGap: metrics.columnGap,
    contentWidth: metrics.contentWidth,
    contentHeight: metrics.contentHeight,
    margins: {
      top: metrics.marginTop,
      right: metrics.marginRight,
      bottom: metrics.marginBottom,
      left: metrics.marginLeft
    },
    sectionId: section.id,
    sectionIndex,
    width: metrics.pageWidth,
    height: metrics.pageHeight,
    text: doc.canonicalText.slice(page.canonicalStart, page.canonicalEnd),
    tokens: tokensForRange(tokens, page.canonicalStart, page.canonicalEnd)
  }));

  // Visible page: one actual page shell containing one clipped content viewport.
  // The cloned flow is translated by the exact content-column step used by CSS.
  const displayShell = document.createElement("div");
  displayShell.className = "page-shell display-page-shell";
  displayShell.style.width = `${metrics.pageWidth}px`;
  displayShell.style.height = `${metrics.pageHeight}px`;
  container.appendChild(displayShell);

  function buildVisiblePage(pageIndex) {
    const surface = document.createElement("div");
    surface.className = "single-page-surface";
    surface.style.width = `${metrics.pageWidth}px`;
    surface.style.height = `${metrics.pageHeight}px`;

    const clip = document.createElement("div");
    clip.className = "page-content-clip single-page-content-clip";
    clip.style.left = `${metrics.marginLeft}px`;
    clip.style.top = `${metrics.marginTop}px`;
    clip.style.width = `${metrics.contentWidth}px`;
    clip.style.height = `${metrics.contentHeight}px`;

    const fragmentFlow = flow.cloneNode(true);
    fragmentFlow.className = "reader-flow page-fragment-flow";
    fragmentFlow.removeAttribute("id");
    applyFlowGeometry(fragmentFlow, metrics, options);
    fragmentFlow.style.position = "absolute";
    fragmentFlow.style.left = "0";
    fragmentFlow.style.top = "0";
    fragmentFlow.style.transition = "none";
    fragmentFlow.style.transform = `translate3d(${-pageIndex * metrics.columnStep}px, 0, 0)`;
    fragmentFlow.dataset.visiblePageIndex = String(pageIndex);

    clip.appendChild(fragmentFlow);
    surface.appendChild(clip);
    return surface;
  }

  function showPage(pageIndex) {
    const safeIndex = Math.max(0, Math.min(pageCount - 1, Number(pageIndex) || 0));
    displayShell.replaceChildren(buildVisiblePage(safeIndex));
  }

  showPage(0);
  return { shell: displayShell, measureShell, flow, pages, pageCount, pageStep: metrics.columnStep, metrics, showPage, section, stats: getDocumentStats(doc) };
}

export function renderFixedLayoutDocument({ container, doc, tokens = [] }) {
  container.innerHTML = "";
  const pages = (doc.fixedLayoutPages || []).map(page => ({
    ...page,
    tokens: tokensForRange(tokens, page.canonicalStart, page.canonicalEnd)
  }));
  const shell = document.createElement("div");
  shell.className = "page-shell fixed-layout-shell";
  container.appendChild(shell);
  function showPage(pageIndex) {
    const page = pages[pageIndex];
    if (!page) return;
    shell.style.width = `${Math.min(900, page.width)}px`;
    shell.style.height = `${Math.min(1100, page.height)}px`;
    shell.innerHTML = page.html;
    const fixed = shell.querySelector(".pdf-fixed-page");
    if (fixed) {
      const scale = Math.min(1, 850 / page.width, 1040 / page.height);
      fixed.style.transform = `scale(${scale})`;
      fixed.style.transformOrigin = "top left";
    }
  }
  showPage(0);
  return { shell, pages, pageCount: pages.length, showPage, stats: getDocumentStats(doc) };
}

export function collectCharacterBoxesForPage(flow, page, options = DEFAULT_RENDER_OPTIONS, limit = 4000) {
  const flowRect = flow.getBoundingClientRect();
  const metrics = page?.columnStep ? {
    columnStep: page.columnStep,
    marginLeft: page.margins?.left || 0,
    marginTop: page.margins?.top || 0
  } : pageMetrics(options);
  const nodes = collectTextNodes(flow);
  const perBlockOffsets = new Map();
  const chars = [];
  for (const node of nodes) {
    const block = nearestBlock(node);
    if (!block) continue;
    const blockId = block.dataset.blockId;
    const blockStart = Number(block.dataset.canonicalStart || 0);
    const seen = perBlockOffsets.get(blockId) || 0;
    const run = nearestTextRun(node);
    const runStart = Number(run?.dataset?.canonicalStart ?? NaN);
    const textBase = Number.isFinite(runStart) && runStart >= 0 ? runStart : blockStart + seen;
    const text = node.nodeValue || "";
    for (let i = 0; i < text.length; i++) {
      const canonicalIndex = textBase + i;
      if (canonicalIndex < page.canonicalStart || canonicalIndex >= page.canonicalEnd) continue;
      if (!text[i].trim()) continue;
      const range = document.createRange();
      range.setStart(node, i);
      range.setEnd(node, i + 1);
      const rect = Array.from(range.getClientRects()).find(r => r.width >= 0 && r.height > 0);
      range.detach();
      if (!rect) continue;
      const xInFlow = rect.left - flowRect.left;
      const pageIndex = Math.max(0, Math.floor((xInFlow + 0.5) / metrics.columnStep));
      if (pageIndex !== page.pageIndex) continue;
      chars.push({
        char: text[i], canonicalIndex,
        x: metrics.marginLeft + xInFlow - pageIndex * metrics.columnStep,
        y: metrics.marginTop + rect.top - flowRect.top,
        width: rect.width,
        height: rect.height
      });
      if (chars.length >= limit) return chars;
    }
    perBlockOffsets.set(blockId, seen + text.length);
  }
  return chars;
}
