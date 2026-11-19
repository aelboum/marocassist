// Local test page behaviour: client-side validation that changes the DOM
// (aria-invalid, error texts, an alert summary) and a two-step flow that
// shows/hides sections. Nothing is sent anywhere.
(function () {
  "use strict";
  const step1 = document.getElementById("step-1");
  const step2 = document.getElementById("step-2");
  const summary = document.getElementById("summary");

  function setError(id, message) {
    const input = document.getElementById(id);
    const error = document.getElementById(id + "-error");
    input.setAttribute("aria-invalid", message ? "true" : "false");
    error.textContent = message;
  }

  document.getElementById("next").addEventListener("click", function () {
    const name = document.getElementById("full-name").value.trim();
    const email = document.getElementById("email").value.trim();
    const passport = document.getElementById("passport").value.trim();
    setError("full-name", name ? "" : "Please enter your full name.");
    setError("email", /.+@.+\..+/.test(email) ? "" : "Please enter a valid email address.");
    // Echoes the user's input, as some real sites do: the extension must mask it.
    setError("passport", /^[A-Z]{2}\d{7}$/.test(passport) ? "" : "Passport number " + passport + " is not valid.");
    const invalid = document.querySelectorAll("[aria-invalid='true']").length;
    summary.textContent = invalid ? invalid + " field(s) need attention." : "";
    if (!invalid) {
      step1.hidden = true;
      step2.hidden = false;
    }
  });

  document.getElementById("back").addEventListener("click", function () {
    step2.hidden = true;
    step1.hidden = false;
  });

  document.getElementById("demo-form").addEventListener("submit", function (event) {
    event.preventDefault();
    summary.textContent = "Demo only: nothing was submitted.";
  });
})();
