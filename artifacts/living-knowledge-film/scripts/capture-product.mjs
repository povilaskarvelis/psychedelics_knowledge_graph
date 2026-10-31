// Capture the live Psychedelics Knowledge Graph for the closing sequence.
import puppeteer from 'puppeteer-core';
const browser = await puppeteer.launch({executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new',
  args: ['--hide-scrollbars', '--force-color-profile=srgb']});
const page = await browser.newPage();
await page.setViewport({width: 1600, height: 1000, deviceScaleFactor: 2});
await page.emulateMediaFeatures([{name: 'prefers-color-scheme', value: 'dark'}, {name: 'prefers-reduced-motion', value: 'reduce'}]);
await page.goto('https://psychedelicskg.com/', {waitUntil: 'networkidle0', timeout: 90000});
await new Promise((r) => setTimeout(r, 4000));
await page.screenshot({path: 'public/product/home.png'});
await page.screenshot({path: 'public/product/home-full.png', fullPage: true});
// hover a compound to light up its relationships
const nodes = await page.$$('svg text');
console.log('svg texts', nodes.length);
await page.click('[data-explorer-mode="analysis"]');
await new Promise((r) => setTimeout(r, 5000));
await page.screenshot({path: 'public/product/analyze.png'});
await page.screenshot({path: 'public/product/analyze-full.png', fullPage: true});
await browser.close();
