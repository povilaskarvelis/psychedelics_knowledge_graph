# Workspace navigation study

The prototype files record the earlier comparison. The 8034 preview proxy now serves the clean main interface with the selected Q6B treatment; it no longer adds the comparison toolbar.

Focused Q6B boundary study (URL-only, with no comparison toolbar):
- `tab-variant=inset-divider` — short centered hairline; the quietest explicit separation.
- `tab-variant=frame-seam` — full-height structural seam matching the outer frame.
- `tab-variant=recessed-gutter` — a two-pixel dark channel separating the surfaces.
- `tab-variant=faded-divider` — a taller divider that fades before meeting the frame.

The comparison switches the actual application without reloading its research state. Only local prototype files are changed. Browser storage on port 8034 is separate from port 8011.

Revised options:
- Current: original layout.
- A — Refined: original rim switch, 14px labels and a slightly larger target. Minimal change.
- B — Text: plain labels in a small break in the panel border, with a thin neutral selected underline.
- C — Header: workspaces in the site header, with a compact introduction.
- D — Attached: small tabs whose selected outline joins the panel edge. Makes ownership explicit without another navigation row.

All variants reuse the existing neutral palette. No explanatory copy, full-width separator, or extra workspace row. C and D offer the clearest structural alternatives; A is the conservative adjustment.

Visually checked A–D at the available browser width and verified switching to Explore in D. These are design prototypes, not a completed responsive redesign or a usability-tested conclusion.

D refinements:
- D1 — Shared corner: the whole tab group and panel share one outer left edge, eliminating the adjacent panel corner. Default for this review.
- D1a — Quiet fill: selected tab uses a slightly lighter graphite fill.
- Q1 — Clean fill: quiet fill with no divider or underline on either tab.
- Q2 — Soft edge: clean fill with a barely visible top edge on the selected tab.
- Q3 — Tonal fill: clean fill with a very slight vertical tonal shift.
- Q4 — Open cutout: selected tab uses exactly the panel surface and is outlined as the open section.
- Q4a — Soft tint: open cutout with a very small muted green surface tint.
- Q4b — Edge marker: open cutout with a 2px interior edge marker.
- Q4c — Top glow: open cutout with a barely visible 1px top edge.
- Q5 — Recessed alternative: selected tab stays on the panel surface while the unselected tab is slightly darker.
- Q6 — Inverted fill: the unselected tab gets the light fill, while the selected tab remains continuous with the panel and gets the stronger outline.
- Q6a — Inverted flush: light inactive tab, panel-colored active tab, with the panel seam masked below it.
- Q6b — Inverted recess: darker inactive tab and panel-colored active tab, with the same seam treatment.
- D1b — Accent line: selected tab stays transparent and uses a thin neutral line at the bottom.
- D1c — Text only: selected tab is carried by stronger text weight and contrast.
- D1d — Folder tab: selected tab has a complete outline whose lower edge disappears into the panel surface.
- D1e — Seam: selected tab meets the panel through a quiet bottom seam rather than a filled highlight.
- D1f — Cutout: only the selected tab owns the folder outline; the surrounding group becomes invisible.
- D2 — Inset: the panel retains its full rounded outline; navigation sits inside with a restrained selected fill.
- D3 — Softer: D with matching 12px radii and a 32px inset from the left edge.

JavaScript syntax checked. Browser reload stalled during visual verification of D1–D3; these variants have not yet been visually verified.
