const { chromium } = require('/Users/frank/Library/Caches/ms-playwright-go/1.57.0/package');
const fs = require('fs');
const path = require('path');

const outputDir = path.resolve(__dirname, 'capture');
fs.mkdirSync(outputDir, { recursive: true });

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function centerOf(locator) {
  const box = await locator.boundingBox();
  if (!box) throw new Error('Target is not visible');
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

async function moveCursor(page, locator, duration = 650) {
  const point = await centerOf(locator);
  await page.evaluate(({ x, y, duration }) => {
    const cursor = document.querySelector('[data-launch-cursor]');
    cursor.style.transitionDuration = `${duration}ms`;
    cursor.style.transform = `translate(${x - 10}px, ${y - 10}px)`;
  }, { ...point, duration });
  await sleep(duration + 120);
}

async function clickWithCursor(page, locator) {
  await moveCursor(page, locator);
  await page.evaluate(() => {
    const cursor = document.querySelector('[data-launch-cursor]');
    cursor.classList.add('is-clicking');
    setTimeout(() => cursor.classList.remove('is-clicking'), 260);
  });
  await locator.click();
  await sleep(900);
}

async function addCapturePolish(page) {
  await page.addStyleTag({ content: `
    html { scroll-behavior: smooth !important; }
    body { cursor: none !important; }
    [data-launch-cursor] {
      position: fixed;
      inset: 0 auto auto 0;
      width: 20px;
      height: 20px;
      border: 2px solid rgba(255,255,255,.96);
      border-radius: 999px;
      background: rgba(30, 105, 91, .88);
      box-shadow: 0 2px 12px rgba(15, 23, 42, .35), 0 0 0 1px rgba(15, 23, 42, .32);
      z-index: 2147483647;
      pointer-events: none;
      transition: transform 650ms cubic-bezier(.22,.8,.26,1), width 180ms ease, height 180ms ease, margin 180ms ease, background 180ms ease;
      transform: translate(1180px, 650px);
    }
    [data-launch-cursor].is-clicking {
      width: 32px;
      height: 32px;
      margin: -6px;
      background: rgba(88, 180, 155, .6);
    }
    .local-preview-badge, [data-environment-badge] { display: none !important; }
  ` });
  await page.evaluate(() => {
    const cursor = document.createElement('div');
    cursor.dataset.launchCursor = '';
    document.body.appendChild(cursor);
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      if (walker.currentNode.nodeValue?.trim() === 'Local preview') {
        walker.currentNode.parentElement.style.display = 'none';
      }
    }
  });
}

async function run() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args: ['--hide-scrollbars', '--disable-background-timer-throttling'],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    colorScheme: 'light',
    recordVideo: { dir: outputDir, size: { width: 1440, height: 900 } },
  });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:8011/?data-source=local', { waitUntil: 'networkidle', timeout: 120000 });
  await page.locator('[data-stat="total-papers"]').waitFor({ state: 'visible', timeout: 120000 });
  await page.waitForFunction(() => document.querySelector('[data-stat="total-papers"]')?.textContent.trim() === '21,735', null, { timeout: 120000 });
  await addCapturePolish(page);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  await sleep(2600);

  const psilocybinNode = page.locator('#graph text').filter({ hasText: /^Psilocybin$/ }).first();
  if (await psilocybinNode.isVisible()) {
    await clickWithCursor(page, psilocybinNode);
    await sleep(1900);
  }

  const analyze = page.getByRole('tab', { name: 'Analyze' });
  await clickWithCursor(page, analyze);
  await page.getByRole('heading', { name: 'Evidence profile' }).waitFor({ state: 'visible', timeout: 120000 });
  await sleep(3400);

  const psilocybinButton = page.getByRole('button', { name: /^Psilocybin\s+2,008$/ });
  await clickWithCursor(page, psilocybinButton);
  await sleep(3600);

  const publicationHistory = page.getByRole('heading', { name: 'Publication history' });
  await publicationHistory.scrollIntoViewIfNeeded();
  await sleep(3300);

  const coverage = page.getByRole('heading', { name: 'Evidence coverage' });
  await coverage.scrollIntoViewIfNeeded();
  await sleep(3600);

  const cell = page.getByRole('checkbox', { name: /Human participants, RCT:/ }).first();
  if (await cell.isVisible()) {
    await clickWithCursor(page, cell);
    await sleep(1600);
  }

  await page.getByRole('heading', { name: 'Findings' }).scrollIntoViewIfNeeded();
  await sleep(3600);

  const video = page.video();
  await context.close();
  const videoPath = await video.path();
  const finalPath = path.join(outputDir, 'preview-raw.webm');
  fs.copyFileSync(videoPath, finalPath);
  await browser.close();
  console.log(finalPath);
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
