const INDEX_SCHEMA = "psychedelics_kg_analysis_index_v1";
const QUERY_CACHE_LIMIT = 48;

let index = null;
let studies = [];
let areaEntries = [];
let areaByKey = new Map();
let conceptsByArea = new Map();
let entitiesByLens = new Map();
let entityByLensAndKey = new Map();
let lensMemberships = new Map();
const queryCache = new Map();

function normalized(value) {
  return (value ?? "").toString().trim().toLocaleLowerCase("en-US");
}

function rememberQuery(key, value) {
  if (queryCache.has(key)) queryCache.delete(key);
  queryCache.set(key, value);
  while (queryCache.size > QUERY_CACHE_LIMIT) {
    queryCache.delete(queryCache.keys().next().value);
  }
}

function hydrateMembership(entry) {
  const [key, label, ids] = entry;
  const areas = new Map(
    Object.entries(entry[3] || {}).map(([areaKey, areaIds]) => [
      areaKey,
      { ids: areaIds, membership: new Set(areaIds) },
    ])
  );
  const concepts = new Map(
    Object.entries(entry[4] || {}).map(([areaKey, areaConcepts]) => [
      areaKey,
      new Map(
        Object.entries(areaConcepts || {}).map(([conceptKey, conceptIds]) => [
          conceptKey,
          { ids: conceptIds, membership: new Set(conceptIds) },
        ])
      ),
    ])
  );
  return {
    key,
    label,
    ids: Array.isArray(ids) ? ids : [],
    membership: new Set(Array.isArray(ids) ? ids : []),
    areas,
    concepts,
  };
}

function entityIdsForScope(entity, params) {
  if (params.areaKey && params.conceptKey) {
    return entity.concepts.get(params.areaKey)?.get(params.conceptKey)?.ids || [];
  }
  if (params.areaKey) return entity.areas.get(params.areaKey)?.ids || [];
  return entity.ids;
}

function hydrateIndex(payload) {
  if (!payload || payload.schema_version !== INDEX_SCHEMA || !Array.isArray(payload.studies)) {
    throw new Error("The analysis index has an unsupported format.");
  }
  index = payload;
  studies = payload.studies.map((entry, id) => ({
    id,
    key: entry[0],
    source: entry[1],
    year: Number(entry[2]) || 0,
    open: Boolean(entry[3]),
  }));
  areaEntries = Object.entries(payload.areas || {}).map(([key, entry]) => ({
    key,
    label: entry[0],
    ids: Array.isArray(entry[1]) ? entry[1] : [],
    membership: new Set(Array.isArray(entry[1]) ? entry[1] : []),
  }));
  areaByKey = new Map(areaEntries.map((entry) => [entry.key, entry]));
  conceptsByArea = new Map(
    Object.entries(payload.concepts || {}).map(([areaKey, entries]) => [
      areaKey,
      (entries || []).map(hydrateMembership),
    ])
  );
  entitiesByLens = new Map(
    Object.entries(payload.entities || {}).map(([lens, entries]) => [
      lens,
      (entries || []).map(hydrateMembership),
    ])
  );
  entityByLensAndKey = new Map();
  lensMemberships = new Map();
  entitiesByLens.forEach((entries, lens) => {
    entityByLensAndKey.set(lens, new Map(entries.map((entry) => [entry.key, entry])));
    const membership = new Set();
    entries.forEach((entry) => entry.ids.forEach((id) => membership.add(id)));
    lensMemberships.set(lens, membership);
  });
}

