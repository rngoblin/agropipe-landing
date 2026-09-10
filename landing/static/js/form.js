(function () {
  "use strict";
  var form = document.querySelector(".lead-form form");
  if (!form) return;
  var success = document.querySelector(".lead-form__success");
  var i18n = JSON.parse(document.getElementById("form-i18n").textContent);
  var phone = form.phone;

  phone.addEventListener("input", function () {
    var d = phone.value.replace(/\D/g, "").replace(/^7|^8/, "").slice(0, 10);
    var out = "+7";
    if (d) out += " (" + d.slice(0, 3);
    if (d.length >= 3) out += ")";
    if (d.length > 3) out += " " + d.slice(3, 6);
    if (d.length > 6) out += "-" + d.slice(6, 8);
    if (d.length > 8) out += "-" + d.slice(8, 10);
    phone.value = out;
  });

  function setError(name, message) {
    var el = form.querySelector('[data-field="' + name + '"]');
    var err = el.classList.contains("field__error") ? el : el.querySelector(".field__error");
    if (err !== el) el.classList.toggle("field--error", !!message);
    err.textContent = message || "";
    err.hidden = !message;
  }

  function validate() {
    var ok = true;
    var name = form.name.value.trim();
    var digits = form.phone.value.replace(/\D/g, "");
    var company = form.company.value.trim();
    ["name", "phone", "company", "consent"].forEach(function (f) { setError(f, ""); });
    if (name.length < 2 || name.length > 60) { setError("name", i18n.name); ok = false; }
    if (digits.length !== 11) { setError("phone", i18n.phone); ok = false; }
    if (company.length < 2 || company.length > 120) { setError("company", i18n.company); ok = false; }
    if (!form.consent.checked) { setError("consent", i18n.consent); ok = false; }
    return ok;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    setError("server", "");
    if (!validate()) return;

    fetch("/api/lead", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({
        name: form.name.value.trim(),
        phone: form.phone.value.trim(),
        company: form.company.value.trim(),
        consent: form.consent.checked,
        hp: form.hp.value,
        rendered_at: form.rendered_at.value
      })
    })
      .then(function (r) {
        return r.json().then(function (data) { return { status: r.status, data: data }; });
      })
      .then(function (result) {
        if (result.status === 200 && result.data.ok) {
          form.hidden = true;
          success.hidden = false;
          return;
        }
        var f = result.data.field;
        setError(f && i18n[f] ? f : "server", (f && i18n[f]) || i18n.server);
      })
      .catch(function () { setError("server", i18n.server); });
  });
})();
