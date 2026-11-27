// Static safety, manifest allowlist, single-selector-map, and Romanian punctuation checks.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { extensionIdFromKey } from '../../tools/build.mjs';

const EXT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const REPO_DIR = path.resolve(EXT_DIR, '..');

async function walkRuntimeFiles(dir, rel = '') {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const nextRel = rel ? `${rel}/${entry.name}` : entry.name;
    if (['tests', 'tools', 'dist', 'screenshots', 'node_modules'].includes(nextRel.split('/')[0])) continue;
    if (entry.name.startsWith('.')) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...(await walkRuntimeFiles(full, nextRel)));
    else if (/\.(js|mjs|html|css)$/.test(entry.name)) files.push({ rel: nextRel, full });
  }
  return files;
}

test('manifest requests only minimal permissions, strict CSP, and stable key', async () => {
  const manifest = JSON.parse(await fs.readFile(path.join(EXT_DIR, 'manifest.json'), 'utf8'));
  const pkg = JSON.parse(await fs.readFile(path.join(EXT_DIR, 'package.json'), 'utf8'));
  assert.equal(manifest.manifest_version, 3);
  assert.equal(manifest.version, pkg.version);
  assert.deepEqual(manifest.permissions, ['storage', 'clipboardWrite']);
  assert.deepEqual(manifest.host_permissions, ['https://web.whatsapp.com/*']);
  assert.deepEqual(manifest.optional_host_permissions, ['https://*/*', 'http://localhost/*', 'http://127.0.0.1/*']);
  assert.equal(manifest.web_accessible_resources, undefined);
  assert.equal(extensionIdFromKey(manifest.key), 'pihdgadpmjibpcbacfflgkipidjedkej');

  const csp = manifest.content_security_policy?.extension_pages || '';
  assert.match(csp, /script-src 'self'/);
  assert.ok(!csp.includes('unsafe-eval'));
  assert.ok(!csp.includes('unsafe-inline'));
  assert.ok(!/script-src[^;]*https?:/i.test(csp));
});

test('runtime extension sources contain no Send button, no synthetic Enter, no eval, and no WhatsApp selectors outside selectors.js', async () => {
  const files = await walkRuntimeFiles(EXT_DIR);
  assert.ok(files.length >= 10);

  for (const file of files) {
    const src = await fs.readFile(file.full, 'utf8');
    assert.ok(!/\beval\s*\(/.test(src), `eval forbidden in ${file.rel}`);
    assert.ok(!/\bnew\s+Function\s*\(/.test(src), `new Function forbidden in ${file.rel}`);
    assert.ok(!/<script[^>]+src=["']https?:/i.test(src), `remote script forbidden in ${file.rel}`);
    assert.ok(!/\.innerHTML\s*=/.test(src), `innerHTML assignment forbidden in ${file.rel}`);
    assert.ok(!/data-icon=["']send["']|aria-label=["'](Trimite|Send)["']/i.test(src), `send selector forbidden in ${file.rel}`);
    assert.ok(!/new\s+KeyboardEvent\s*\(\s*['"]key(down|press|up)['"][^)]*Enter/s.test(src), `synthetic Enter forbidden in ${file.rel}`);
    assert.ok(!/\u2014/.test(src), `em dash forbidden in ${file.rel}`);

    if (file.rel !== 'content/selectors.js' && file.rel !== 'options/options.js' && file.rel !== 'panel/panel.js') {
      assert.ok(!/\.querySelector(All)?\s*\(/.test(src), `DOM query outside selectors.js/panel/options in ${file.rel}`);
    }
    if (file.rel === 'panel/panel.js') {
      // Panel only queries its own shadow DOM button elements, never WhatsApp's DOM.
      const matches = [...src.matchAll(/\.querySelector(All)?\s*\(\s*['"]([^'"]+)['"]\s*\)/g)].map((m) => m[2]);
      assert.ok(matches.every((sel) => sel === 'button'), `panel.js only queries its own button elements, got: ${matches.join(', ')}`);
    }
  }
});

test('Romanian extension docs and RUNBOOK exist and contain no em dashes', async () => {
  for (const rel of ['docs/extensie-instalare.md', 'docs/extensie-publicare.md', 'RUNBOOK.md']) {
    const text = await fs.readFile(path.join(REPO_DIR, rel), 'utf8');
    assert.ok(text.length > 400, `${rel} is populated`);
    assert.ok(!/\u2014/.test(text), `no em dash in ${rel}`);
  }
  const runbook = await fs.readFile(path.join(REPO_DIR, 'RUNBOOK.md'), 'utf8');
  assert.match(runbook, /WhatsApp s-a schimbat/);
  const pub = await fs.readFile(path.join(REPO_DIR, 'docs/extensie-publicare.md'), 'utf8');
  assert.match(pub, /chrome-extension:\/\/pihdgadpmjibpcbacfflgkipidjedkej/);
});
