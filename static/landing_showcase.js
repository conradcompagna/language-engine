(function() {
  'use strict';

  var DATA_URL = '/static/marketing/showcase_payloads.json';
  var samples = [];
  var activeIndex = 0;

  function $(id) {
    return document.getElementById(id);
  }

  function setText(el, value) {
    if (el) el.textContent = String(value || '');
  }

  function getDirection(sample) {
    return String(sample && sample.dir || '').toLowerCase() === 'rtl' ? 'rtl' : 'ltr';
  }

  function setAttribution(sample) {
    var el = $('showcaseAttribution');
    if (!el) return;
    var text = String((sample && (sample.provenance_display || sample.source_title)) || '').trim();
    el.textContent = text ? ('- ' + text) : '';
  }

  function buildTabs() {
    var tabs = $('showcaseTabs');
    if (!tabs) return;
    tabs.innerHTML = '';
    for (var i = 0; i < samples.length; i++) {
      var sample = samples[i] || {};
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'le-live-showcase-tab' + (i === activeIndex ? ' is-active' : '');
      btn.textContent = sample.label || sample.title || sample.lang || ('Sample ' + (i + 1));
      btn.dataset.index = String(i);
      btn.addEventListener('click', function() {
        selectSample(parseInt(this.dataset.index || '0', 10) || 0);
      });
      tabs.appendChild(btn);
    }
  }

  function markActiveTab() {
    var tabs = document.querySelectorAll('.le-live-showcase-tab');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].classList.toggle('is-active', i === activeIndex);
    }
  }

  function selectSample(index) {
    if (!samples.length) return;
    activeIndex = Math.max(0, Math.min(index, samples.length - 1));
    var sample = samples[activeIndex] || {};
    var api = window.LEReaderShowcaseApi;
    var root = $('renderedText');
    var lang = String(sample.lang || '').trim().toLowerCase();

    markActiveTab();
    setAttribution(sample);
    if (root) {
      root.dataset.lang = lang;
      root.lang = lang || '';
      root.dir = getDirection(sample);
      root.innerHTML = '';
    }

    if (!api || typeof api.renderPayload !== 'function') {
      setText(root, 'Showcase runtime unavailable.');
      return;
    }
    if (typeof api.hidePopup === 'function') api.hidePopup();
    api.renderPayload(sample.payload, {
      lang: lang,
      text: sample.text || (sample.payload && (sample.payload.display_text || sample.payload.q)) || '',
      renderedText: root,
      hoverPopupContainer: $('hoverPopupContainer'),
      hoverPopup: $('hoverPopup'),
      grammarPopup: $('grammarPopup'),
      udPopup: $('udPopup'),
      g2pPopup: $('g2pPopup'),
      notePopup: $('notePopup'),
      subsegmentPopupsContainer: $('subsegmentPopupsContainer')
    });
  }

  function initShowcase(data) {
    samples = (data && Array.isArray(data.samples)) ? data.samples : [];
    if (!samples.length) {
      setText($('renderedText'), 'Showcase data unavailable.');
      return;
    }
    buildTabs();
    selectSample(0);

    var frame = document.querySelector('.le-live-showcase-frame');
    if (frame) {
      frame.addEventListener('mouseleave', function() {
        var api = window.LEReaderShowcaseApi;
        if (api && typeof api.hidePopup === 'function') api.hidePopup();
      });
    }
  }

  fetch(DATA_URL)
    .then(function(resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.json();
    })
    .then(initShowcase)
    .catch(function(err) {
      console.error('showcase load failed', err);
      setText($('renderedText'), 'Showcase data unavailable.');
    });
})();
