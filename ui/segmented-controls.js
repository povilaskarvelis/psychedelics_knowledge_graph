/* Shared sliding selection indicator for segmented controls and workspace tabs. */
(() => {
  const HOST_SELECTOR = [
    ".workspace-tabs",
    ".analysis-publication-mode",
    ".analytics-compact-toggle",
  ].join(", ");
  const ACTIVE_BUTTON_SELECTOR = "button.active, button[aria-selected=\"true\"], button[aria-pressed=\"true\"]";
  const initializedHosts = new WeakSet();
  let refreshFrame = 0;

  function activeButton(host) {
    return Array.from(host.querySelectorAll(ACTIVE_BUTTON_SELECTOR)).find(
      (button) => !button.hidden && button.getClientRects().length
    );
  }

  function setSliderPosition(host) {
    const button = activeButton(host);
    if (!button) {
      host.classList.remove("has-selection-slider");
      return;
    }

    const hostRect = host.getBoundingClientRect();
    const buttonRect = button.getBoundingClientRect();
    if (!hostRect.width || !buttonRect.width) return;

    const hostStyles = window.getComputedStyle(host);
    const borderLeft = Number.parseFloat(hostStyles.borderLeftWidth) || 0;
    const borderTop = Number.parseFloat(hostStyles.borderTopWidth) || 0;
    const x = buttonRect.left - hostRect.left - borderLeft;
    const y = buttonRect.top - hostRect.top - borderTop;

    host.style.setProperty("--selection-slider-x", `${x}px`);
    host.style.setProperty("--selection-slider-y", `${y}px`);
    host.style.setProperty("--selection-slider-width", `${buttonRect.width}px`);
    host.style.setProperty("--selection-slider-height", `${buttonRect.height}px`);
    host.classList.add("has-selection-slider");

    if (!initializedHosts.has(host)) {
      initializedHosts.add(host);
      window.requestAnimationFrame(() => {
        if (host.isConnected) host.classList.add("is-selection-slider-ready");
      });
    } else {
      host.classList.add("is-selection-slider-ready");
    }
  }

  function refreshSelectionSliders() {
    refreshFrame = 0;
    document.querySelectorAll(HOST_SELECTOR).forEach(setSliderPosition);
  }

  function scheduleRefresh() {
    if (refreshFrame) return;
    refreshFrame = window.requestAnimationFrame(refreshSelectionSliders);
  }

  window.refreshSelectionSliders = scheduleRefresh;
  window.addEventListener("resize", scheduleRefresh, { passive: true });
  document.addEventListener("click", scheduleRefresh);
  document.addEventListener("change", scheduleRefresh);

  new MutationObserver(scheduleRefresh).observe(document.body, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ["class", "aria-selected", "aria-pressed", "hidden"],
  });

  refreshSelectionSliders();
})();
