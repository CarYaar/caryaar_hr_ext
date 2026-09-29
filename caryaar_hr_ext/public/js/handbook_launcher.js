// A floating Handbook button on every desk page, so the Employee Handbook is one click away from
// anywhere in the ERP. Opens /handbook in a new tab. Stays out of the way on phones (bottom left,
// above the safe area) and never shows on the handbook page itself.
(function () {
  if (!window.frappe || window.location.pathname.indexOf("/handbook") === 0) return;
  function mount() {
    if (document.getElementById("cy-handbook-launcher")) return;
    var a = document.createElement("a");
    a.id = "cy-handbook-launcher";
    a.href = "/handbook";
    a.target = "_blank";
    a.rel = "noopener";
    a.title = "Employee Handbook";
    a.setAttribute("aria-label", "Open the Employee Handbook");
    a.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg><span>Handbook</span>';
    a.style.cssText = "position:fixed;left:16px;bottom:calc(16px + env(safe-area-inset-bottom,0px));z-index:1030;display:inline-flex;align-items:center;gap:8px;padding:10px 14px;border-radius:999px;background:#6D28D9;color:#F5F3F0;font:600 13px Inter,system-ui,sans-serif;text-decoration:none;box-shadow:0 8px 24px rgba(23,19,31,.22);transition:transform .15s ease,box-shadow .15s ease;";
    a.addEventListener("mouseenter", function () { a.style.transform = "translateY(-2px)"; a.style.boxShadow = "0 12px 28px rgba(23,19,31,.28)"; });
    a.addEventListener("mouseleave", function () { a.style.transform = ""; a.style.boxShadow = "0 8px 24px rgba(23,19,31,.22)"; });
    document.body.appendChild(a);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
})();
