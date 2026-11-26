// Dev tool: renders the extension icons and the offer image used by the tests.
// Run with: node tools/make-assets.mjs (needs Playwright with Chromium, dev only).
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const iconHtml = (size) => `<!doctype html><body style="margin:0;background:transparent">
<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#00745f"/>
  <path d="M30 34h68a8 8 0 0 1 8 8v36a8 8 0 0 1-8 8H62l-20 16V86H30a8 8 0 0 1-8-8V42a8 8 0 0 1 8-8z" fill="#fff"/>
  <text x="64" y="72" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-weight="700" font-size="34" fill="#00745f">EC</text>
</svg></body>`;

const offerHtml = `<!doctype html><body style="margin:0;font-family:Arial,Helvetica,sans-serif;background:#f4f1ea;width:800px;height:500px">
<div style="padding:44px 52px">
  <div style="font-size:20px;color:#00745f;font-weight:700;letter-spacing:1px">ETICHETE CREATIVE</div>
  <div style="font-size:38px;font-weight:700;margin-top:10px;color:#1c2529">Etichete rotunde 50 mm</div>
  <div style="font-size:21px;color:#55636b;margin-top:6px">Hartie lucioasa, laminare mata</div>
  <div style="display:flex;gap:22px;margin-top:40px">
    <div style="flex:1;background:#fff;border-radius:16px;padding:22px 24px"><div style="color:#55636b;font-size:18px">500 buc</div><div style="font-size:32px;font-weight:700;margin-top:6px">214,20 lei</div></div>
    <div style="flex:1;background:#00745f;color:#fff;border-radius:16px;padding:22px 24px"><div style="font-size:18px;opacity:.85">1000 buc</div><div style="font-size:32px;font-weight:700;margin-top:6px">333,20 lei</div></div>
    <div style="flex:1;background:#fff;border-radius:16px;padding:22px 24px"><div style="color:#55636b;font-size:18px">2000 buc</div><div style="font-size:32px;font-weight:700;margin-top:6px">547,40 lei</div></div>
  </div>
  <div style="margin-top:34px;color:#55636b;font-size:18px">Imagine de test pentru extensie. Preturi fictive.</div>
</div></body>`;

const browser = await chromium.launch();
const page = await browser.newPage();
for (const size of [16, 32, 48, 128]) {
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(iconHtml(size));
  await page.screenshot({ path: path.join(root, 'icons', `icon${size}.png`), omitBackground: true });
}
await page.setViewportSize({ width: 800, height: 500 });
await page.setContent(offerHtml);
await page.screenshot({ path: path.join(root, 'tests', 'fixtures', 'offer.png') });
await browser.close();
console.log('assets written');
