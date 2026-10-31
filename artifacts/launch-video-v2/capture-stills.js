const {chromium} = require('/Users/frank/Library/Caches/ms-playwright-go/1.57.0/package');
const path = require('path');

const out = path.resolve(__dirname, 'public/assets');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const shot = async (page, name) => {
  await page.screenshot({path: path.join(out, `${name}.png`), animations: 'disabled'});
};

async function run() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args: ['--hide-scrollbars'],
  });
  const page = await browser.newPage({viewport: {width: 1440, height: 900}, deviceScaleFactor: 1});
  await page.goto('http://127.0.0.1:8011/?data-source=local', {waitUntil: 'networkidle', timeout: 120000});
  await page.locator('[data-stat="total-papers"]').waitFor({state: 'visible', timeout: 120000});
  await page.waitForFunction(
    () => document.querySelector('[data-stat="total-papers"]')?.textContent.trim() === '21,735',
    null,
    {timeout: 120000},
  );
  await page.addStyleTag({content: `
    html { scroll-behavior: auto !important; }
    .local-preview-badge, [data-environment-badge] { display: none !important; }
  `});
  await page.evaluate(() => window.scrollTo(0, 0));
  await shot(page, 'explore-home');

  const psilocybinNode = page.locator('#graph text').filter({hasText: /^Psilocybin$/}).first();
  if (await psilocybinNode.isVisible()) {
    await psilocybinNode.click();
    await sleep(700);
  }
  await shot(page, 'explore-psilocybin');

  await page.getByRole('tab', {name: 'Analyze'}).click();
  await page.getByRole('heading', {name: 'Evidence profile'}).waitFor({state: 'visible', timeout: 120000});
  await sleep(700);
  await shot(page, 'analyze-overview');

  const psilocybinButton = page.getByRole('button', {name: /^Psilocybin\s+2,008$/});
  await psilocybinButton.click();
  await sleep(700);
  await shot(page, 'analyze-psilocybin');

  await page.getByRole('heading', {name: 'Publication history'}).scrollIntoViewIfNeeded();
  await sleep(250);
  await shot(page, 'publication-history');

  await page.getByRole('heading', {name: 'Evidence coverage'}).scrollIntoViewIfNeeded();
  await sleep(250);
  await shot(page, 'coverage');

  await browser.close();
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
