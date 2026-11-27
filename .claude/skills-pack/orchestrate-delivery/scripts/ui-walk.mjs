#!/usr/bin/env node
// ui-walk.mjs: open the app in a real browser and walk it like a first-time tester.
//
//   node <kit>/orchestrate-delivery/scripts/ui-walk.mjs --url http://localhost:5173 \
//        --out .claude/skills-pack/.run-notes/ui-walk [--role admin --role staff] \
//        [--login-url /login] [--max-pages 25] [--depth 2] \
//        [--viewports 1440x900,390x844] [--headed] [--slow-mo 250]
//
// For every role (credentials from E2E_<ROLE>_EMAIL / E2E_<ROLE>_PASSWORD, plus an
// anonymous pass) and every viewport it: signs in through the real login form,
// follows same-origin links breadth-first (GET only; logout/delete-like links are
// never followed, no button is ever clicked), and on each page records the HTTP
// status, a screenshot, console errors, uncaught exceptions, failed requests,
// horizontal overflow, broken images, leaked placeholders (undefined, NaN, i18n
// keys), axe serious/critical violations, and an inventory of headings, forms,
// fields, and buttons.
//
// Writes <out>/ui-map.json (routes and inventory: the map ui-test builds charters
// from), <out>/report.md, <out>/report.html (self-contained, thumbnails embedded),
// and <out>/shots/*.png. Exit 0 when the walk ran (findings are in the report),
// 2 when the URL never answered, 3 when no browser could be launched.
//
// Browser: the first that launches of $PW_EXECUTABLE, Playwright's own Chromium,
// the system Chrome (channel "chrome"), and @sparticuz/chromium (an npm-bundled
// Chromium for sandboxes that block Playwright's browser download).
// --headed opens a visible window when the machine has a display.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(path.join(process.cwd(), 'noop.js'));

// ------------------------------------------------------------------ args
const args = { role: [], viewports: '1440x900,390x844', 'max-pages': '25', depth: '2', 'slow-mo': '0' };
for (let i = 2; i < process.argv.length; i++) {
  const a = process.argv[i];
  if (!a.startsWith('--')) continue;
  const key = a.slice(2);
  if (key === 'headed') { args.headed = true; continue; }
  const val = process.argv[++i];
  if (key === 'role') args.role.push(val); else args[key] = val;
}
if (!args.url) {
  console.error('usage: ui-walk.mjs --url <app url> [--out dir] [--role r ...] [--login-url path] [--headed]');
  process.exit(64);
}
const BASE = new URL(args.url);
const OUT = path.resolve(args.out || '.claude/skills-pack/.run-notes/ui-walk');
const SHOTS = path.join(OUT, 'shots');
fs.mkdirSync(SHOTS, { recursive: true });
const MAX_PAGES = Number(args['max-pages']);
const DEPTH = Number(args.depth);
const VIEWPORTS = args.viewports.split(',').map((v) => { const [w, h] = v.split('x').map(Number); return { width: w, height: h, name: v }; });
const UNSAFE = /log-?out|sign-?out|logoff|delete|remove|destroy|unsubscribe|deconect|iesire|ieșire|sterge|șterge|elimina|anuleaz|cancel-account|\.(pdf|zip|csv|xlsx|docx)(\?|$)/i;

// ------------------------------------------------------------------ browser
function tryRequire(name) { try { return require(name); } catch { return null; } }
const pw = tryRequire('@playwright/test') || tryRequire('playwright');
if (!pw) { console.error('Playwright is not installed in this project: npm i -D @playwright/test'); process.exit(3); }
const axeMod = tryRequire('@axe-core/playwright');
const AxeBuilder = axeMod && (axeMod.default || axeMod.AxeBuilder || axeMod);

async function launch() {
  const headless = !args.headed;
  const slowMo = Number(args['slow-mo']) || (args.headed ? 250 : 0);
  const attempts = [];
  if (process.env.PW_EXECUTABLE) attempts.push(['$PW_EXECUTABLE', { executablePath: process.env.PW_EXECUTABLE }]);
  attempts.push(['playwright chromium', {}]);
  attempts.push(['system chrome', { channel: 'chrome' }]);
  const sparticuz = tryRequire('@sparticuz/chromium');
  if (sparticuz) {
    const s = sparticuz.default || sparticuz;
    attempts.push(['@sparticuz/chromium', async () => ({ executablePath: await s.executablePath(), args: s.args })]);
  }
  const errors = [];
  for (const [name, opt] of attempts) {
    try {
      const o = typeof opt === 'function' ? await opt() : opt;
      const browser = await pw.chromium.launch({ headless, slowMo, ...o });
      return { browser, name };
    } catch (e) { errors.push(`${name}: ${String(e.message).split('\n')[0]}`); }
  }
  console.error('No browser could be launched:\n  ' + errors.join('\n  ') +
    '\nFix: npx playwright install chromium, or set PW_EXECUTABLE, or npm i -D @sparticuz/chromium in a sandbox.');
  process.exit(3);
}

