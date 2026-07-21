#!/usr/bin/env node
/**
 * Recover article PDFs by following DOI landing pages in Chrome.
 *
 * This complements provider/direct-HTTP retrieval. It starts from doi.org,
 * follows only visible article PDF/full-text controls, and writes downloads to
 * the manual PDF inbox. Canonical promotion and identity validation remain the
 * responsibility of import_manual_pdfs.py.
 */

const fs = require("node:fs");
const dns = require("node:dns").promises;
const net = require("node:net");
const path = require("node:path");
const ROOT = path.resolve(__dirname, "..", "..");
const DEFAULT_DOI_FILE = path.join(
  ROOT,
  "data/processed/corpus/audits/manual_pdf_download_ranked.txt",
);
const DEFAULT_INBOX = path.join(ROOT, "data/raw/papers/manual_pdf_inbox");
const DEFAULT_REPORT = path.join(
  ROOT,
  "data/processed/corpus/audits/doi_browser_pdf_recovery_report.json",
);
const MAX_PDF_BYTES = 128 * 1024 * 1024;

const NON_PUBLIC_ADDRESSES = new net.BlockList();
for (const [network, prefix] of [
  ["0.0.0.0", 8], ["10.0.0.0", 8], ["100.64.0.0", 10], ["127.0.0.0", 8],
  ["169.254.0.0", 16], ["172.16.0.0", 12], ["192.0.0.0", 24], ["192.0.2.0", 24],
  ["192.168.0.0", 16], ["198.18.0.0", 15], ["198.51.100.0", 24], ["203.0.113.0", 24],
  ["224.0.0.0", 4], ["240.0.0.0", 4],
]) NON_PUBLIC_ADDRESSES.addSubnet(network, prefix, "ipv4");
for (const [network, prefix] of [
  ["::", 128], ["::1", 128], ["64:ff9b:1::", 48], ["100::", 64],
  ["2001:2::", 48], ["2001:db8::", 32], ["fc00::", 7], ["fe80::", 10], ["ff00::", 8],
]) NON_PUBLIC_ADDRESSES.addSubnet(network, prefix, "ipv6");

function parseArgs(argv) {
  const args = {
    doiFile: DEFAULT_DOI_FILE,
    inboxDir: DEFAULT_INBOX,
    report: DEFAULT_REPORT,
    limit: 0,
    offset: 0,
    workers: 8,
    timeoutMs: 18000,
    settleMs: 1800,
    maxDepth: 3,
    headless: true,
    preserveOrder: false,
    priorReports: [],
    directUrlCsv: "",
    retryBrowserErrors: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--doi-file") args.doiFile = value, i += 1;
    else if (key === "--inbox-dir") args.inboxDir = value, i += 1;
    else if (key === "--report") args.report = value, i += 1;
    else if (key === "--limit") args.limit = Number(value), i += 1;
    else if (key === "--offset") args.offset = Number(value), i += 1;
    else if (key === "--workers") args.workers = Number(value), i += 1;
    else if (key === "--timeout-ms") args.timeoutMs = Number(value), i += 1;
    else if (key === "--settle-ms") args.settleMs = Number(value), i += 1;
    else if (key === "--max-depth") args.maxDepth = Number(value), i += 1;
    else if (key === "--prior-report") args.priorReports.push(value), i += 1;
    else if (key === "--direct-url-csv") args.directUrlCsv = value, i += 1;
    else if (key === "--preserve-order") args.preserveOrder = true;
    else if (key === "--retry-browser-errors") args.retryBrowserErrors = true;
    else if (key === "--headed") args.headless = false;
    else if (key === "--help" || key === "-h") args.help = true;
    else throw new Error(`Unknown argument: ${key}`);
  }
  return args;
}

