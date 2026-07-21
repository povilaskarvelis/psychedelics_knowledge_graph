const assert = require("node:assert/strict");
const test = require("node:test");

const {
  deterministicPublicationFormatFromUrl,
  isPublicHttpUrl,
  urlFormatExclusion,
} = require("../pipeline/fulltext/recover_pdfs_via_doi_browser.cjs");

test("browser recovery allows public hosts and rejects local network destinations", async () => {
  const publicLookup = async () => [{ address: "93.184.216.34", family: 4 }];
  const mixedLookup = async () => [
    { address: "93.184.216.34", family: 4 },
    { address: "10.0.0.8", family: 4 },
  ];

  assert.equal(await isPublicHttpUrl("https://publisher.example/paper.pdf", publicLookup), true);
  assert.equal(await isPublicHttpUrl("https://publisher.example/paper.pdf", mixedLookup), false);
  assert.equal(await isPublicHttpUrl("http://127.0.0.1:8070/api/isalive", publicLookup), false);
  assert.equal(await isPublicHttpUrl("http://169.254.169.254/latest/meta-data/", publicLookup), false);
  assert.equal(await isPublicHttpUrl("file:///etc/passwd", publicLookup), false);
});

test("explicit poster path segments are deterministic publication-format exclusions", () => {
  assert.deepEqual(
    deterministicPublicationFormatFromUrl("https://f1000research.com/posters/5-997?ref=doi#top"),
    {
      publication_format: "conference_poster",
      reason: "explicit_url_path_segment:posters",
      evidence_url: "https://f1000research.com/posters/5-997?ref=doi",
    },
  );
  assert.equal(
    deterministicPublicationFormatFromUrl("https://example.org/POSTER/123").publication_format,
    "conference_poster",
  );
});

test("poster URL classification requires an exact path segment", () => {
  for (const url of [
    "https://example.org/articles/posterior-cingulate-cortex",
    "https://example.org/articles/123?type=poster",
    "https://example.org/assets/conference-poster.pdf",
    "https://example.org/proceedings/2026/paper-17",
    "https://example.org/conference-abstracts/ketamine-study",
  ]) {
    assert.equal(deterministicPublicationFormatFromUrl(url), null, url);
  }
});

test("browser outcome records durable URL evidence and remains terminal", () => {
  assert.deepEqual(
    urlFormatExclusion(
      "10.7490/f1000research.1111976.1",
      "https://f1000research.com/posters/5-997",
      ["https://f1000research.com/posters/5-997"],
    ),
    {
      doi: "10.7490/f1000research.1111976.1",
      status: "excluded_publication_format",
      publication_format: "conference_poster",
      reason: "explicit_url_path_segment:posters",
      evidence_url: "https://f1000research.com/posters/5-997",
      trail: ["https://f1000research.com/posters/5-997"],
    },
  );
});
