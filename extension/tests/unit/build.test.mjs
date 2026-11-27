import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { buildExtension, verifyVersionBumpSinceTag } from '../../tools/build.mjs';

function readZipEntries(buf) {
  // Locate End of Central Directory signature 0x06054b50.
  let eocd = -1;
  for (let i = buf.length - 22; i >= 0; i -= 1) {
    if (buf.readUInt32LE(i) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  assert.ok(eocd >= 0, 'ZIP EOCD header found');
  const count = buf.readUInt16LE(eocd + 10);
  let ptr = buf.readUInt32LE(eocd + 16);
  const names = [];
  for (let i = 0; i < count; i += 1) {
    assert.equal(buf.readUInt32LE(ptr), 0x02014b50);
    const nameLen = buf.readUInt16LE(ptr + 28);
    const extraLen = buf.readUInt16LE(ptr + 30);
    const commentLen = buf.readUInt16LE(ptr + 32);
    names.push(buf.subarray(ptr + 46, ptr + 46 + nameLen).toString('utf8'));
    ptr += 46 + nameLen + extraLen + commentLen;
  }
  return names;
}

const EXPECTED_FILES = [
  'background/api-client.js',
  'background/coordinator.js',
  'background/service-worker.js',
  'content/composer.js',
  'content/main.js',
  'content/media.js',
  'content/selectors.js',
  'icons/icon128.png',
  'icons/icon16.png',
  'icons/icon32.png',
  'icons/icon48.png',
  'manifest.json',
  'options/options.css',
  'options/options.html',
  'options/options.js',
  'panel/panel-style.js',
  'panel/panel.js',
];

test('two builds produce byte-identical zips with only runtime files and stable extension id', async () => {
  const dirA = await fs.mkdtemp(path.join(os.tmpdir(), 'ecq-build-a-'));
  const dirB = await fs.mkdtemp(path.join(os.tmpdir(), 'ecq-build-b-'));
  try {
    const first = await buildExtension({ outDir: dirA });
    const second = await buildExtension({ outDir: dirB });

    assert.equal(first.extensionId, 'pihdgadpmjibpcbacfflgkipidjedkej');
    assert.equal(first.origin, 'chrome-extension://pihdgadpmjibpcbacfflgkipidjedkej');
    assert.equal(first.sha256, second.sha256);

    const bytesA = await fs.readFile(first.zipPath);
    const bytesB = await fs.readFile(second.zipPath);
    assert.equal(Buffer.compare(bytesA, bytesB), 0, 'zips are byte-for-byte identical');

    const names = readZipEntries(bytesA);
    assert.deepEqual(names, EXPECTED_FILES);
    for (const name of names) {
      assert.ok(!name.startsWith('tests/'));
      assert.ok(!name.startsWith('tools/'));
      assert.ok(!name.includes('node_modules'));
      assert.ok(!name.includes('.env'));
    }
  } finally {
    await fs.rm(dirA, { recursive: true, force: true });
    await fs.rm(dirB, { recursive: true, force: true });
  }
});

test('version check rejects runtime changes since latest v* tag without a semver bump', () => {
  const fakeGitSame = (args) => {
    if (args[0] === 'describe') return 'v0.1.0';
    if (args[0] === 'diff') return 'extension/content/main.js\n';
    return '';
  };
  assert.throws(
    () => verifyVersionBumpSinceTag({ version: '0.1.0', gitRunner: fakeGitSame }),
    /was not bumped above v0\.1\.0/,
  );

  assert.doesNotThrow(() => verifyVersionBumpSinceTag({ version: '0.1.1', gitRunner: fakeGitSame }));

  const fakeGitUnchanged = (args) => (args[0] === 'describe' ? 'v0.1.0' : '');
  assert.doesNotThrow(() => verifyVersionBumpSinceTag({ version: '0.1.0', gitRunner: fakeGitUnchanged }));
});
