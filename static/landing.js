/* ================================================================
   Language Engine — Landing Page JS
   Auth modal, nav scroll, smooth interactions.
   ================================================================ */

(function() {
  'use strict';

  // ---- Nav scroll shadow ----
  var nav = document.getElementById('leNav');
  if (nav) {
    window.addEventListener('scroll', function() {
      nav.classList.toggle('scrolled', window.scrollY > 10);
    }, { passive: true });
  }

  // ---- Pricing billing toggle ----
  (function initProBillingToggle() {
    var buttons = document.querySelectorAll('[data-pro-billing]');
    var amount = document.getElementById('proPriceAmount');
    var period = document.getElementById('proPricePeriod');
    var meta = document.getElementById('proPriceMeta');
    var billingBenefit = document.getElementById('proBillingBenefitText');
    if (!buttons.length || !amount || !period || !meta) return;

    function setBilling(mode) {
      var yearly = mode === 'yearly';
      amount.textContent = yearly ? '$100' : '$10';
      period.textContent = yearly ? ' / year' : ' / month';
      meta.textContent = yearly ? 'Billed yearly' : 'Monthly billing';
      if (billingBenefit) billingBenefit.textContent = yearly ? '2 months free' : 'Cancel anytime';
      for (var i = 0; i < buttons.length; i++) {
        var active = buttons[i].getAttribute('data-pro-billing') === mode;
        buttons[i].classList.toggle('is-active', active);
        buttons[i].setAttribute('aria-pressed', active ? 'true' : 'false');
      }
    }

    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener('click', function() {
        setBilling(this.getAttribute('data-pro-billing') || 'monthly');
      });
    }
  })();

  // ---- Preview video carousel ----
  (function initPreviewVideoCarousel() {
    var root = document.getElementById('previewVideoCarousel');
    if (!root) return;

    var video = document.getElementById('previewVideo');
    var source = document.getElementById('previewVideoSource');
    var buttons = root.querySelectorAll('[data-preview-video]');
    if (!video || !source || !buttons.length) return;

    var activeIndex = 0;
    var videoLoaded = false;

    function loadSelectedVideo() {
      var btn = buttons[activeIndex];
      var src = btn.getAttribute('data-video-src') || '';
      var poster = btn.getAttribute('data-video-poster') || '';
      if (!src) return;
      if (source.getAttribute('src') !== src) {
        video.pause();
        source.setAttribute('src', src);
        if (poster) video.setAttribute('poster', poster);
        video.load();
      } else if (!videoLoaded) {
        video.load();
      }
      videoLoaded = true;
    }

    function selectVideo(index, loadNow) {
      activeIndex = ((index % buttons.length) + buttons.length) % buttons.length;
      var btn = buttons[activeIndex];
      var src = btn.getAttribute('data-video-src') || '';
      var poster = btn.getAttribute('data-video-poster') || '';

      for (var i = 0; i < buttons.length; i++) {
        var active = i === activeIndex;
        buttons[i].classList.toggle('is-active', active);
        buttons[i].setAttribute('aria-selected', active ? 'true' : 'false');
      }

      if (poster) {
        video.setAttribute('poster', poster);
      }
      if (src && source.getAttribute('src') !== src) {
        source.removeAttribute('src');
        source.setAttribute('data-src', src);
        videoLoaded = false;
      }
      if (loadNow) loadSelectedVideo();
    }

    for (var i = 0; i < buttons.length; i++) {
      (function(idx) {
        buttons[idx].addEventListener('click', function() {
          selectVideo(idx, true);
        });
      })(i);
    }

    if ('IntersectionObserver' in window) {
      var observer = new IntersectionObserver(function(entries) {
        if (entries[0] && entries[0].isIntersecting) {
          loadSelectedVideo();
          observer.disconnect();
        }
      }, { rootMargin: '120px 0px' });
      observer.observe(root);
    }
    video.addEventListener('pointerdown', loadSelectedVideo, { once: true });
  })();

  // ---- Auth modal ----
  var PENDING_CHECKOUT_KEY = 'lePendingCheckoutBilling';
  var verificationResendEmail = '';
  var verificationResendMessageId = '';

  function currentProBilling() {
    var active = document.querySelector('[data-pro-billing].is-active');
    var billing = active ? active.getAttribute('data-pro-billing') : 'monthly';
    return billing === 'yearly' ? 'yearly' : 'monthly';
  }

  function postAuthRedirect() {
    var billing = sessionStorage.getItem(PENDING_CHECKOUT_KEY);
    sessionStorage.removeItem(PENDING_CHECKOUT_KEY);
    if (billing === 'monthly' || billing === 'yearly') {
      return '/account?checkout=' + encodeURIComponent(billing);
    }
    return '/reader';
  }

  window.startProSignup = function() {
    sessionStorage.setItem(PENDING_CHECKOUT_KEY, currentProBilling());
    openAuthModal('signup');
  };

  window.openAuthModal = function(view) {
    var modal = document.getElementById('authModal');
    modal.classList.add('active');
    switchAuthView(view || 'signup');
    document.body.style.overflow = 'hidden';
  };

  window.closeAuthModal = function() {
    var modal = document.getElementById('authModal');
    modal.classList.remove('active');
    document.body.style.overflow = '';
    clearFormErrors();
  };

  window.switchAuthView = function(view) {
    var signup = document.getElementById('authSignup');
    var login  = document.getElementById('authLogin');
    var forgot = document.getElementById('authForgot');
    var reset = document.getElementById('authReset');
    clearFormErrors();
    signup.style.display = 'none';
    login.style.display = 'none';
    if (forgot) forgot.style.display = 'none';
    if (reset) reset.style.display = 'none';
    if (view === 'login') {
      login.style.display  = 'block';
    } else if (view === 'forgot' && forgot) {
      forgot.style.display = 'block';
    } else if (view === 'reset' && reset) {
      reset.style.display = 'block';
    } else {
      signup.style.display = 'block';
    }
  };

  // Close modal on overlay click
  var overlay = document.getElementById('authModal');
  if (overlay) {
    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) closeAuthModal();
    });
  }

  // Close modal on Escape
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeAuthModal();
  });

  // ---- Form handling ----
  function clearFormErrors() {
    var errors = document.querySelectorAll('.le-form-error');
    for (var i = 0; i < errors.length; i++) {
      errors[i].className = 'le-form-error';
      errors[i].style.display = 'none';
      errors[i].textContent = '';
    }
    hideResendVerification();
  }

  function showFormMessage(id, msg, kind) {
    var el = document.getElementById(id);
    if (el) {
      el.textContent = msg;
      el.className = 'le-form-error' + (kind === 'info' ? ' info' : '');
      el.style.display = 'block';
    }
  }

  function showError(id, msg) {
    showFormMessage(id, msg, 'error');
  }

  function showInfo(id, msg) {
    showFormMessage(id, msg, 'info');
  }

  function hideResendVerification() {
    verificationResendEmail = '';
    verificationResendMessageId = '';
    var buttons = document.querySelectorAll('.le-inline-resend-verification');
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].remove();
    }
  }

  function showResendVerification(email, messageId) {
    verificationResendEmail = email || '';
    verificationResendMessageId = messageId || '';
    var el = document.getElementById(verificationResendMessageId);
    if (!verificationResendEmail || !el) return;
    var oldButtons = document.querySelectorAll('.le-inline-resend-verification');
    for (var i = 0; i < oldButtons.length; i++) {
      oldButtons[i].remove();
    }
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'le-inline-resend-verification';
    btn.textContent = 'Resend';
    btn.onclick = window.handleResendVerification;
    el.appendChild(document.createTextNode(' '));
    el.appendChild(btn);
  }

  window.handleSignup = function(e) {
    e.preventDefault();
    clearFormErrors();
    var email    = document.getElementById('signupEmail').value.trim();
    var password = document.getElementById('signupPassword').value;

    if (!email) {
      showError('signupEmailError', 'Please enter your email.');
      return false;
    }
    if (password.length < 8) {
      showError('signupPasswordError', 'Password must be at least 8 characters.');
      return false;
    }

    // POST to auth endpoint
    fetch('/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email, password: password })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.ok) {
        showInfo('signupEmailError', data.message || 'Check your email for a verification link.');
        showResendVerification(email, 'signupEmailError');
      } else {
        showError('signupEmailError', data.error || 'Signup failed.');
      }
    })
    .catch(function() {
      showError('signupEmailError', 'Network error. Please try again.');
    });

    return false;
  };

  window.handleLogin = function(e) {
    e.preventDefault();
    clearFormErrors();
    var email    = document.getElementById('loginEmail').value.trim();
    var password = document.getElementById('loginPassword').value;

    if (!email) {
      showError('loginEmailError', 'Please enter your email.');
      return false;
    }
    if (!password) {
      showError('loginPasswordError', 'Please enter your password.');
      return false;
    }

    fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email, password: password })
    })
    .then(function(r) {
      return r.json().then(function(data) {
        data._status = r.status;
        return data;
      });
    })
    .then(function(data) {
      if (data.ok) {
        window.location.href = postAuthRedirect();
      } else {
        showError('loginEmailError', data.error || 'Login failed.');
        if (data._status === 403) {
          showResendVerification(email, 'loginEmailError');
        }
      }
    })
    .catch(function() {
      showError('loginEmailError', 'Network error. Please try again.');
    });

    return false;
  };

  window.handleResendVerification = function() {
    var email = verificationResendEmail;
    var messageId = verificationResendMessageId || 'signupEmailError';
    if (!email) return false;

    fetch('/auth/resend-verification', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.ok) {
        showInfo(messageId, data.message || 'Verification email sent.');
        showResendVerification(email, messageId);
      } else {
        showError(messageId, data.error || 'Could not send verification email.');
      }
    })
    .catch(function() {
      showError(messageId, 'Network error. Please try again.');
    });

    return false;
  };

  window.handleForgotPassword = function(e) {
    e.preventDefault();
    clearFormErrors();
    var email = document.getElementById('forgotEmail').value.trim();
    if (!email) {
      showError('forgotEmailError', 'Please enter your email.');
      return false;
    }

    fetch('/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.ok) {
        showInfo('forgotEmailError', 'A reset link has been sent to your account inbox.');
      } else {
        showError('forgotEmailError', data.error || 'Could not send reset link.');
      }
    })
    .catch(function() {
      showError('forgotEmailError', 'Network error. Please try again.');
    });

    return false;
  };

  window.handleResetPassword = function(e) {
    e.preventDefault();
    clearFormErrors();
    var token = document.getElementById('resetToken').value;
    var password = document.getElementById('resetPassword').value;
    if (password.length < 8) {
      showError('resetPasswordError', 'Password must be at least 8 characters.');
      return false;
    }

    fetch('/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: token, password: password })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.ok) {
        window.history.replaceState(null, '', '/');
        switchAuthView('login');
        showInfo('loginEmailError', 'Password updated. Sign in with your new password.');
      } else {
        showError('resetPasswordError', data.error || 'Could not update password.');
      }
    })
    .catch(function() {
      showError('resetPasswordError', 'Network error. Please try again.');
    });

    return false;
  };

  window.handleGoogleAuth = function() {
    var billing = sessionStorage.getItem(PENDING_CHECKOUT_KEY);
    if (billing === 'monthly' || billing === 'yearly') {
      window.location.href = '/auth/google/login?next=' + encodeURIComponent('/account?checkout=' + billing);
      return;
    }
    window.location.href = '/auth/google/login';
  };

  (function openResetLinkIfPresent() {
    var token = new URLSearchParams(window.location.search).get('reset_token');
    if (!token) return;
    var resetToken = document.getElementById('resetToken');
    if (resetToken) resetToken.value = token;
    openAuthModal('reset');
  })();

  (function openEmailVerificationResultIfPresent() {
    var params = new URLSearchParams(window.location.search);
    if (params.get('email_verified') === '1') {
      window.history.replaceState(null, '', '/');
      openAuthModal('login');
      showInfo('loginEmailError', 'Email verified. Sign in to continue.');
    } else if (params.get('email_verify') === 'invalid') {
      window.history.replaceState(null, '', '/');
      openAuthModal('login');
      showError('loginEmailError', 'This verification link is invalid or expired.');
    }
  })();

  // ---- Hero showcase carousel ----
  (function initShowcaseCarousel() {
    var slides = document.querySelectorAll('.le-showcase-slide');
    var dots   = document.querySelectorAll('.le-showcase-dot');
    if (!slides.length) return;

    var i = 0;
    var timer = null;
    var INTERVAL_MS = 6000;

    function go(n) {
      slides[i].classList.remove('is-active');
      if (dots[i]) dots[i].classList.remove('is-active');
      i = ((n % slides.length) + slides.length) % slides.length;
      slides[i].classList.add('is-active');
      if (dots[i]) dots[i].classList.add('is-active');
    }
    function start() { stop(); timer = setInterval(function() { go(i + 1); }, INTERVAL_MS); }
    function stop()  { if (timer) { clearInterval(timer); timer = null; } }

    for (var d = 0; d < dots.length; d++) {
      (function(idx) {
        dots[idx].addEventListener('click', function() { go(idx); start(); });
      })(d);
    }
    var prev = document.querySelector('.le-showcase-prev');
    var next = document.querySelector('.le-showcase-next');
    if (prev) prev.addEventListener('click', function() { go(i - 1); start(); });
    if (next) next.addEventListener('click', function() { go(i + 1); start(); });

    var frame = document.querySelector('.le-showcase-frame');
    if (frame) {
      frame.addEventListener('mouseenter', stop);
      frame.addEventListener('mouseleave', start);
    }

    start();
  })();

  // ---- Per-pane mini-carousels (feature blocks) ----
  (function initFblockCarousels() {
    var carousels = document.querySelectorAll('.le-fblock-carousel');
    for (var c = 0; c < carousels.length; c++) {
      (function(root) {
        var slides = root.querySelectorAll('.le-fbc-slide');
        var dots   = root.querySelectorAll('.le-fbc-dot');
        if (slides.length < 2) return; // single-image: no controls needed
        var i = 0;
        var timer = null;
        var INTERVAL_MS = 7000;

        function go(n) {
          slides[i].classList.remove('is-active');
          if (dots[i]) dots[i].classList.remove('is-active');
          i = ((n % slides.length) + slides.length) % slides.length;
          slides[i].classList.add('is-active');
          if (dots[i]) dots[i].classList.add('is-active');
        }
        function start() { stop(); timer = setInterval(function() { go(i + 1); }, INTERVAL_MS); }
        function stop()  { if (timer) { clearInterval(timer); timer = null; } }

        for (var d = 0; d < dots.length; d++) {
          (function(idx) {
            dots[idx].addEventListener('click', function() { go(idx); start(); });
          })(d);
        }
        var prev = root.querySelector('.le-fbc-prev');
        var next = root.querySelector('.le-fbc-next');
        if (prev) prev.addEventListener('click', function() { go(i - 1); start(); });
        if (next) next.addEventListener('click', function() { go(i + 1); start(); });

        root.addEventListener('mouseenter', stop);
        root.addEventListener('mouseleave', start);

        start();
      })(carousels[c]);
    }
  })();

  // ---- Check if user is already logged in ----
  fetch('/auth/me')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.ok && data.user) {
        // Swap "Sign In" / "Get Started" to "Open Reader" / account link
        var signInBtn = document.getElementById('btnSignIn');
        if (signInBtn) {
          signInBtn.textContent = data.user.email;
          signInBtn.onclick = function() { window.location.href = '/account'; };
        }
      }
    })
    .catch(function() { /* not logged in, that's fine */ });

})();
