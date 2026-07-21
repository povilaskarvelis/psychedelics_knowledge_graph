(function () {
  const localHosts = new Set(["", "localhost", "127.0.0.1", "::1"]);
  const query = new URLSearchParams(window.location.search);
  if (localHosts.has(window.location.hostname) && query.get("data-source") === "local") {
    document.querySelectorAll('a[href]').forEach((link) => {
      const rawHref = link.getAttribute("href") || "";
      if (!rawHref || rawHref.startsWith("#")) return;
      const url = new URL(rawHref, window.location.href);
      if (url.origin !== window.location.origin) return;
      url.searchParams.set("data-source", "local");
      link.href = `${url.pathname}${url.search}${url.hash}`;
    });
  }

  const headers = document.querySelectorAll("[data-site-header]");

  headers.forEach((header) => {
    const toggle = header.querySelector("[data-site-nav-toggle]");
    const nav = header.querySelector("[data-site-nav]");

    if (!toggle || !nav) return;

    const setOpen = (open) => {
      header.classList.toggle("is-nav-open", open);
      toggle.setAttribute("aria-expanded", String(open));
    };

    toggle.addEventListener("click", () => {
      setOpen(!header.classList.contains("is-nav-open"));
    });

    nav.addEventListener("click", (event) => {
      if (event.target.closest("a")) setOpen(false);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        setOpen(false);
        toggle.focus();
      }
    });

    document.addEventListener("click", (event) => {
      if (!header.contains(event.target)) setOpen(false);
    });
  });
})();
