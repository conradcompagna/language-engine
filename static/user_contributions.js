/**
 * user_contributions.js — Community dictionary entries, annotations, and MT annotation UI.
 *
 * Extends the side panel with:
 *  - User dict entry creation (mirroring TSV structure)
 *  - Annotation creation/editing on tokens
 *  - Community entries display (from other users)
 *  - Synthetic MT entry annotation (pos, extra glosses, alt forms)
 *  - Settings toggles for community visibility
 *
 * Depends on: reader.js (loaded after), auth/me endpoint for tier info.
 */
(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  var userTier = 'free';
  var showOtherEntries = true;
  var showOtherAnnotations = true;

  // Fetch user tier on load
  fetch('/auth/me')
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.ok && d.user) {
        userTier = d.user.tier || 'free';
      }
    })
    .catch(function () {});

  // Load preferences
  try {
    var prefs = JSON.parse(localStorage.getItem('le_community_prefs') || '{}');
    if (prefs.showOtherEntries === false) showOtherEntries = false;
    if (prefs.showOtherAnnotations === false) showOtherAnnotations = false;
  } catch (_e) {}

  function savePrefs() {
    localStorage.setItem('le_community_prefs', JSON.stringify({
      showOtherEntries: showOtherEntries,
      showOtherAnnotations: showOtherAnnotations,
    }));
  }

  function escapeHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function isPaid() { return userTier === 'basic' || userTier === 'pro'; }

  // ---------------------------------------------------------------------------
  // MT synthetic entry annotation UI
  // ---------------------------------------------------------------------------

  /**
   * Render annotation controls for a synthetic (MT) entry in the popup/panel.
   * Called by reader.js when rendering a dict entry with entry.synthetic === true.
   */
  window.UserContributions = window.UserContributions || {};

  window.UserContributions.renderSyntheticAnnotationUI = function () {
    // Legacy Google Translate synthetic-entry annotation path disabled.
  };

  // Old annotation system removed — replaced by entry-level notes in reader_wikt.js + reader.js
  window.UserContributions.renderAnnotationBox = function () {};

  // ---------------------------------------------------------------------------
  // Community entries display
  // ---------------------------------------------------------------------------

  window.UserContributions.renderCommunityEntries = function () {};

  // ---------------------------------------------------------------------------
  // Upgrade nudge for unknown tokens (free users)
  // ---------------------------------------------------------------------------

  window.UserContributions.renderUpgradeNudge = function (container) {
    if (isPaid()) return;
    var nudge = document.createElement('div');
    nudge.className = 'le-upgrade-nudge';
    nudge.innerHTML = ''
      + '<div class="nudge-icon">&#x2728;</div>'
      + '<div class="nudge-text">Upgrade to create Gemini synthetic entries for unknown terms</div>'
      + '<a href="/account" class="nudge-link">Upgrade</a>';
    container.appendChild(nudge);
  };

  // ---------------------------------------------------------------------------
  // Settings toggles (injected into side panel settings menu)
  // ---------------------------------------------------------------------------

  window.UserContributions.injectSettingsToggles = function (menuContainer) {
    void menuContainer;
  };

  // Auto-inject settings into the left menu on load
  document.addEventListener('DOMContentLoaded', function () {
    var settingsContent = document.querySelector('.menu-section[data-section="settings"] .menu-section-content');
    if (settingsContent) {
      window.UserContributions.injectSettingsToggles(settingsContent);
    }
  });
})();