// ------------------------------------------------------------------ helpers
const slug = (u) => (new URL(u).pathname.replace(/\/+$/, '') || '/home').replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').slice(0, 60) || 'home';
const norm = (u) => { const x = new URL(u, BASE); x.hash = ''; return x.toString(); };

async function waitForApp() {
  const tries = Math.max(1, Math.ceil(Number(process.env.UI_WALK_WAIT_SECONDS || 120) / 3));
  for (let i = 0; i < tries; i++) {
    try { const r = await fetch(BASE, { redirect: 'manual' }); if (r.status < 500) return true; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 3000));
  }
  return false;
}

async function login(page, role) {
  const email = process.env[`E2E_${role.toUpperCase()}_EMAIL`] || process.env[`E2E_${role.toUpperCase()}_USER`];
  const password = process.env[`E2E_${role.toUpperCase()}_PASSWORD`];
  if (!email || !password) return { ok: false, why: `E2E_${role.toUpperCase()}_EMAIL/PASSWORD not set` };
  const candidates = args['login-url'] ? [args['login-url']] : ['/login', '/signin', '/sign-in', '/auth/login', '/autentificare', '/'];
  for (const c of candidates) {
    const url = new URL(c, BASE).toString();
    try { await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 }); } catch { continue; }
    const pass = page.locator('input[type="password"]').first();
    if (!(await pass.count())) continue;
    const user = page.locator('input[type="email"], input[autocomplete="username"], input[name*="email" i], input[name*="user" i], input[name*="login" i], input[id*="email" i]').first();
    if (!(await user.count())) continue;
    await user.fill(email);
    await pass.fill(password);
    const submit = page.locator('button[type="submit"], input[type="submit"]').first();
    const before = page.url();
    if (await submit.count()) await submit.click(); else await pass.press('Enter');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    const stillThere = await page.locator('input[type="password"]').count();
    if (!stillThere || page.url() !== before) return { ok: true, at: url, landed: page.url() };
    return { ok: false, why: `form at ${url} submitted, still on the login form (wrong credentials or selector)` };
  }
  return { ok: false, why: 'no login form found; pass --login-url' };
}

async function inspect(page) {
  return page.evaluate(() => {
    const text = (el) => (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    const label = (inp) => {
      if (inp.id) { const l = document.querySelector(`label[for="${CSS.escape(inp.id)}"]`); if (l) return text(l); }
      const p = inp.closest('label'); if (p) return text(p);
      return inp.getAttribute('aria-label') || inp.getAttribute('placeholder') || inp.name || '';
    };
    const body = document.body ? document.body.innerText : '';
    const leaks = [];
    for (const m of body.matchAll(/\b(undefined|NaN|null|\[object Object\])\b|\{\{[^}]+\}\}|\b[a-z]+(?:\.[a-zA-Z_]+){2,}\b/g)) {
      const t = m[0];
      const isKey = !/^(undefined|NaN|null|\[object Object\])$/.test(t) && !t.startsWith('{{');
      if (isKey && (t.split('.').pop().length <= 3 || /^www\./.test(t))) continue; // a domain, not an i18n key
      if (leaks.length < 6) leaks.push(t);
    }
    return {
      title: document.title,
      h: [...document.querySelectorAll('h1, h2')].slice(0, 8).map(text),
      forms: [...document.querySelectorAll('form')].slice(0, 6).map((f) => ({
        fields: [...f.querySelectorAll('input:not([type=hidden]), select, textarea')].slice(0, 15).map((i) => ({ label: label(i), type: i.type || i.tagName.toLowerCase(), required: i.required })),
        submit: text(f.querySelector('button[type=submit], input[type=submit], button:not([type])') || document.createElement('i')),
      })),
      buttons: [...document.querySelectorAll('button, [role=button]')].slice(0, 20).map(text).filter(Boolean),
      unlabeled: [...document.querySelectorAll('input:not([type=hidden]), select, textarea')].filter((i) => !label(i)).length,
      links: [...document.querySelectorAll('a[href]')].map((a) => a.href),
      overflowX: document.documentElement.scrollWidth > window.innerWidth + 2,
      brokenImages: [...document.images].filter((i) => i.complete && i.naturalWidth === 0).map((i) => i.src).slice(0, 5),
      leaks,
      lang: document.documentElement.lang || '',
    };
  });
}

