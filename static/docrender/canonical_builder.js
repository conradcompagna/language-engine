/* canonical_builder.js
 *
 * Offset-safe builder for CanonicalDocument/Page/Block/Run data.
 *
 * Browser global:
 *   window.CanonicalBuilder
 */
(function(global) {
  'use strict';

  function model() {
    if (!global.CanonicalModel) throw new Error('CanonicalModel must be loaded before CanonicalBuilder');
    return global.CanonicalModel;
  }

  function styleApi() {
    return global.CanonicalStyle || null;
  }

  function str(v) { return v == null ? '' : String(v); }

  function Builder(meta) {
    this.doc = model().makeDocument({ meta: meta || {}, pages: [] });
    this.page = null;
    this.block = null;
    this._lastRun = null;
  }

  Builder.prototype.startPage = function(opts) {
    this.endBlock();
    opts = opts || {};
    var page = model().makePage({
      index: this.doc.pages.length,
      layout: opts.layout || {},
      source: opts.source || {}
    });
    this.doc.pages.push(page);
    this.page = page;
    this.block = null;
    this._lastRun = null;
    return page;
  };

  Builder.prototype.ensurePage = function() {
    if (!this.page) this.startPage();
    return this.page;
  };

  Builder.prototype.startBlock = function(opts) {
    this.ensurePage();
    this.endBlock();
    opts = opts || {};
    var block = model().makeBlock({
      type: opts.type || 'paragraph',
      style: opts.style || {},
      layout: opts.layout || {},
      source: opts.source || {},
      start: this.page.text.length,
      end: this.page.text.length,
      runs: []
    });
    this.page.blocks.push(block);
    this.block = block;
    this._lastRun = null;
    return block;
  };

  Builder.prototype.ensureBlock = function(opts) {
    if (!this.block) this.startBlock(opts || { type: 'paragraph' });
    return this.block;
  };

  Builder.prototype.endBlock = function() {
    if (this.block && this.page) {
      this.block.end = this.page.text.length;
    }
    this.block = null;
    this._lastRun = null;
  };

  Builder.prototype.addRun = function(text, opts) {
    opts = opts || {};
    text = str(text);
    if (!text) return null;
    var page = this.ensurePage();
    var block = this.ensureBlock(opts.block || {});
    var inherited = block.style || {};
    var style = opts.style || {};
    if (styleApi() && styleApi().mergeTextStyle) style = styleApi().mergeTextStyle(inherited, style);
    var canMerge = opts.merge !== false && this._lastRun &&
      (!opts.rects || !opts.rects.length) &&
      (!this._lastRun.rects || !this._lastRun.rects.length) &&
      styleApi() && styleApi().sameTextStyle && styleApi().sameTextStyle(this._lastRun.style, style);
    if (canMerge) {
      this._lastRun.text += text;
      page.text += text;
      this._lastRun.end = page.text.length;
      block.end = page.text.length;
      return this._lastRun;
    }
    var start = page.text.length;
    page.text += text;
    var run = model().makeRun({
      text: text,
      start: start,
      end: page.text.length,
      style: style,
      layout: opts.layout || {},
      rects: opts.rects || [],
      source: opts.source || {}
    });
    block.runs.push(run);
    block.end = page.text.length;
    this._lastRun = run;
    return run;
  };

  Builder.prototype.addSeparator = function(text, opts) {
    opts = opts || {};
    opts.merge = false;
    opts.source = opts.source || { synthetic: true, kind: 'separator' };
    return this.addRun(text == null ? '\n' : text, opts);
  };

  Builder.prototype.endPage = function() {
    this.endBlock();
    if (this.page) model().assertPageInvariant(this.page, 'builder page');
    this.page = null;
    this.block = null;
    this._lastRun = null;
  };

  Builder.prototype.finish = function(opts) {
    opts = opts || {};
    this.endBlock();
    for (var i = 0; i < this.doc.pages.length; i++) {
      if (opts.recompute) model().recomputePageText(this.doc.pages[i]);
      model().assertPageInvariant(this.doc.pages[i], 'finish page ' + i);
    }
    return this.doc;
  };

  function fromText(text, opts) {
    opts = opts || {};
    var b = new Builder(opts.meta || { format: 'text' });
    b.startPage({ layout: opts.layout || {} });
    b.startBlock({ type: opts.blockType || 'plain', style: opts.style || {}, layout: opts.blockLayout || {} });
    b.addRun(text || '', { style: opts.style || {} });
    return b.finish();
  }

  global.CanonicalBuilder = {
    Builder: Builder,
    fromText: fromText
  };
})(window);
