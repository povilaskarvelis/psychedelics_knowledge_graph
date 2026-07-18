(function () {
  const apiBase = "https://psychedelics-kg-api.onrender.com";
  const status = document.querySelector("[data-api-status]");
  const release = document.querySelector("[data-api-release]");
  const papers = document.querySelector("[data-api-papers]");
  const findings = document.querySelector("[data-api-findings]");

  const formatCount = (value) =>
    Number.isFinite(Number(value)) ? Number(value).toLocaleString("en-US") : "—";

  let wakeTimer = window.setTimeout(() => {
    if (status) status.textContent = "Waking service…";
  }, 4500);

  fetch(`${apiBase}/api/v1/meta`, { headers: { Accept: "application/json" } })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((meta) => {
      window.clearTimeout(wakeTimer);
      if (status) {
        status.textContent = "Live";
        status.classList.add("is-live");
      }
      if (release) release.textContent = meta.run_id || meta.release_id || "Current";
      if (papers) papers.textContent = formatCount(meta.row_counts && meta.row_counts.papers);
      if (findings) findings.textContent = formatCount(meta.row_counts && meta.row_counts.findings);
    })
    .catch(() => {
      window.clearTimeout(wakeTimer);
      if (status) status.textContent = "Temporarily unavailable";
      if (release) release.textContent = "See API health";
    });

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
})();
