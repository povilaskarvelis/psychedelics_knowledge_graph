/* Pure calculations shared by the research workspace and its regression tests. */
(function (root) {
  "use strict";
  const MISSING = "Not recorded";
  const values = (row, field) => [...new Set((Array.isArray(row.fields[field]) ? row.fields[field] : []).filter(Boolean))];

  function filter(rows, filters = {}) {
    return rows.filter((row) => Object.entries(filters).every(([field, value]) => {
      if (value === "" || value === null || value === undefined) return true;
      if (field === "minSample") return row.sample !== null && row.sample >= Number(value);
      if (field === "query") return row.search.includes(String(value).toLocaleLowerCase());
      const entries = values(row, field);
      return value === MISSING ? !entries.length : entries.includes(value);
    }));
  }

  function papers(rows) {
    const grouped = new Map();
    rows.forEach((row) => {
      const paper = grouped.get(row.paperKey) || { key: row.paperKey, rows: [], year: row.year, title: row.title };
      paper.rows.push(row);
      grouped.set(row.paperKey, paper);
    });
    return [...grouped.values()].sort((a, b) => (b.year || 0) - (a.year || 0) || a.title.localeCompare(b.title));
  }

  function paperValues(paper, field) {
    const result = [...new Set(paper.rows.flatMap((row) => values(row, field)))];
    return result.length ? result : [MISSING];
  }

  function distribution(rows, field) {
    const counts = new Map();
    papers(rows).forEach((paper) => paperValues(paper, field).forEach((label) => {
      counts.set(label, (counts.get(label) || 0) + 1);
    }));
    return [...counts].map(([label, count]) => ({ label, count }))
      .sort((a, b) => (a.label === MISSING) - (b.label === MISSING) || b.count - a.count || a.label.localeCompare(b.label));
  }

  // Co-coverage is counted once per publication, including when values occur in
  // different findings. It is never presented as a tested relationship.
  function coverage(rows, rowField, columnField) {
    const cells = new Map();
    const rowCounts = new Map();
    const columnCounts = new Map();
    papers(rows).forEach((paper) => {
      const left = paperValues(paper, rowField);
      const right = paperValues(paper, columnField);
      left.forEach((label) => rowCounts.set(label, (rowCounts.get(label) || 0) + 1));
      right.forEach((label) => columnCounts.set(label, (columnCounts.get(label) || 0) + 1));
      left.forEach((a) => right.forEach((b) => {
        const key = JSON.stringify([a, b]);
        const keys = cells.get(key) || new Set();
        keys.add(paper.key);
        cells.set(key, keys);
      }));
    });
    const ordered = (counts) => [...counts.keys()].sort((a, b) =>
      (a === MISSING) - (b === MISSING) || counts.get(b) - counts.get(a) || a.localeCompare(b));
    return { rows: ordered(rowCounts), columns: ordered(columnCounts), cells };
  }

  function matchingCell(rows, rowField, columnField, a, b) {
    const keys = new Set(papers(rows).filter((paper) =>
      paperValues(paper, rowField).includes(a) && paperValues(paper, columnField).includes(b)).map((paper) => paper.key));
    return rows.filter((row) => keys.has(row.paperKey));
  }

  function fingerprint(text) {
    // Two independent accumulators keep browser snapshots compact.
    let a = 2166136261;
    let b = 5381;
    for (let i = 0; i < text.length; i += 1) {
      a = Math.imul(a ^ text.charCodeAt(i), 16777619);
      b = Math.imul(b, 33) ^ text.charCodeAt(i);
    }
    return `${(a >>> 0).toString(36)}.${(b >>> 0).toString(36)}`;
  }

  function snapshot(rows) {
    return Object.fromEntries(papers(rows).map((paper) => [paper.key,
      fingerprint(paper.rows.map((row) => row.signature).sort().join("\n"))]));
  }

  function changes(before, after) {
    return {
      added: Object.keys(after).filter((key) => !Object.hasOwn(before, key)),
      changed: Object.keys(after).filter((key) => Object.hasOwn(before, key) && before[key] !== after[key]),
      removed: Object.keys(before).filter((key) => !Object.hasOwn(after, key)),
    };
  }

  const api = { MISSING, filter, papers, paperValues, distribution, coverage, matchingCell, snapshot, changes };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PKGResearch = api;
})(typeof window !== "undefined" ? window : globalThis);