// ------------------------------------------------------------------ walk
const results = [];
const logins = [];

async function walk(browser, role, vp) {
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, ignoreHTTPSErrors: true });
  const page = await context.newPage();
  let cur = null;
  const bucket = () => cur;
  const noise = (u) => /\/favicon\.ico(\?|$)/.test(u || '');
  page.on('console', (m) => { if (m.type() === 'error' && bucket() && !noise(m.location()?.url)) bucket().console.push(m.text().slice(0, 200)); });
  page.on('pageerror', (e) => { if (bucket()) bucket().exceptions.push(String(e.message).slice(0, 200)); });
  page.on('response', (r) => { if (r.status() >= 400 && bucket() && !noise(r.url())) bucket().failed.push(`${r.status()} ${r.request().method()} ${r.url().slice(0, 160)}`); });
  page.on('requestfailed', (r) => { if (bucket()) bucket().failed.push(`ERR ${r.method()} ${r.url().slice(0, 160)} ${r.failure()?.errorText || ''}`); });

  let start = BASE.toString();
  if (role !== 'anonymous') {
    const res = await login(page, role);
    logins.push({ role, viewport: vp.name, ...res });
    if (!res.ok) { await context.close(); return; }
    start = res.landed || start;
  }
  const seen = new Set();
  const queue = [{ url: norm(start), depth: 0 }];
  let n = 0;
  while (queue.length && n < MAX_PAGES) {
    const { url, depth } = queue.shift();
    if (seen.has(url)) continue;
    seen.add(url);
    cur = { role, viewport: vp.name, url, depth, console: [], exceptions: [], failed: [] };
    let status = 0;
    try {
      const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
      status = resp ? resp.status() : 0;
    } catch (e) {
      try { await page.waitForLoadState('domcontentloaded', { timeout: 5000 }); } catch { /* keep going */ }
      cur.exceptions.push(`navigation: ${String(e.message).split('\n')[0]}`);
    }
    if (!page.url().startsWith(BASE.origin)) { cur.offsite = page.url(); results.push(cur); continue; }
    cur.final = page.url();
    cur.status = status;
    const info = await inspect(page).catch((e) => ({ error: String(e) }));
    Object.assign(cur, info);
    const shot = path.join(SHOTS, `${role}-${vp.name}-${String(n).padStart(2, '0')}-${slug(url)}.png`);
    await page.screenshot({ path: shot, fullPage: true }).catch(() => {});
    cur.shot = path.relative(OUT, shot);
    cur.thumb = (await page.screenshot({ type: 'jpeg', quality: 45 }).catch(() => null))?.toString('base64');
    if (AxeBuilder) {
      try {
        const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
        cur.axe = r.violations.filter((v) => ['serious', 'critical'].includes(v.impact)).map((v) => `${v.impact}: ${v.id} (${v.nodes.length})`);
      } catch (e) { cur.axe = [`axe failed: ${String(e.message).slice(0, 80)}`]; }
    }
    if (depth < DEPTH) {
      for (const href of info.links || []) {
        let u; try { u = new URL(href); } catch { continue; }
        if (u.origin !== BASE.origin || UNSAFE.test(u.pathname + u.search) || /^(mailto|tel|javascript):/.test(href)) continue;
        const k = norm(u.toString());
        if (!seen.has(k)) queue.push({ url: k, depth: depth + 1 });
      }
    }
    delete cur.links;
    results.push(cur);
    n++;
  }
  await context.close();
}

// ------------------------------------------------------------------ report
function issuesOf(r) {
  const out = [];
  if (r.status >= 400) out.push(`HTTP ${r.status}`);
  if (r.exceptions?.length) out.push(`${r.exceptions.length} uncaught`);
  if (r.console?.length) out.push(`${r.console.length} console errors`);
  if (r.failed?.length) out.push(`${r.failed.length} failed requests`);
  if (r.overflowX) out.push('horizontal overflow');
  if (r.brokenImages?.length) out.push(`${r.brokenImages.length} broken images`);
  if (r.leaks?.length) out.push(`placeholders on screen: ${[...new Set(r.leaks)].join(', ')}`);
  if (r.unlabeled) out.push(`${r.unlabeled} unlabeled fields`);
  if (r.axe?.length) out.push(`axe ${r.axe.length}`);
  return out;
}

