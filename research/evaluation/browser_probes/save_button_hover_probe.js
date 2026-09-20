/*
DevTools snippet: Save button hover probe

Paste into the browser console on the reader page, then interact with the
entry form. This watches the live Save button node, logs hover-related events,
button replacement, attribute/style changes, and repeated state snapshots.

Usage:
1. Paste the whole file into DevTools Console.
2. Open a create/edit entry form.
3. Change the form until Save is relevant.
4. Hover the Save button.
5. Run `__saveProbe.report()` or inspect `__saveProbe.events`.
*/
(function () {
  if (window.__saveProbe && typeof window.__saveProbe.stop === 'function') {
    try { window.__saveProbe.stop(); } catch (_e) {}
  }

  var state = {
    startedAt: performance.now(),
    events: [],
    observers: [],
    listeners: [],
    hoverTimer: null,
    button: null,
    buttonIdSeed: 0,
    form: null
  };

  function nowMs() {
    return Math.round(performance.now() - state.startedAt);
  }

  function shortNode(node) {
    if (!node) return null;
    var bits = [node.tagName ? node.tagName.toLowerCase() : 'node'];
    if (node.id) bits.push('#' + node.id);
    if (node.classList && node.classList.length) bits.push('.' + Array.from(node.classList).join('.'));
    if (node.dataset && node.dataset.probeId) bits.push('[probe=' + node.dataset.probeId + ']');
    return bits.join('');
  }

  function getButton() {
    return document.getElementById('ef-save-btn') || document.querySelector('.gemini-edit-save-btn');
  }

  function getForm() {
    return document.getElementById('entry-form') || document.querySelector('form.userdict-form');
  }

  function getSnapshot(tag, extra) {
    var btn = getButton();
    var form = getForm();
    var cs = btn ? window.getComputedStyle(btn) : null;
    var rect = btn ? btn.getBoundingClientRect() : null;
    return {
      t: nowMs(),
      tag: tag,
      extra: extra || null,
      button_node: shortNode(btn),
      button_connected: !!(btn && btn.isConnected),
      button_text: btn ? String(btn.textContent || '').trim() : null,
      button_disabled: btn ? !!btn.disabled : null,
      button_hidden_attr: btn ? !!btn.hidden : null,
      button_aria_hidden: btn ? btn.getAttribute('aria-hidden') : null,
      button_class: btn ? btn.className : null,
      button_style: btn ? btn.getAttribute('style') : null,
      display: cs ? cs.display : null,
      visibility: cs ? cs.visibility : null,
      opacity: cs ? cs.opacity : null,
      pointer_events: cs ? cs.pointerEvents : null,
      color: cs ? cs.color : null,
      background: cs ? cs.backgroundColor : null,
      width: rect ? Math.round(rect.width) : null,
      height: rect ? Math.round(rect.height) : null,
      form_node: shortNode(form),
      active_element: shortNode(document.activeElement)
    };
  }

  function log(tag, extra) {
    var snap = getSnapshot(tag, extra);
    state.events.push(snap);
    console.log('[save-probe]', snap);
    return snap;
  }

  function clearHoverTimer() {
    if (state.hoverTimer) {
      clearInterval(state.hoverTimer);
      state.hoverTimer = null;
    }
  }

  function startHoverSampling() {
    clearHoverTimer();
    state.hoverTimer = setInterval(function () {
      log('hover-sample');
    }, 75);
  }

  function addListener(target, type, handler, options) {
    target.addEventListener(type, handler, options);
    state.listeners.push({ target: target, type: type, handler: handler, options: options });
  }

  function bindButton(btn) {
    if (!btn || state.button === btn) return;

    clearHoverTimer();
    state.button = btn;
    state.form = getForm();
    if (!btn.dataset.probeId) {
      state.buttonIdSeed += 1;
      btn.dataset.probeId = 'save-' + state.buttonIdSeed;
    }

    log('button-bound', { button: shortNode(btn) });

    var buttonEvents = [
      'mouseenter', 'mouseleave', 'mouseover', 'mouseout',
      'pointerenter', 'pointerleave', 'pointerover', 'pointerout',
      'focus', 'blur', 'click'
    ];
    buttonEvents.forEach(function (type) {
      addListener(btn, type, function (ev) {
        if (type === 'mouseenter' || type === 'pointerenter') startHoverSampling();
        if (type === 'mouseleave' || type === 'pointerleave') clearHoverTimer();
        log('button-' + type, {
          related: shortNode(ev.relatedTarget),
          target: shortNode(ev.target)
        });
      }, true);
    });

    var attrObserver = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        log('button-attr', {
          name: mutation.attributeName,
          value: btn.getAttribute(mutation.attributeName)
        });
      });
    });
    attrObserver.observe(btn, {
      attributes: true,
      attributeFilter: ['disabled', 'class', 'style', 'hidden', 'aria-hidden']
    });
    state.observers.push(attrObserver);
  }

  function bindForm(form) {
    if (!form || state.form === form) return;
    state.form = form;
    log('form-bound', { form: shortNode(form) });

    ['input', 'change', 'focusin', 'focusout', 'mouseover', 'mouseout'].forEach(function (type) {
      addListener(form, type, function (ev) {
        log('form-' + type, {
          target: shortNode(ev.target),
          name: ev.target && ev.target.name ? ev.target.name : null,
          id: ev.target && ev.target.id ? ev.target.id : null
        });
      }, true);
    });

    var formObserver = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        log('form-mutation', {
          type: mutation.type,
          target: shortNode(mutation.target),
          added: mutation.addedNodes ? mutation.addedNodes.length : 0,
          removed: mutation.removedNodes ? mutation.removedNodes.length : 0,
          attr: mutation.attributeName || null
        });
      });
      var latestButton = getButton();
      if (latestButton && latestButton !== state.button) {
        bindButton(latestButton);
      }
    });
    formObserver.observe(form, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['class', 'style', 'disabled', 'hidden', 'aria-hidden', 'value']
    });
    state.observers.push(formObserver);
  }

  var bodyObserver = new MutationObserver(function () {
    var latestButton = getButton();
    var latestForm = getForm();
    if (latestForm && latestForm !== state.form) bindForm(latestForm);
    if (latestButton && latestButton !== state.button) bindButton(latestButton);
    if (!latestButton && state.button) {
      log('button-missing');
      state.button = null;
    }
  });
  bodyObserver.observe(document.body || document.documentElement, {
    subtree: true,
    childList: true
  });
  state.observers.push(bodyObserver);

  bindForm(getForm());
  bindButton(getButton());
  log('probe-installed');

  window.__saveProbe = {
    state: state,
    events: state.events,
    snapshot: function (tag, extra) {
      return log(tag || 'manual-snapshot', extra || null);
    },
    report: function () {
      var last = state.events.slice(-20);
      console.table(last.map(function (e) {
        return {
          t: e.t,
          tag: e.tag,
          button: e.button_node,
          text: e.button_text,
          disabled: e.button_disabled,
          display: e.display,
          visibility: e.visibility,
          opacity: e.opacity,
          pointer_events: e.pointer_events,
          active: e.active_element
        };
      }));
      return last;
    },
    stop: function () {
      clearHoverTimer();
      state.observers.forEach(function (observer) {
        try { observer.disconnect(); } catch (_e) {}
      });
      state.listeners.forEach(function (item) {
        try { item.target.removeEventListener(item.type, item.handler, item.options); } catch (_e) {}
      });
      console.log('[save-probe] stopped');
    }
  };

  console.log('[save-probe] ready. Hover the Save button, then run __saveProbe.report().');
})();
