(function(global) {
  'use strict';

  var CLAMP_CLASS = 'dict-popup-clamped';
  var TRUNCATED_CLASS = 'dict-popup-truncated';
  var OVERFLOW_CLASS = 'dict-popup-overflowed';

  function measureOverflow(popupEl) {
    if (!popupEl) return false;
    return (popupEl.scrollHeight - popupEl.clientHeight) > 1;
  }

  function clear(popupEl) {
    if (!popupEl) return;
    popupEl.classList.remove(CLAMP_CLASS, TRUNCATED_CLASS, OVERFLOW_CLASS);
    popupEl.style.removeProperty('--dict-popup-max-height');
    popupEl.style.removeProperty('max-height');
    popupEl.style.removeProperty('overflow-y');
  }

  function apply(popupEl, options) {
    if (!popupEl) {
      return { applied: false, overflowed: false, maxHeightPx: 0 };
    }

    var opts = options || {};
    var ratio = (typeof opts.ratio === 'number' && isFinite(opts.ratio)) ? opts.ratio : 0.5;
    if (ratio <= 0) ratio = 0.5;
    if (ratio > 1) ratio = 1;

    var minHeightPx = (typeof opts.minHeightPx === 'number' && isFinite(opts.minHeightPx))
      ? Math.max(1, Math.floor(opts.minHeightPx))
      : 120;
    var forceTruncatedIndicator = !!opts.forceTruncatedIndicator;

    var viewportHeight = global.innerHeight || document.documentElement.clientHeight || 0;
    if (viewportHeight <= 0) {
      clear(popupEl);
      return { applied: false, overflowed: false, maxHeightPx: 0 };
    }

    var maxHeightPx = Math.max(minHeightPx, Math.floor(viewportHeight * ratio));
    popupEl.classList.add(CLAMP_CLASS);
    popupEl.style.setProperty('--dict-popup-max-height', maxHeightPx + 'px');
    popupEl.style.maxHeight = maxHeightPx + 'px';
    popupEl.style.overflowY = 'hidden';

    // Measure overflow after max-height is applied.
    var overflowed = measureOverflow(popupEl);
    popupEl.classList.toggle(OVERFLOW_CLASS, overflowed);
    popupEl.classList.toggle(TRUNCATED_CLASS, overflowed || forceTruncatedIndicator);

    return {
      applied: true,
      overflowed: overflowed,
      forced: forceTruncatedIndicator,
      maxHeightPx: maxHeightPx
    };
  }

  global.DictPopupClamp = {
    apply: apply,
    clear: clear,
    CLAMP_CLASS: CLAMP_CLASS,
    TRUNCATED_CLASS: TRUNCATED_CLASS,
    OVERFLOW_CLASS: OVERFLOW_CLASS
  };
})(window);
