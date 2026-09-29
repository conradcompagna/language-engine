/* ================================================================
   lookup_gate.js — Lookup button + quota enforcement for Language Engine

   This script:
   1. Exposes window.__LE_LOOKUP_ALLOWED = false by default
   2. Adds a "Look Up" button inline in the input area (next to status)
   3. After each lookup (free users only), reads server quota status
      and shows a dismissible daily token-usage toast
   4. When the daily token cap is already spent, turns lookup into upgrade
   ================================================================ */

(function() {
  'use strict';

  window.__LE_LOOKUP_ALLOWED = false;
  window.__LE_USER = null;
  window.__LE_SUBSCRIBED = false;

  // ---- Build the inline Lookup Button ----
  var lookupBtn = document.createElement('button');
  lookupBtn.id = 'leLookupBtn';
  lookupBtn.textContent = 'Look Up';
  lookupBtn.className = 'le-lookup-btn';
  var lookupProgress = document.createElement('span');
  lookupProgress.id = 'leLookupProgress';
  lookupProgress.className = 'le-lookup-progress';
  lookupProgress.setAttribute('aria-live', 'polite');
  lookupProgress.style.display = 'none';
  lookupProgress.style.fontSize = '12px';
  lookupProgress.style.color = '#64748b';
  lookupProgress.style.whiteSpace = 'nowrap';

  // ---- Toast popup (created once, reused) ----
  var toast = document.createElement('div');
  toast.id = 'leQuotaToast';
  toast.className = 'le-quota-toast';
  toast.style.display = 'none';
  var toastMsg = document.createElement('span');
  toastMsg.className = 'le-quota-toast-msg';
  var toastClose = document.createElement('button');
  toastClose.className = 'le-quota-toast-close';
  toastClose.textContent = '\u00d7';
  toastClose.title = 'Dismiss';
  toastClose.addEventListener('click', function() { hideToast(); });
  toast.appendChild(toastMsg);
  toast.appendChild(toastClose);

  var toastTimer = null;

  function showToast(html, persistent) {
    toastMsg.innerHTML = html;
    toast.style.display = 'flex';
    toast.classList.remove('le-quota-toast-exhausted');
    if (toastTimer) clearTimeout(toastTimer);
    if (!persistent) {
      toastTimer = setTimeout(function() { hideToast(); }, 6000);
    }
  }

  function showExhaustedToast(html) {
    toastMsg.innerHTML = html;
    toast.style.display = 'flex';
    toast.classList.add('le-quota-toast-exhausted');
    if (toastTimer) clearTimeout(toastTimer);
    // persistent — no auto-dismiss
  }

  function hideToast() {
    toast.style.display = 'none';
    if (toastTimer) { clearTimeout(toastTimer); toastTimer = null; }
  }

  var lookupBusy = false;
  var lookupWatchdogTimer = null;

  function setLookupProgress(text) {
    var msg = String(text || '').trim();
    lookupProgress.textContent = msg;
    lookupProgress.style.display = msg ? 'inline' : 'none';
  }

  function setLookupBusy(text) {
    lookupBusy = true;
    window.__LE_LOOKUP_ACTIVE = true;
    lookupBtn.disabled = true;
    if (!lookupBtn.classList.contains('le-lookup-upgrade')) {
      lookupBtn.textContent = 'Looking up\u2026';
    }
    setLookupProgress(text || 'Starting lookup');
    if (lookupWatchdogTimer) clearTimeout(lookupWatchdogTimer);
    lookupWatchdogTimer = setTimeout(function() {
      clearLookupBusy();
    }, 300000);
  }

  function clearLookupBusy() {
    lookupBusy = false;
    window.__LE_LOOKUP_ACTIVE = false;
    window.__LE_LOOKUP_ALLOWED = false;
    if (lookupWatchdogTimer) {
      clearTimeout(lookupWatchdogTimer);
      lookupWatchdogTimer = null;
    }
    lookupBtn.disabled = false;
    if (!lookupBtn.classList.contains('le-lookup-upgrade')) {
      lookupBtn.textContent = 'Look Up';
    }
    setLookupProgress('');
  }

  function receiveLookupProgress(text) {
    if (!lookupBusy) return;
    setLookupProgress(text);
  }

  window.__LE_lookupProgress = receiveLookupProgress;
  window.__LE_lookupComplete = function() {
    if (lookupBusy) clearLookupBusy();
  };

  document.addEventListener('le:lookup-progress', function(ev) {
    receiveLookupProgress(ev && ev.detail ? ev.detail.message : '');
  });
  document.addEventListener('le:lookup-complete', function() {
    if (lookupBusy) clearLookupBusy();
  });

  function getResetTimeLabel() {
    // Quota resets at midnight server time (UTC-based from date.today())
    var now = new Date();
    var midnight = new Date(now);
    midnight.setHours(24, 0, 0, 0);
    var diff = midnight - now;
    var hrs = Math.floor(diff / 3600000);
    var mins = Math.floor((diff % 3600000) / 60000);
    if (hrs > 0) return hrs + 'h ' + mins + 'm';
    return mins + 'm';
  }

  function getTokenLimit(data) {
    return Number((data && (data.tokens_limit || data.lookup_tokens_limit || data.limit || data.lookups_limit)) || 1000) || 1000;
  }

  function getTokensUsed(data) {
    return Number((data && (data.tokens_used != null ? data.tokens_used : (data.lookup_tokens_used != null ? data.lookup_tokens_used : data.lookups_used))) || 0) || 0;
  }

  function getTokensRemaining(data) {
    if (!data) return null;
    if (data.tokens_remaining != null) return Number(data.tokens_remaining) || 0;
    if (data.lookup_tokens_remaining != null) return Number(data.lookup_tokens_remaining) || 0;
    if (data.remaining != null) return Number(data.remaining) || 0;
    if (data.lookups_remaining != null) return Number(data.lookups_remaining) || 0;
    return null;
  }

  function tokenUsageHtml(used, limit, exhausted) {
    var usageText = exhausted
      ? 'You\u2019ve used <strong>' + used + '/' + limit + '</strong> tokens today.'
      : '<strong>' + used + '/' + limit + '</strong> tokens used today.';
    return usageText + ' Resets in ' +
      getResetTimeLabel() + '.' +
      '<br><a href="/account" class="le-quota-toast-link">Upgrade for unlimited access</a>';
  }

  function showTokenUsageToast(data) {
    var limit = getTokenLimit(data);
    var used = getTokensUsed(data);
    var remaining = getTokensRemaining(data);
    var exhausted = !!(data && (data.over_limit || data.upgrade)) || used >= limit || remaining === 0;
    if (exhausted) {
      showExhaustedToast(tokenUsageHtml(used, limit, true));
      showUpgradeButton();
      return;
    }
    showToast(tokenUsageHtml(used, limit, false), true);
  }

  function showLookupQuotaFromPayload(payload) {
    if (window.__LE_SUBSCRIBED) return;
    var quota = payload && payload.lookup_quota;
    if (!quota || quota.tokens_limit == null) return;
    showTokenUsageToast(quota);
  }

  function insertElements() {
    var anchor = document.getElementById('leLookupAnchor');
    if (anchor) {
      anchor.appendChild(lookupBtn);
      anchor.appendChild(lookupProgress);
    } else {
      var status = document.getElementById('statusText');
      if (status && status.parentNode) {
        status.parentNode.insertBefore(lookupBtn, status.nextSibling);
        status.parentNode.insertBefore(lookupProgress, lookupBtn.nextSibling);
      }
    }
    document.body.appendChild(toast);
    bindLookupSelectionValidation();
  }

  var lookupSelectionMissingClass = 'lookup-required-missing';

  function getSelectValue(el) {
    return String((el && el.value) || '').trim();
  }

  function clearLookupSelectionHighlights() {
    var languageSelect = document.getElementById('languageSelect');
    var dictSourceSelect = document.getElementById('dictSourceSelect');
    if (languageSelect) languageSelect.classList.remove(lookupSelectionMissingClass);
    if (dictSourceSelect) dictSourceSelect.classList.remove(lookupSelectionMissingClass);
  }

  function validateLookupSelections() {
    var languageSelect = document.getElementById('languageSelect');
    var dictSourceSelect = document.getElementById('dictSourceSelect');
    var missingLanguage = !getSelectValue(languageSelect);
    var missingDictionary = !getSelectValue(dictSourceSelect);
    clearLookupSelectionHighlights();
    if (missingLanguage && languageSelect) languageSelect.classList.add(lookupSelectionMissingClass);
    if (missingDictionary && dictSourceSelect) dictSourceSelect.classList.add(lookupSelectionMissingClass);
    if (missingLanguage && languageSelect && languageSelect.focus) {
      languageSelect.focus();
    } else if (missingDictionary && dictSourceSelect && !dictSourceSelect.disabled && dictSourceSelect.focus) {
      dictSourceSelect.focus();
    }
    return !(missingLanguage || missingDictionary);
  }

  function bindLookupSelectionValidation() {
    var languageSelect = document.getElementById('languageSelect');
    var dictSourceSelect = document.getElementById('dictSourceSelect');
    if (languageSelect && !languageSelect.dataset.lookupValidationBound) {
      languageSelect.dataset.lookupValidationBound = '1';
      languageSelect.addEventListener('change', clearLookupSelectionHighlights);
    }
    if (dictSourceSelect && !dictSourceSelect.dataset.lookupValidationBound) {
      dictSourceSelect.dataset.lookupValidationBound = '1';
      dictSourceSelect.addEventListener('change', function() {
        if (getSelectValue(dictSourceSelect)) {
          dictSourceSelect.classList.remove(lookupSelectionMissingClass);
        }
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', insertElements);
  } else {
    insertElements();
  }

  // ---- Auth + quota check ----
  function checkStatus(callback) {
    var interactive = typeof callback === 'function';
    fetch('/auth/me')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!data.ok || !data.user) {
          window.location.href = '/?login=1';
          return;
        }
        window.__LE_USER = data.user;
        window.__LE_SUBSCRIBED = data.user.is_subscribed;

        fetch('/payments/status')
          .then(function(r) { return r.json(); })
          .then(function(status) {
            if (status.is_subscribed) {
              if (callback) callback(true);
            } else {
              var used = getTokensUsed(status);
              var limit = getTokenLimit(status);
              if (used >= limit) {
                if (callback) callback(false);
                if (interactive) {
                  showTokenUsageToast({
                    tokens_used: used,
                    tokens_limit: limit,
                    tokens_remaining: 0,
                    over_limit: true,
                    upgrade: true
                  });
                }
                showUpgradeButton();
              } else {
                if (callback) callback(true);
              }
            }
          });
      })
      .catch(function() {
        window.location.href = '/?login=1';
      });
  }

  function showUpgradeButton() {
    if (lookupWatchdogTimer) {
      clearTimeout(lookupWatchdogTimer);
      lookupWatchdogTimer = null;
    }
    setLookupProgress('');
    lookupBusy = false;
    window.__LE_LOOKUP_ACTIVE = false;
    window.__LE_LOOKUP_ALLOWED = false;
    lookupBtn.textContent = 'Upgrade';
    lookupBtn.className = 'le-lookup-btn le-lookup-upgrade';
    lookupBtn.disabled = false;
    lookupBtn.onclick = function() { window.location.href = '/account'; };
  }

  function runReaderLookup() {
    if (typeof window.__LE_triggerUpdate !== 'function') {
      clearLookupBusy();
      return;
    }
    receiveLookupProgress('Starting analysis');
    var result = null;
    try {
      result = window.__LE_triggerUpdate();
    } catch (err) {
      console.error(err);
      clearLookupBusy();
      return;
    }
    if (result && typeof result.then === 'function') {
      result.then(function() {
        clearLookupBusy();
      }, function(err) {
        if (err) console.error(err);
        clearLookupBusy();
      });
    } else {
      clearLookupBusy();
    }
  }

  function isMainLookupUrl(input) {
    try {
      var raw = typeof input === 'string' ? input : (input && input.url) || '';
      if (!raw) return false;
      var url = new URL(String(raw), window.location.origin);
      return url.pathname === '/lookup';
    } catch (_e) {
      return false;
    }
  }

  var _leQuotaOrigFetch = window.fetch;
  window.fetch = function(input, init) {
    var promise = _leQuotaOrigFetch.apply(this, arguments);
    if (isMainLookupUrl(input)) {
      promise.then(function(resp) {
        if (!resp || !resp.ok || !resp.clone) return;
        resp.clone().json().then(function(payload) {
          if (payload && payload.ok) showLookupQuotaFromPayload(payload);
        }).catch(function() {});
      }).catch(function() {});
    }
    return promise;
  };

  // ---- Lookup button click handler ----
  lookupBtn.addEventListener('click', function() {
    if (lookupBtn.textContent === 'Upgrade') {
      window.location.href = '/account';
      return;
    }
    bindLookupSelectionValidation();
    if (!validateLookupSelections()) return;

    setLookupBusy('Checking account');
    hideToast();

    checkStatus(function(allowed) {
      if (!allowed) {
        clearLookupBusy();
        return;
      }

      receiveLookupProgress('Checking quota');
      fetch('/lookup/gate', { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (!data.ok) {
            if (data.upgrade) {
              showTokenUsageToast(data);
              showUpgradeButton();
            }
            if (!data.upgrade) clearLookupBusy();
            return;
          }

          window.__LE_LOOKUP_ALLOWED = true;
          receiveLookupProgress('Preparing lookup');

          // Wait for dictionary engine to be ready before triggering lookup
          var dc = window.DictionaryClient;
          if (dc && typeof dc.isEngineReady === 'function' && !dc.isEngineReady()) {
            // Engine still loading — poll until ready, then trigger
            receiveLookupProgress('Loading dictionary');
            var _pollTimeout = null;
            var _pollTimer = setInterval(function() {
              if (dc.isEngineReady()) {
                clearInterval(_pollTimer);
                if (_pollTimeout) clearTimeout(_pollTimeout);
                runReaderLookup();
              }
            }, 200);
            // Safety timeout: give up after 60s
            _pollTimeout = setTimeout(function() {
              clearInterval(_pollTimer);
              clearLookupBusy();
            }, 60000);
          } else if (typeof window.__LE_triggerUpdate === 'function') {
            runReaderLookup();
          } else {
            clearLookupBusy();
          }

          // Free-user token usage is recorded by /lookup; the fetch wrapper
          // reads lookup_quota from that response for the toast.

        })
        .catch(function() {
          clearLookupBusy();
        });
    });
  });

  // Initial status check (silent for subscribed users)
  checkStatus();

})();