function baseStudyMask(params, { ignoreAccess = false, ignoreScope = false } = {}) {
  const mask = new Uint8Array(studies.length);
  const source = params.evidenceView === "all" ? "" : params.evidenceView;
  const minYear = Number(params.yearMin) || 0;
  const maxYear = Number(params.yearMax) || 0;
  const openOnly = !ignoreAccess && params.accessView === "open";
  const focus = params.focusKey
    ? entityByLensAndKey.get(params.lens)?.get(params.focusKey)
    : null;
  let lensMembership = lensMemberships.get(params.lens) || null;
  if (lensMembership && params.areaKey && !ignoreScope) {
    lensMembership = new Set();
    (entitiesByLens.get(params.lens) || []).forEach((entity) => {
      entityIdsForScope(entity, params).forEach((id) => lensMembership.add(id));
    });
  }
  const area = ignoreScope ? null : areaByKey.get(params.areaKey);
  const concept = ignoreScope || !params.areaKey || !params.conceptKey
    ? null
    : (conceptsByArea.get(params.areaKey) || []).find((entry) => entry.key === params.conceptKey);

  studies.forEach((study) => {
    if (source && study.source !== source) return;
    if (openOnly && !study.open) return;
    if (minYear && study.year && study.year < minYear) return;
    if (maxYear && study.year && study.year > maxYear) return;
    if (lensMembership && !lensMembership.has(study.id)) return;
    if (params.focusKey && !focus?.membership.has(study.id)) return;
    if (area && !area.membership.has(study.id)) return;
    if (concept && !concept.membership.has(study.id)) return;
    mask[study.id] = 1;
  });
  return mask;
}

function idsFromMask(mask) {
  const ids = [];
  for (let id = 0; id < mask.length; id += 1) {
    if (mask[id]) ids.push(id);
  }
  return ids;
}

function matchingIds(ids, mask) {
  return ids.filter((id) => mask[id]);
}

function countMembership(ids, mask) {
  let count = 0;
  ids.forEach((id) => {
    if (mask[id]) count += 1;
  });
  return count;
}

function scopeOptions(params) {
  const baseMask = baseStudyMask(params, {
    ignoreScope: true,
  });
  const areas = areaEntries
    .map((area) => ({ key: area.key, label: area.label, count: countMembership(area.ids, baseMask) }))
    .filter((area) => area.count > 0);
  const concepts = params.areaKey
    ? (conceptsByArea.get(params.areaKey) || [])
        .map((entry) => ({ key: entry.key, label: entry.label, count: countMembership(entry.ids, baseMask) }))
        .filter((entry) => entry.count > 0)
        .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label))
    : [];
  return { areas, concepts };
}

function matrixForQuery(params, mask) {
  if (!entitiesByLens.has(params.lens)) {
    const entries = params.areaKey
      ? (conceptsByArea.get(params.areaKey) || []).map((concept) => {
          const ids = matchingIds(concept.ids, mask);
          return {
            key: concept.key,
            label: concept.label,
            studyCount: ids.length,
            studyYears: ids.map((id) => studies[id].year).filter(Boolean),
          };
        })
      : areaEntries.map((area) => {
          const ids = matchingIds(area.ids, mask);
          return {
            key: area.key,
            label: area.label,
            studyCount: ids.length,
            studyYears: ids.map((id) => studies[id].year).filter(Boolean),
          };
        });
    return {
      entries: entries
        .filter((entry) => entry.studyCount > 0)
        .sort((left, right) => right.studyCount - left.studyCount || left.label.localeCompare(right.label)),
      maxCellCount: Math.max(1, ...entries.map((entry) => entry.studyCount)),
    };
  }

  const columns = params.areaKey
    ? (conceptsByArea.get(params.areaKey) || [])
        .filter((entry) => !params.conceptKey || entry.key === params.conceptKey)
        .map((entry) => ({
        key: entry.key,
        label: entry.label,
        membership: entry.membership,
        type: "concept",
      }))
    : areaEntries.map((entry) => ({
        key: entry.key,
        label: entry.label,
        membership: entry.membership,
        type: "area",
      }));
  let maxCellCount = 1;
  const entries = (entitiesByLens.get(params.lens) || []).map((entity) => {
    const ids = matchingIds(entityIdsForScope(entity, params), mask);
    if (!ids.length) return null;
    const cellCounts = {};
    columns.forEach((column) => {
      let count = 0;
      const entityColumnMembership = column.type === "concept"
        ? entity.concepts.get(params.areaKey)?.get(column.key)?.membership
        : entity.areas.get(column.key)?.membership;
      if (entityColumnMembership) {
        ids.forEach((id) => {
          if (entityColumnMembership.has(id)) count += 1;
        });
      }
      cellCounts[column.key] = count;
      maxCellCount = Math.max(maxCellCount, count);
    });
    const breadthCount = Object.values(cellCounts).filter((count) => count > 0).length;
    return {
      key: entity.key,
      label: entity.label,
      studyCount: ids.length,
      breadthCount,
      areaCount: params.areaKey ? 1 : breadthCount,
      conceptCount: params.areaKey ? breadthCount : 0,
      cellCounts,
      studyYears: ids.map((id) => studies[id].year).filter(Boolean),
    };
  }).filter(Boolean);
  entries.sort((left, right) =>
    right.studyCount - left.studyCount ||
    right.breadthCount - left.breadthCount ||
    left.label.localeCompare(right.label)
  );
  const focus = params.focusKey
    ? entityByLensAndKey.get(params.lens)?.get(params.focusKey)
    : null;
  let focusDetail = null;
  if (focus) {
    const ids = matchingIds(entityIdsForScope(focus, params), mask);
    focusDetail = {
      key: focus.key,
      studyKeys: ids.map((id) => studies[id].key),
      cells: Object.fromEntries(
        columns.map((column) => [
          column.key,
          ids.filter((id) => {
            const entityColumnMembership = column.type === "concept"
              ? focus.concepts.get(params.areaKey)?.get(column.key)?.membership
              : focus.areas.get(column.key)?.membership;
            return entityColumnMembership?.has(id);
          }).map((id) => studies[id].key),
        ])
      ),
    };
  }
  return { entries, maxCellCount, focusDetail };
}