function usage() {
  return `Usage: recover_pdfs_via_doi_browser.cjs [options]\n\n` +
    `  --doi-file PATH     One DOI per line\n` +
    `  --inbox-dir PATH    Download destination\n` +
    `  --report PATH       Resumable JSON report\n` +
    `  --limit N           Maximum records (0 = all)\n` +
    `  --offset N          Skip first N input records\n` +
    `  --workers N         Concurrent Chrome pages (default: 8)\n` +
    `  --timeout-ms N      Per-navigation/request timeout\n` +
    `  --settle-ms N       Quiet-page interval after redirects (default: 1800)\n` +
    `  --max-depth N       Maximum PDF/full-text click depth\n` +
    `  --prior-report PATH Reuse completed DOI outcomes (repeatable)\n` +
    `  --direct-url-csv PATH  CSV with doi and direct_pdf_url; try these before landing-page navigation\n` +
    `  --preserve-order    Disable DOI-prefix round-robin scheduling\n` +
    `  --retry-browser-errors  Retry prior browser/navigation errors\n` +
    `  --headed            Show Chrome windows`;
}

function normalizeDoi(value) {
  return String(value || "")
    .trim()
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "")
    .replace(/^doi:\s*/i, "")
    .toLowerCase();
}

function directUrlsByDoiFromCsv(csvPath) {
  if (!csvPath || !fs.existsSync(csvPath)) return new Map();
  const lines = fs.readFileSync(csvPath, "utf8").split(/\r?\n/).filter((line) => line.trim());
  if (!lines.length) return new Map();
  const header = lines.shift().split(",").map((value) => value.trim().toLowerCase());
  const doiIndex = header.indexOf("doi");
  const urlIndex = ["direct_pdf_url", "known_pdf_url", "pdf_url", "explicit_pdf_url", "direct_url", "route_url"]
    .map((name) => header.indexOf(name))
    .find((index) => index >= 0);
  if (doiIndex < 0 || urlIndex == null) {
    throw new Error("--direct-url-csv must contain DOI and direct_pdf_url columns");
  }
  const byDoi = new Map();
  for (const line of lines) {
    // Queue artifacts deliberately place DOI and direct URL before any free-text
    // fields, so parsing those two URL-safe CSV columns does not need a general
    // purpose CSV dependency.
    const values = line.split(",");
    const doi = normalizeDoi(values[doiIndex]);
    const url = cleanUrl(values[urlIndex]);
    if (!doi || !url) continue;
    if (!byDoi.has(doi)) byDoi.set(doi, []);
    if (!byDoi.get(doi).includes(url)) byDoi.get(doi).push(url);
  }
  return byDoi;
}

function outputName(doi) {
  const stem = doi.replace(/[^a-z0-9._()-]+/gi, "_").replace(/^_+|_+$/g, "");
  return `${stem}__doi_browser.pdf`;
}

function interleaveByPrefix(dois) {
  const buckets = new Map();
  for (const doi of dois) {
    const prefix = doi.split("/", 1)[0];
    if (!buckets.has(prefix)) buckets.set(prefix, []);
    buckets.get(prefix).push(doi);
  }
  const orderedBuckets = Array.from(buckets.values()).sort((left, right) => right.length - left.length);
  const output = [];
  while (orderedBuckets.some((bucket) => bucket.length)) {
    for (const bucket of orderedBuckets) {
      if (bucket.length) output.push(bucket.shift());
    }
  }
  return output;
}

function isPdfBuffer(buffer) {
  return Buffer.isBuffer(buffer) && buffer.length >= 5 && buffer.subarray(0, 5).toString() === "%PDF-";
}

function cleanUrl(value) {
  try {
    const url = new URL(value);
    if (!/^https?:$/.test(url.protocol)) return "";
    url.hash = "";
    return url.href;
  } catch {
    return "";
  }
}

function isPublicIpAddress(value) {
  const address = String(value || "").split("%", 1)[0];
  const mapped = address.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/i);
  if (mapped) return !NON_PUBLIC_ADDRESSES.check(mapped[1], "ipv4");
  const family = net.isIP(address);
  if (!family) return false;
  return !NON_PUBLIC_ADDRESSES.check(address, family === 4 ? "ipv4" : "ipv6");
}

