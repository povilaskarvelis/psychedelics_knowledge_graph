/* Lossless run-length columns keep repeated paper metadata off the wire. */
(function (root) {
  "use strict";
  function validate(payload) {
    if (payload?.schema_version !== "psychedelics_kg_analysis_bootstrap_v1" ||
        !Number.isSafeInteger(payload.row_count) || payload.row_count < 0 ||
        !Array.isArray(payload.fields) || !Array.isArray(payload.values) || !payload.values.length ||
        !Array.isArray(payload.columns) || payload.columns.length !== payload.fields.length ||
        new Set(payload.fields).size !== payload.fields.length ||
        payload.fields.some((field) => typeof field !== "string" || field.startsWith("__"))) {
      throw new Error("Unsupported analysis data.");
    }
    for (const runs of payload.columns) {
      let count = 0;
      if (!Array.isArray(runs)) throw new Error("Invalid analysis column.");
      for (const run of runs) {
        if (!Array.isArray(run) || run.length !== 2 ||
            !Number.isInteger(run[0]) || run[0] < 0 || run[0] >= payload.values.length ||
            !Number.isSafeInteger(run[1]) || run[1] < 1) throw new Error("Invalid analysis run.");
        count += run[1];
      }
      if (count !== payload.row_count) throw new Error("Incomplete analysis column.");
    }
  }

  function* batches(payload, batchSize = 1024) {
    validate(payload);
    if (!Number.isInteger(batchSize) || batchSize < 1) throw new Error("Invalid analysis batch size.");
    const positions = payload.fields.map(() => 0);
    const remaining = payload.columns.map((runs) => runs[0]?.[1] || 0);
    let batch = [];
    for (let row = 0; row < payload.row_count; row++) {
      const item = Object.create(null);
      payload.fields.forEach((field, column) => {
        const runs = payload.columns[column];
        const value = payload.values[runs[positions[column]][0]];
        if (value !== null && value !== undefined && value !== "") item[field] = value;
        if (--remaining[column] === 0) {
          positions[column]++;
          remaining[column] = runs[positions[column]]?.[1] || 0;
        }
      });
      item.__analysis_row = row;
      batch.push(item);
      if (batch.length === batchSize) { yield batch; batch = []; }
    }
    if (batch.length) yield batch;
  }

  const api = { validate, batches };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PKGAnalysisPayload = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
