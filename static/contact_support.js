(function() {
  function valueFrom(id) {
    var el = document.getElementById(id);
    return el && typeof el.value === "string" ? el.value.trim() : "";
  }

  function setStatus(text, kind) {
    var status = document.getElementById("contactStatus");
    if (!status) return;
    status.textContent = text || "";
    status.className = "contact-status" + (kind ? " " + kind : "");
  }

  function contactContext() {
    return {
      url: document.referrer || window.location.href,
      contact_page: window.location.href,
      user_agent: navigator.userAgent || ""
    };
  }

  function submitContact(ev) {
    ev.preventDefault();

    var submit = document.getElementById("contactSubmit");
    var contactType = valueFrom("contactType") || "Question";
    var subject = valueFrom("contactSubject");
    var message = valueFrom("contactMessage");

    if (!subject || !message) {
      setStatus("Title and message are required.", "error");
      return;
    }

    if (submit) submit.disabled = true;
    setStatus("Sending...", "");

    fetch("/api/contact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contact_type: contactType,
        subject: subject,
        message: message,
        context: contactContext()
      })
    })
      .then(function(resp) {
        return resp.json().catch(function() { return {}; }).then(function(data) {
          if (!resp.ok || !data.ok) {
            throw new Error(data.error || "Could not send message.");
          }
          return data;
        });
      })
      .then(function() {
        setStatus("Message sent.", "success");
        var form = document.getElementById("contactForm");
        if (form) form.reset();
      })
      .catch(function(err) {
        setStatus(err && err.message ? err.message : "Could not send message.", "error");
      })
      .finally(function() {
        if (submit) submit.disabled = false;
      });
  }

  function initContactPage() {
    var form = document.getElementById("contactForm");
    if (!form) return;
    form.addEventListener("submit", submitContact);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initContactPage);
  } else {
    initContactPage();
  }
})();