async function isPublicHttpUrl(value, lookup = dns.lookup) {
  const cleaned = cleanUrl(value);
  if (!cleaned) return false;
  const url = new URL(cleaned);
  if (url.username || url.password) return false;
  const hostname = url.hostname.replace(/^\[|\]$/g, "").replace(/\.$/, "").toLowerCase();
  if (hostname === "localhost" || hostname.endsWith(".localhost")) return false;
  if (net.isIP(hostname)) return isPublicIpAddress(hostname);
  try {
    const records = await lookup(hostname, { all: true, verbatim: true });
    return records.length > 0 && records.every((record) => isPublicIpAddress(record.address));
  } catch {
    return false;
  }
}

function createPublicUrlGate(lookup = dns.lookup) {
  const cache = new Map();
  return async (value) => {
    const cleaned = cleanUrl(value);
    if (!cleaned) return false;
    const hostname = new URL(cleaned).hostname.toLowerCase();
    if (!cache.has(hostname)) cache.set(hostname, isPublicHttpUrl(cleaned, lookup));
    return await cache.get(hostname);
  };
}

/**
 * Return authoritative publication-format evidence encoded by a landing URL.
 *
 * Only exact path segments are eligible here.  Substring matching would turn
 * ordinary article URLs containing words such as "posterior" into exclusions,
 * while query parameters and link text are not authoritative enough on their
 * own.  Conference proceedings and abstract-collection paths are deliberately
 * left for document/page inspection because they can also contain full papers.
 */
function deterministicPublicationFormatFromUrl(value) {
  const cleaned = cleanUrl(value);
  if (!cleaned) return null;
  const url = new URL(cleaned);
  const segments = url.pathname
    .split("/")
    .map((segment) => {
      try { return decodeURIComponent(segment).trim().toLowerCase(); }
      catch { return segment.trim().toLowerCase(); }
    })
    .filter(Boolean);
  const posterSegment = segments.find((segment) => segment === "poster" || segment === "posters");
  if (!posterSegment) return null;
  return {
    publication_format: "conference_poster",
    reason: `explicit_url_path_segment:${posterSegment}`,
    evidence_url: cleaned,
  };
}

function urlFormatExclusion(doi, pageUrl, trail = []) {
  const evidence = deterministicPublicationFormatFromUrl(pageUrl);
  if (!evidence) return null;
  return {
    doi,
    status: "excluded_publication_format",
    ...evidence,
    trail: trail.includes(pageUrl) ? trail : [...trail, pageUrl],
  };
}

function hostFamily(hostname) {
  const parts = String(hostname || "").toLowerCase().split(".").filter(Boolean);
  if (parts.length <= 2) return parts.join(".");
  const countrySecondLevels = new Set(["co.uk", "ac.uk", "com.au", "co.jp", "com.br"]);
  const lastTwo = parts.slice(-2).join(".");
  return countrySecondLevels.has(lastTwo) ? parts.slice(-3).join(".") : lastTwo;
}

function trustedArticleCdn(hostname) {
  return /(?:silverchair|els-cdn|sciencedirect|cambridge|wiley|springernature|nature|sagepub|tandfonline|oup|oxfordjournals|jamanetwork|cloudfront)\./i.test(hostname);
}

