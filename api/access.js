(function () {
  "use strict";

  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copyTarget);
      if (!target) return;
      const text = target.textContent.trim();
      try {
        await navigator.clipboard.writeText(text);
        const original = button.textContent;
        button.textContent = "Copied";
        window.setTimeout(() => { button.textContent = original; }, 1400);
      } catch (_error) {
        window.getSelection().selectAllChildren(target);
      }
    });
  });

  document.querySelectorAll("[data-download-link]").forEach((link) => {
    link.addEventListener("click", () => {
      const original = link.textContent;
      link.textContent = "Preparing…";
      link.setAttribute("aria-busy", "true");
      window.setTimeout(() => {
        link.textContent = original;
        link.removeAttribute("aria-busy");
      }, 15000);
    });
  });
})();