function evidenceRowsForMask(mask) {
  return ["primary", "meta_analyses", "reviews"].map((source) => {
    const ids = [];
    for (let id = 0; id < studies.length; id += 1) {
      if (mask[id] && studies[id].source === source) ids.push(id);
    }
    const areaCounts = Object.fromEntries(
      areaEntries.map((area) => [
        area.key,
        ids.reduce((count, id) => count + (area.membership.has(id) ? 1 : 0), 0),
      ])
    );
    return {
      key: source,
      studyKeys: ids.map((id) => studies[id].key),
      count: ids.length,
      areaCounts,
    };
  });
}

function runQuery(params) {
  const queryKey = JSON.stringify(params);
  const cached = queryCache.get(queryKey);
  if (cached) {
    queryCache.delete(queryKey);
    queryCache.set(queryKey, cached);
    return cached;
  }
  const mask = baseStudyMask(params);
  const allAccessMask = baseStudyMask(params, { ignoreAccess: true });
  const studyIds = idsFromMask(mask);
  const allAccessStudyIds = idsFromMask(allAccessMask);
  const result = {
    queryKey,
    studyKeys: studyIds.map((id) => studies[id].key),
    allAccessStudyKeys: allAccessStudyIds.map((id) => studies[id].key),
    scope: scopeOptions(params),
    matrix: matrixForQuery(params, mask),
    evidenceRows: evidenceRowsForMask(mask),
    allAccessEvidenceRows: evidenceRowsForMask(allAccessMask),
  };
  rememberQuery(queryKey, result);
  return result;
}

self.addEventListener("message", async (event) => {
  const message = event.data || {};
  try {
    if (message.type === "init") {
      const response = await fetch(message.url, { cache: "force-cache" });
      if (!response.ok) throw new Error(`Analysis index returned HTTP ${response.status}.`);
      hydrateIndex(await response.json());
      self.postMessage({ type: "ready", requestId: message.requestId, studyCount: studies.length });
      return;
    }
    if (message.type === "query") {
      if (!index) throw new Error("Analysis index is not ready.");
      self.postMessage({ type: "result", requestId: message.requestId, result: runQuery(message.params || {}) });
    }
  } catch (error) {
    self.postMessage({
      type: "error",
      requestId: message.requestId,
      message: error instanceof Error ? error.message : String(error),
    });
  }
});
