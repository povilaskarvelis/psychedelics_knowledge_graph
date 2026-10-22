const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const remote = 'https://data.psychedelicskg.com/browser/active.json';

function contextFor(file, names, href, globals = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../ui', file), 'utf8');
  const context = vm.createContext({
    URL, URLSearchParams, window: { location: new URL(href) },
    LOCAL_GRAPH_DATA_HOSTS: new Set(['', 'localhost', '127.0.0.1', '::1']),
    LOCAL_DATA_HOSTS: new Set(['', 'localhost', '127.0.0.1', '::1']),
    LOCAL_DATA_SOURCE_QUERY_PARAMETER: 'data-source',
    GRAPH_PAYLOAD_LOCAL_POINTER_URL: '/__preview__/active.json',
    LOCAL_DATA_POINTER_URL: '/__preview__/active.json',
    GRAPH_PAYLOAD_PUBLIC_PREVIEW_POINTER_URL: '/__preview__/published.json',
    PUBLIC_PREVIEW_POINTER_URL: '/__preview__/published.json',
    GRAPH_PAYLOAD_REMOTE_POINTER_URL: remote, PUBLIC_DATA_POINTER_URL: remote,
    cleanDisplayText: value => String(value).trim(), ...globals,
  });
  for (const name of names) {
    const match = source.match(new RegExp(`^(?:async )?function ${name}\\([\\s\\S]*?^}`, 'm'));
    assert.ok(match, name);
    vm.runInContext(match[0], context);
  }
  return context;
}

test('Graph and Methods select the proxy only for this Netlify project', () => {
  const cases = [
    ['https://deploy-preview-4--psychedelicskg.netlify.app/', '/browser/active.json'],
    ['https://feature--psychedelicskg.netlify.app/methods/', '/browser/active.json'],
    ['https://abc123--psychedelicskg.netlify.app/', '/browser/active.json'],
    ['https://psychedelicskg.netlify.app/', '/browser/active.json'],
    ['https://psychedelicskg.com/', remote],
    ['https://www.psychedelicskg.com/methods/', remote],
    ['https://deploy-preview-4--another-site.netlify.app/', remote],
    ['https://deploy-preview-4--psychedelicskg.netlify.app.example.com/', remote],
    ['https://psychedelicskg.com/?data-source=local', remote],
    ['https://deploy-preview-4--psychedelicskg.netlify.app/?data-source=local', '/browser/active.json'],
    ['http://localhost:8000/', '/__preview__/published.json'],
    ['http://127.0.0.1:8000/?data-source=local', '/__preview__/active.json'],
  ];
  for (const [href, expected] of cases) {
    const graph = contextFor('app.js', ['localDataSourceRequested', 'graphPayloadPointerCandidates'], href);
    const methods = contextFor('methods.js', ['localDataSourceRequested', 'selectedDataPointerUrl'], href);
    assert.equal(graph.graphPayloadPointerCandidates()[0], expected, `Graph: ${href}`);
    assert.equal(methods.selectedDataPointerUrl(), expected, `Methods: ${href}`);
  }
});

test('Graph release files and relative detail chunks retain the pointer origin', () => {
  const release = 'browser/releases/run/release/analysis_primary.json';
  for (const pointer of [remote, 'https://deploy-preview-4--psychedelicskg.netlify.app/browser/active.json']) {
    const graph = contextFor('app.js', ['graphPayloadCandidates'], pointer);
    const url = graph.graphPayloadCandidates({ __pointer_url: pointer }, release)[0];
    assert.equal(url, `${new URL(pointer).origin}/${release}`);
    assert.equal(new URL('detail_0.json', url).href,
      `${new URL(pointer).origin}/browser/releases/run/release/detail_0.json`);
  }
});

test('Methods datasets retain the pointer origin for both previews and production', async () => {
  for (const pointer of [remote, 'https://deploy-preview-4--psychedelicskg.netlify.app/browser/active.json']) {
    const requests = [];
    const methods = contextFor('methods.js', ['loadMethodsData'], pointer, {
      REQUIRED_METHODS_DATA: new Set(['pipeline_status', 'bibliography', 'graph_inclusion_dispositions']),
      loadPublicDataPointer: async () => ({
        __pointer_url: pointer,
        methods: Object.fromEntries(['pipeline_status', 'bibliography', 'graph_inclusion_dispositions']
          .map(name => [name, `browser/releases/run/release/${name}.json`])),
      }),
      fetchJsonFromCandidates: async urls => { requests.push(...urls); return { loaded: true }; },
    });
    for (const name of ['pipeline_status', 'bibliography', 'graph_inclusion_dispositions']) {
      assert.equal((await methods.loadMethodsData(name)).loaded, true);
      assert.equal(requests.at(-1), `${new URL(pointer).origin}/browser/releases/run/release/${name}.json`);
    }
    await assert.rejects(methods.loadMethodsData('private-api'), /Unknown Methods dataset/);
  }
});