function candidateScore(candidate, pageUrl) {
  const text = `${candidate.text || ""} ${candidate.title || ""} ${candidate.aria || ""}`.toLowerCase();
  const href = String(candidate.href || "").toLowerCase();
  let score = 0;
  if (/\.pdf(?:$|[?#])/.test(href)) score += 100;
  if (/(?:\/|=)(?:pdf|pdfdirect|articlepdf)(?:\/|$|[?&])/i.test(href)) score += 75;
  if (/\b(download|view|open)\s+(?:the\s+)?pdf\b/.test(text)) score += 90;
  else if (/\bpdf\b/.test(text)) score += 70;
  if (/\bfull\s*text\b/.test(text)) score += 45;
  if (/\bdownload\b/.test(text)) score += 35;
  if (/citation_pdf_url|type=application%2fpdf/.test(href)) score += 80;
  if (candidate.kind === "meta" || candidate.kind === "link") score += 80;
  if (/supplement|supporting|appendix|poster|cover|issue|toc|citation|reference|metric/.test(`${text} ${href}`)) score -= 140;
  if (/purchase|buy|rent|subscribe|sign\s*in|login/.test(text)) score -= 100;
  try {
    const pageHost = new URL(pageUrl).hostname;
    const candidateHost = new URL(candidate.href).hostname;
    const samePublisherFamily = hostFamily(pageHost) === hostFamily(candidateHost);
    if (candidate.kind === "anchor" && !samePublisherFamily && !trustedArticleCdn(candidateHost)) score -= 180;
  } catch {
    score -= 180;
  }
  return score;
}

async function writeJsonAtomic(target, payload) {
  await fs.promises.mkdir(path.dirname(target), { recursive: true });
  const tmp = `${target}.${process.pid}.tmp`;
  await fs.promises.writeFile(tmp, `${JSON.stringify(payload, null, 2)}\n`);
  await fs.promises.rename(tmp, target);
}

let reportWriteChain = Promise.resolve();

function writeReportSerially(target, payload) {
  const snapshot = JSON.parse(JSON.stringify(payload));
  reportWriteChain = reportWriteChain.then(() => writeJsonAtomic(target, snapshot));
  return reportWriteChain;
}

async function savePdfBuffer(buffer, target) {
  if (!isPdfBuffer(buffer) || buffer.length > MAX_PDF_BYTES) return false;
  await fs.promises.mkdir(path.dirname(target), { recursive: true });
  const tmp = `${target}.part`;
  await fs.promises.writeFile(tmp, buffer);
  await fs.promises.rename(tmp, target);
  return true;
}

async function responsePdf(response, target) {
  if (!response) return false;
  const headers = response.headers();
  const contentType = String(headers["content-type"] || "").toLowerCase();
  const disposition = String(headers["content-disposition"] || "").toLowerCase();
  const declaredLength = Number(headers["content-length"] || 0);
  if (Number.isFinite(declaredLength) && declaredLength > MAX_PDF_BYTES) return false;
  if (!contentType.includes("pdf") && !disposition.includes(".pdf") && !/\.pdf(?:$|[?#])/i.test(response.url())) {
    return false;
  }
  try {
    return await savePdfBuffer(await response.body(), target);
  } catch {
    return false;
  }
}

async function requestPdf(context, url, referer, target, timeoutMs, isAllowedUrl) {
  try {
    let currentUrl = cleanUrl(url);
    let response = null;
    for (let redirects = 0; redirects <= 10; redirects += 1) {
      if (!currentUrl || !(await isAllowedUrl(currentUrl))) return false;
      response = await context.request.get(currentUrl, {
        headers: referer ? { referer } : {},
        timeout: timeoutMs,
        failOnStatusCode: false,
        maxRedirects: 0,
      });
      const location = String(response.headers().location || "").trim();
      if (response.status() >= 300 && response.status() < 400 && location) {
        if (redirects >= 10) return false;
        currentUrl = cleanUrl(new URL(location, response.url()).href);
        continue;
      }
      break;
    }
    if (!response) return false;
    const headers = response.headers();
    const contentType = String(headers["content-type"] || "").toLowerCase();
    const disposition = String(headers["content-disposition"] || "").toLowerCase();
    const declaredLength = Number(headers["content-length"] || 0);
    if (Number.isFinite(declaredLength) && declaredLength > MAX_PDF_BYTES) return false;
    if (!response.ok()) return false;
    // Some public repository APIs (notably DSpace deployments) serve actual
    // PDF bytes with a generic or even JSON MIME label.  The byte-level PDF
    // signature remains the decisive validation in savePdfBuffer(), so do not
    // discard a bounded, successful response solely because its header is
    // inaccurate.
    const headerIndicatesPdf = contentType.includes("pdf")
      || disposition.includes(".pdf")
      || /\.pdf(?:$|[?#])/i.test(response.url());
    const body = await response.body();
    if (!headerIndicatesPdf && !isPdfBuffer(body)) return false;
    return await savePdfBuffer(body, target);
  } catch {
    return false;
  }
}

async function pageCandidates(page) {
  return await page.evaluate(() => {
    const candidates = [];
    const seen = new Set();
    const add = (href, text, title, aria, kind) => {
      if (!href) return;
      let absolute = "";
      try { absolute = new URL(href, document.baseURI).href; } catch { return; }
      if (!/^https?:/i.test(absolute) || seen.has(absolute)) return;
      seen.add(absolute);
      candidates.push({ href: absolute, text, title, aria, kind });
    };
    for (const meta of document.querySelectorAll('meta[name="citation_pdf_url"], meta[name="wkhealth_pdf_url"], meta[property="og:pdf"]')) {
      add(meta.content, "citation pdf", "", "", "meta");
    }
    for (const link of document.querySelectorAll('link[type="application/pdf"], link[rel="alternate"][href*="pdf"]')) {
      add(link.href, "linked pdf", link.title || "", "", "link");
    }
    for (const anchor of document.querySelectorAll("a[href]")) {
      add(
        anchor.href,
        (anchor.innerText || anchor.textContent || "").trim().slice(0, 300),
        anchor.getAttribute("title") || "",
        anchor.getAttribute("aria-label") || "",
        "anchor",
      );
    }
    return candidates;
  });
}

function transientNavigationError(error) {
  const message = String(error && error.message || error || "");
  return /Execution context was destroyed|navigation|Timeout .* exceeded|ERR_ABORTED/i.test(message);
}

async function waitForStablePage(page, timeoutMs, settleMs) {
  await page.waitForLoadState("domcontentloaded", { timeout: Math.min(timeoutMs, 10000) }).catch(() => {});
  let previousUrl = "";
  let stableIntervals = 0;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline && stableIntervals < 2) {
    await page.waitForTimeout(settleMs);
    const currentUrl = page.url();
    if (currentUrl && currentUrl === previousUrl) stableIntervals += 1;
    else stableIntervals = 0;
    previousUrl = currentUrl;
  }
}

async function gotoStable(page, url, timeoutMs, settleMs) {
  let response = null;
  let navigationError = null;
  try {
    response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
  } catch (error) {
    navigationError = error;
    if (!transientNavigationError(error)) throw error;
  }
  await waitForStablePage(page, timeoutMs, settleMs);
  const usablePage = page.url() && page.url() !== "about:blank"
    && await page.locator("body").count().catch(() => 0) > 0;
  if (!usablePage && navigationError) throw navigationError;
  return response;
}

async function stablePageCandidates(page, timeoutMs, settleMs) {
  let lastError = null;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      await waitForStablePage(page, Math.min(timeoutMs, 8000), settleMs);
      return await pageCandidates(page);
    } catch (error) {
      lastError = error;
      if (!transientNavigationError(error)) throw error;
    }
  }
  throw lastError || new Error("Unable to inspect the settled article page");
}

function platformPdfSelectors(hostname) {
  const host = String(hostname || "").toLowerCase();
  const common = [
    'a[href*="/pdf/"]',
    'a[href*="/epdf/"]',
    'a[href*="/pdfdirect/"]',
    'a[href*="article-pdf"]',
    'a[href$=".pdf"]',
    'a[aria-label*="pdf" i]',
    'a[title*="pdf" i]',
  ];
  if (host.includes("academic.oup.com")) return ['a.article-pdfLink', 'a[href*="article-pdf"]', ...common];
  if (host.includes("wiley.com")) return ['a.pdf-download', 'a[href*="/doi/pdfdirect/"]', 'a[href*="/doi/epdf/"]', ...common];
  if (host.includes("sagepub.com")) return ['a[href*="/doi/pdf/"]', 'a[href*="/doi/epdf/"]', ...common];
  if (host.includes("tandfonline.com")) return ['a.show-pdf', 'a[href*="/doi/pdf/"]', ...common];
  if (host.includes("lww.com")) return ['a[aria-label*="PDF" i]', 'a[title*="PDF" i]', ...common];
  if (host.includes("zenodo.org")) return ['a[href*="/files/"]', 'a[download]', ...common];
  if (host.includes("sciencedirect.com")) return ['a.pdf-download-btn-link', 'a[href*="/pdfft"]', ...common];
  return common;
}

async function clickLocatorForPdf(page, context, locator, target, timeoutMs, isAllowedUrl) {
  const eventTimeout = Math.min(timeoutMs, 15000);
  const downloadPromise = page.waitForEvent("download", { timeout: eventTimeout })
    .then((value) => ({ kind: "download", value })).catch(() => null);
  const responsePromise = page.waitForResponse(
    (response) => String(response.headers()["content-type"] || "").toLowerCase().includes("pdf"),
    { timeout: eventTimeout },
  ).then((value) => ({ kind: "response", value })).catch(() => null);
  const popupPromise = context.waitForEvent("page", { timeout: eventTimeout })
    .then((value) => ({ kind: "popup", value })).catch(() => null);
  const navigationPromise = page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: eventTimeout })
    .then((value) => ({ kind: "navigation", value })).catch(() => null);
  try {
    await locator.click({ timeout: eventTimeout });
  } catch {
    return false;
  }
  const event = await Promise.race([
    downloadPromise,
    responsePromise,
    popupPromise,
    navigationPromise,
    page.waitForTimeout(eventTimeout).then(() => null),
  ]);
  if (event && event.kind === "download") {
    const downloadPath = await event.value.path().catch(() => null);
    const fileSize = downloadPath ? (await fs.promises.stat(downloadPath).catch(() => null))?.size : 0;
    const header = downloadPath && fileSize <= MAX_PDF_BYTES
      ? await fs.promises.readFile(downloadPath).then((body) => body.subarray(0, 5)).catch(() => null)
      : null;
    if (downloadPath && fileSize > 0 && fileSize <= MAX_PDF_BYTES && isPdfBuffer(header)) {
      await event.value.saveAs(target);
      return true;
    }
  }
  if (event && event.kind === "response" && await responsePdf(event.value, target)) return true;
  if (event && event.kind === "navigation" && await responsePdf(event.value, target)) return true;
  if (event && event.kind === "popup") {
    const popup = event.value;
    await popup.waitForLoadState("domcontentloaded", { timeout: eventTimeout }).catch(() => {});
    if (await requestPdf(context, popup.url(), page.url(), target, eventTimeout, isAllowedUrl)) {
      await popup.close().catch(() => {});
      return true;
    }
    await popup.close().catch(() => {});
  }
  return await requestPdf(context, page.url(), page.url(), target, eventTimeout, isAllowedUrl);
}

async function clickFallback(page, context, target, timeoutMs, isAllowedUrl) {
  const patterns = [
    /download\s+(?:the\s+)?pdf/i,
    /view\s+(?:the\s+)?pdf/i,
    /open\s+(?:the\s+)?pdf/i,
    /^pdf$/i,
    /full\s*text/i,
  ];
  const seen = new Set();
  for (const selector of platformPdfSelectors(new URL(page.url()).hostname)) {
    const matches = page.locator(selector);
    const count = Math.min(await matches.count().catch(() => 0), 5);
    for (let index = 0; index < count; index += 1) {
      const locator = matches.nth(index);
      if (!(await locator.isVisible().catch(() => false))) continue;
      const href = await locator.getAttribute("href").catch(() => "");
      const key = `${selector}\u241f${href}`;
      if (seen.has(key)) continue;
      seen.add(key);
      if (await clickLocatorForPdf(page, context, locator, target, timeoutMs, isAllowedUrl)) return true;
    }
  }
  for (const pattern of patterns) {
    for (const role of ["link", "button"]) {
      const locator = page.getByRole(role, { name: pattern }).first();
      if (await locator.count() === 0 || !(await locator.isVisible().catch(() => false))) continue;
      if (await clickLocatorForPdf(page, context, locator, target, timeoutMs, isAllowedUrl)) return true;
    }
  }
  return false;
}

async function recoverOne(browser, doi, args, directUrls = []) {
  const target = path.join(args.inboxDir, outputName(doi));
  if (fs.existsSync(target)) return { doi, status: "already_in_inbox", target };
  const context = await browser.newContext({
    acceptDownloads: true,
    userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0 Safari/537.36",
  });
  const isAllowedUrl = createPublicUrlGate();
  await context.route("**/*", async (route) => {
    const requestUrl = route.request().url();
    if (/^(?:about|blob|data):/i.test(requestUrl) || await isAllowedUrl(requestUrl)) {
      await route.continue();
    } else {
      await route.abort("blockedbyclient");
    }
  });
  const page = await context.newPage();
  page.setDefaultTimeout(args.timeoutMs);
  const visited = new Set();
  const trail = [];
  try {
    for (const directUrl of directUrls) {
      const formatExclusion = urlFormatExclusion(doi, directUrl, []);
      if (formatExclusion) return formatExclusion;
      if (await requestPdf(
        context,
        directUrl,
        `https://doi.org/${doi}`,
        target,
        args.timeoutMs,
        isAllowedUrl,
      )) {
        return {
          doi,
          status: "downloaded",
          target,
          trail: [directUrl],
          selected_url: directUrl,
          selected_via: "curated_direct_pdf_url",
        };
      }
    }
    let response = await gotoStable(
      page,
      `https://doi.org/${doi}`,
      args.timeoutMs,
      args.settleMs,
    );
    const initialFormatExclusion = urlFormatExclusion(doi, page.url(), trail);
    if (initialFormatExclusion) return initialFormatExclusion;
    if (await responsePdf(response, target)) return { doi, status: "downloaded", target, trail: [page.url()] };
    for (let depth = 0; depth < args.maxDepth; depth += 1) {
      const pageUrl = page.url();
      trail.push(pageUrl);
      const formatExclusion = urlFormatExclusion(doi, pageUrl, trail);
      if (formatExclusion) return formatExclusion;
      visited.add(pageUrl);
      const ranked = (await stablePageCandidates(page, args.timeoutMs, args.settleMs))
        .map((candidate) => ({ ...candidate, score: candidateScore(candidate, pageUrl) }))
        .filter((candidate) => candidate.score >= 35 && !visited.has(candidate.href))
        .sort((left, right) => right.score - left.score)
        .slice(0, 10);

      for (const candidate of ranked) {
        if (await requestPdf(context, candidate.href, pageUrl, target, args.timeoutMs, isAllowedUrl)) {
          return {
            doi,
            status: "downloaded",
            target,
            trail,
            selected_url: candidate.href,
            selected_score: candidate.score,
            selected_text: candidate.text,
            selected_kind: candidate.kind,
          };
        }
      }

      if (await clickFallback(page, context, target, args.timeoutMs, isAllowedUrl)) {
        return { doi, status: "downloaded", target, trail, selected_via: "visible_pdf_control" };
      }

      const next = ranked.find((candidate) => candidate.score >= 45);
      if (next) {
        visited.add(next.href);
        response = await gotoStable(page, next.href, args.timeoutMs, args.settleMs).catch(() => null);
        const navigatedFormatExclusion = urlFormatExclusion(doi, page.url(), trail);
        if (navigatedFormatExclusion) return navigatedFormatExclusion;
        if (await responsePdf(response, target)) {
          return { doi, status: "downloaded", target, trail, selected_url: next.href, selected_score: next.score };
        }
        continue;
      }
      break;
    }
    const bodyText = (await page.locator("body").innerText({ timeout: 3000 }).catch(() => "")).toLowerCase();
    const accessHint = /purchase|buy article|rent article|institutional access|subscribe to access|sign in to access/.test(bodyText)
      ? "paywall_detected"
      : "no_pdf_control_found";
    return { doi, status: "not_recovered", reason: accessHint, trail };
  } catch (error) {
    return { doi, status: "browser_error", error: String(error && error.message || error), trail };
  } finally {
    await context.close().catch(() => {});
  }
}

async function main() {
  const { chromium } = require("playwright");
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  const allDois = Array.from(new Set(
    fs.readFileSync(args.doiFile, "utf8").split(/\r?\n/).map(normalizeDoi).filter((doi) => doi.startsWith("10.")),
  ));
  const scheduled = args.preserveOrder ? allDois : interleaveByPrefix(allDois);
  const sliced = scheduled.slice(Math.max(0, args.offset), args.limit > 0 ? args.offset + args.limit : undefined);
  await fs.promises.mkdir(args.inboxDir, { recursive: true });
  const directUrlsByDoi = directUrlsByDoiFromCsv(args.directUrlCsv);

  const priorPaths = [args.report, ...args.priorReports].filter((value, index, values) => value && values.indexOf(value) === index);
  const priorByDoi = new Map();
  for (const priorPath of priorPaths) {
    if (!fs.existsSync(priorPath)) continue;
    const prior = JSON.parse(fs.readFileSync(priorPath, "utf8"));
    for (const record of [...(prior.records || []), ...(prior.results || [])]) {
      const doi = normalizeDoi(record.doi);
      if (doi) priorByDoi.set(doi, { ...record, doi });
    }
  }
  const terminal = new Set(["downloaded", "already_in_inbox"]);
  const pending = sliced.filter((doi) => {
    const prior = priorByDoi.get(doi);
    return !prior || (args.retryBrowserErrors && prior.status === "browser_error");
  });
  const records = sliced
    .filter((doi) => {
      const prior = priorByDoi.get(doi);
      return prior && !(args.retryBrowserErrors && prior.status === "browser_error");
    })
    .map((doi) => priorByDoi.get(doi));
  const browser = await chromium.launch({ channel: "chrome", headless: args.headless });
  let cursor = 0;
  const workers = Array.from({ length: Math.max(1, args.workers) }, async () => {
    while (true) {
      const position = cursor;
      cursor += 1;
      if (position >= pending.length) return;
      const doi = pending[position];
      const record = await recoverOne(browser, doi, args, directUrlsByDoi.get(doi) || []);
      records.push(record);
      const completed = records.length;
      const downloaded = records.filter((item) => terminal.has(item.status)).length;
      process.stdout.write(`PROGRESS ${completed}/${sliced.length} downloaded=${downloaded} doi=${doi} status=${record.status}\n`);
      await writeReportSerially(args.report, {
        schema_version: "doi_browser_pdf_recovery_v1",
        complete: completed >= sliced.length,
        inputs: { ...args, doiFile: path.resolve(args.doiFile), inboxDir: path.resolve(args.inboxDir) },
        counts: {
          scope: sliced.length,
          completed,
          downloaded,
          not_recovered: records.filter((item) => item.status === "not_recovered").length,
          excluded_publication_format: records.filter(
            (item) => item.status === "excluded_publication_format",
          ).length,
          browser_error: records.filter((item) => item.status === "browser_error").length,
        },
        records: records.sort((a, b) => sliced.indexOf(a.doi) - sliced.indexOf(b.doi)),
      });
    }
  });
  await Promise.all(workers);
  await reportWriteChain;
  await browser.close();
}

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`${error.stack || error}\n`);
    process.exitCode = 1;
  });
}

module.exports = {
  isPublicHttpUrl,
  deterministicPublicationFormatFromUrl,
  urlFormatExclusion,
};
