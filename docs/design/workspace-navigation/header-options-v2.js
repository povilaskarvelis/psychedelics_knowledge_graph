(() => {
  const options = [
    ["above-left", "Neutral"],
    ["above-green-soft", "Soft green"],
    ["above-green-edge", "Green edge"],
    ["above-green-tonal", "Tonal green"],
    ["shared-edge", "Folder reference"],
  ];
  const dock = document.createElement("aside");
  dock.className = "nav-study-dock";
  dock.setAttribute("aria-label", "Explore and Analyze selection treatments");
  dock.innerHTML = options.map(([key, label]) => (
    `<button type="button" data-nav-option="${key}" aria-pressed="false">${label}</button>`
  )).join("");
  document.body.append(dock);

  const known = new Set(options.map(([key]) => key));
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("nav-option");

  function setOption(key, { updateUrl = true } = {}) {
    const next = known.has(key) ? key : "above-left";
    document.body.dataset.navOption = next;
    dock.querySelectorAll("button").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.navOption === next));
    });
    if (updateUrl) {
      const url = new URL(window.location.href);
      if (next === "above-left") url.searchParams.delete("nav-option");
      else url.searchParams.set("nav-option", next);
      history.replaceState(history.state, "", url);
    }
    window.dispatchEvent(new Event("resize"));
  }

  dock.addEventListener("click", (event) => {
    const button = event.target.closest("[data-nav-option]");
    if (button) setOption(button.dataset.navOption);
  });

  setOption(requested || "above-left", { updateUrl: false });
})();
