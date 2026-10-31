// Helper for scan_field_coupling.py: finds literal tables and protocol-coupled
// lines in browser JavaScript. Usage:
//   node scan_js_literals.cjs <acorn-module-path> <scan_config.json> <file>...
// Prints one JSON object: {tables: [...], logic: {file: counts}}.
'use strict';
const fs = require('fs');
const acorn = require(process.argv[2]);
const config = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const files = process.argv.slice(4);

const DOMAIN_OR_KIND = new Set([...config.domain_ids, ...config.node_kinds]);
const FIELD = new RegExp(config.field_term_pattern, 'i');
const ANCHOR = new RegExp(config.anchor_terms.join('|'), 'i');
const ANCHOR_IDENT = new RegExp(config.anchor_identifier_pattern, 'i');

function parse(src) {
  const opts = { ecmaVersion: 'latest', locations: true, allowHashBang: true };
  try { return acorn.parse(src, { ...opts, sourceType: 'script' }); }
  catch (e) { return acorn.parse(src, { ...opts, sourceType: 'module' }); }
}

function children(node, fn) {
  for (const key of Object.keys(node)) {
    if (key === 'loc') continue;
    const value = node[key];
    if (Array.isArray(value)) value.forEach((v) => v && typeof v.type === 'string' && fn(v));
    else if (value && typeof value.type === 'string') fn(value);
  }
}

// String literals inside an initializer, without descending into functions.
function strings(node) {
  const acc = [];
  (function walk(n) {
    if (n.type === 'Literal' && typeof n.value === 'string') acc.push(n.value);
    else if (n.type === 'Literal' && n.regex) acc.push('/' + n.regex.pattern + '/');
    else if (n.type === 'TemplateLiteral' && n.expressions.length === 0) acc.push(n.quasis.map((q) => q.value.cooked).join(''));
    if (/Function/.test(n.type)) return;
    children(n, walk);
  })(node);
  return acc;
}

function isTableInit(init) {
  if (!init) return false;
  if (init.type === 'ArrayExpression' || init.type === 'ObjectExpression') return true;
  if (init.type === 'NewExpression' && init.callee && ['Set', 'Map'].includes(init.callee.name)) return true;
  return init.type === 'CallExpression' && init.callee && init.callee.type === 'MemberExpression' &&
    init.callee.object && init.callee.object.name === 'Object' && init.callee.property && init.callee.property.name === 'freeze';
}

const tables = [];
const logic = {};
for (const file of files) {
  if (!fs.existsSync(file)) continue;
  const src = fs.readFileSync(file, 'utf8');
  const lines = src.split('\n');
  const ast = parse(src);
  const tableLines = new Set();
  (function visit(n) {
    if (n.type === 'VariableDeclarator' && n.id && n.id.type === 'Identifier' && isTableInit(n.init)) {
      const items = strings(n.init);
      if (items.length >= 4) {
        tables.push({ file, name: n.id.name, line: n.loc.start.line, end: n.loc.end.line, items });
        for (let i = n.loc.start.line; i <= n.loc.end.line; i++) tableLines.add(i);
      }
    }
    children(n, visit);
  })(ast);
  const hit = { domain_or_kind: new Set(), field_term: new Set(), anchor_literal: new Set() };
  (function walk(n) {
    let value = null;
    if (n.type === 'Literal' && typeof n.value === 'string') value = n.value;
    else if (n.type === 'TemplateElement') value = n.value.cooked || '';
    if (value !== null && !tableLines.has(n.loc.start.line)) {
      const ln = n.loc.start.line;
      if (DOMAIN_OR_KIND.has(value)) hit.domain_or_kind.add(ln);
      if (FIELD.test(value)) hit.field_term.add(ln);
      if (ANCHOR.test(value)) hit.anchor_literal.add(ln);
    }
    children(n, walk);
  })(ast);
  let anchorIdent = 0;
  lines.forEach((line, i) => {
    if (!tableLines.has(i + 1) && ANCHOR_IDENT.test(line) && !/^\s*\/\//.test(line)) anchorIdent++;
  });
  const any = new Set([...hit.domain_or_kind, ...hit.field_term, ...hit.anchor_literal]);
  logic[file] = {
    total_lines: lines.length,
    domain_or_kind_lines: hit.domain_or_kind.size,
    field_term_lines: hit.field_term.size,
    anchor_literal_lines: hit.anchor_literal.size,
    anchor_identifier_lines: anchorIdent,
    any_protocol_literal_lines: any.size,
    inline_vocabulary_regexes: 0,
  };
}
process.stdout.write(JSON.stringify({ tables, logic }));