function writeReports(browserName) {
  const routes = {};
  for (const r of results.filter((x) => !x.offsite)) {
    const p = new URL(r.final || r.url).pathname;
    routes[p] ||= { path: p, title: r.title, headings: r.h, forms: r.forms, buttons: r.buttons, seenAs: [] };
    routes[p].seenAs.push(`${r.role}@${r.viewport}`);
  }
  const map = { base: BASE.toString(), generated: new Date().toISOString(), browser: browserName, logins,
    routes: Object.values(routes), pages: results.map(({ thumb, ...rest }) => rest) };
  fs.writeFileSync(path.join(OUT, 'ui-map.json'), JSON.stringify(map, null, 2));

  const withIssues = results.filter((r) => issuesOf(r).length);
  let md = `# UI walk: ${BASE}\n\n${map.generated} · browser: ${browserName} · ${results.length} page visits · ${Object.keys(routes).length} routes · viewports ${VIEWPORTS.map((v) => v.name).join(', ')}\n\n`;
  md += `## Logins\n\n| Role | Viewport | Result |\n| --- | --- | --- |\n`;
  for (const l of logins) md += `| ${l.role} | ${l.viewport} | ${l.ok ? `ok, landed on ${l.landed}` : `FAILED: ${l.why}`} |\n`;
  if (!logins.length) md += `| anonymous only | | no --role given |\n`;
  md += `\n## Routes\n\n| Route | Title | Forms | Seen as |\n| --- | --- | --- | --- |\n`;
  for (const r of Object.values(routes)) md += `| \`${r.path}\` | ${r.title || ''} | ${(r.forms || []).map((f) => `${f.fields.length} fields → "${f.submit}"`).join('; ') || '-'} | ${r.seenAs.join(', ')} |\n`;
  md += `\n## Issues (${withIssues.length} of ${results.length} visits)\n\n`;
  if (!withIssues.length) md += 'None found by the automatic checks. The human-style pass still has to look at the screenshots.\n';
  else {
    md += `| Page | Role@viewport | Issues | Screenshot |\n| --- | --- | --- | --- |\n`;
    for (const r of withIssues) md += `| \`${new URL(r.final || r.url).pathname}\` | ${r.role}@${r.viewport} | ${issuesOf(r).join('; ')} | ${r.shot} |\n`;
    md += `\n### Details\n\n`;
    for (const r of withIssues) {
      md += `- \`${r.url}\` (${r.role}@${r.viewport})\n`;
      for (const k of ['exceptions', 'console', 'failed', 'axe', 'brokenImages']) for (const v of r[k] || []) md += `  - ${k}: ${v}\n`;
    }
  }
  fs.writeFileSync(path.join(OUT, 'report.md'), md);

  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const cards = results.filter((r) => r.thumb).map((r) => {
    const iss = issuesOf(r);
    return `<figure class="${iss.length ? 'bad' : ''}"><img src="data:image/jpeg;base64,${r.thumb}" alt="${esc(r.url)}"><figcaption><b>${esc(new URL(r.final || r.url).pathname)}</b> · ${esc(r.role)}@${esc(r.viewport)}${iss.length ? `<br><span>${esc(iss.join('; '))}</span>` : ''}</figcaption></figure>`;
  }).join('\n');
  fs.writeFileSync(path.join(OUT, 'report.html'), `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UI walk</title>
<style>:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--bad:#c0392b;--line:#ddd}@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#eee;--mut:#999;--line:#333}}
body{background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif;margin:0;padding:16px}h1{font-size:18px}p{color:var(--mut)}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}figure{margin:0;border:1px solid var(--line);border-radius:8px;overflow:hidden}
figure.bad{border-color:var(--bad)}img{width:100%;display:block;border-bottom:1px solid var(--line)}figcaption{padding:8px;font-size:12px}figcaption span{color:var(--bad)}</style>
<h1>UI walk: ${esc(BASE)}</h1><p>${esc(map.generated)} · ${results.length} visits · ${withIssues.length} with issues · browser ${esc(browserName)}</p><main>${cards}</main>`);
  return { visits: results.length, routes: Object.keys(routes).length, withIssues: withIssues.length };
}

// ------------------------------------------------------------------ main
if (!(await waitForApp())) { console.error(`${BASE} did not answer. Bring the stack up first.`); process.exit(2); }
const { browser, name } = await launch();
try {
  for (const vp of VIEWPORTS) {
    await walk(browser, 'anonymous', vp);
    for (const role of args.role) await walk(browser, role, vp);
  }
} finally {
  await browser.close();
}
const s = writeReports(name);
console.log(`ui-walk: ${s.visits} visits, ${s.routes} routes, ${s.withIssues} with issues · browser ${name}`);
console.log(`  ${path.join(OUT, 'report.md')}\n  ${path.join(OUT, 'report.html')}\n  ${path.join(OUT, 'ui-map.json')}`);
