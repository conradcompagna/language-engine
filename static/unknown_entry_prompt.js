/* Paid-entry prompt shown when a free user opens an unknown token. */
(function () {
  'use strict';
  var userTier = 'free';
  // Fetch user tier on load
  fetch('/auth/me')
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.ok && d.user) {
        userTier = d.user.tier || 'free';
      }
    })
    .catch(function () {});


  function isPaid() { return userTier === 'basic' || userTier === 'pro'; }
  window.UnknownEntryPrompt = {};
  window.UnknownEntryPrompt.renderUpgradeNudge = function (container) {
    if (isPaid()) return;
    var nudge = document.createElement('div');
    nudge.className = 'le-upgrade-nudge';
    nudge.innerHTML = ''
      + '<div class="nudge-icon">&#x2728;</div>'
      + '<div class="nudge-text">Upgrade to create Gemini synthetic entries for unknown terms</div>'
      + '<a href="/account" class="nudge-link">Upgrade</a>';
    container.appendChild(nudge);
  };

})();
