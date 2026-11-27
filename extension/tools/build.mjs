// Reproducible Manifest V3 package builder (Node built-in modules only).
// Produces extension/dist/ and byte-identical extension/dist/ec-quote-extension-<version>.zip.
import { execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import zlib from 'node:zlib';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const ROOT_DIR = path.resolve(HERE, '..');

export const RUNTIME_ENTRIES = Object.freeze([
  'manifest.json',
  'background',
  'content',
  'panel',
  'options',
  'icons',
]);

// Fixed DOS date/time (1980-01-01 00:00:00) so two builds produce byte-identical archives.
const FIXED_DOS_TIME = 0x0000;
const FIXED_DOS_DATE = 0x0021;

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i += 1) {
    let c = i;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[i] = c >>> 0;
  }
  return table;
})();

export function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i += 1) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

export function extensionIdFromKey(base64Spki) {
  const der = Buffer.from(String(base64Spki || ''), 'base64');
  const digest = crypto.createHash('sha256').update(der).digest();
  let id = '';
  for (let i = 0; i < 16; i += 1) {
    id += String.fromCharCode(97 + (digest[i] >> 4)) + String.fromCharCode(97 + (digest[i] & 0x0f));
  }
  return id;
}

// Minimal deterministic ZIP writer (PKZIP 2.0, deflate level 9, sorted entries).
export function createDeterministicZip(files) {
  const sorted = [...files].sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  const localParts = [];
  const centralParts = [];
  let offset = 0;

  for (const item of sorted) {
    const nameBuf = Buffer.from(item.name, 'utf8');
    const raw = Buffer.isBuffer(item.data) ? item.data : Buffer.from(item.data);
    const deflated = zlib.deflateRawSync(raw, { level: 9 });
    const useStore = deflated.length >= raw.length;
    const method = useStore ? 0 : 8;
    const payload = useStore ? raw : deflated;
    const crc = crc32(raw);

    const localHeader = Buffer.alloc(30);
    localHeader.writeUInt32LE(0x04034b50, 0);
    localHeader.writeUInt16LE(20, 4);
    localHeader.writeUInt16LE(0x0800, 6); // UTF-8 filename flag
    localHeader.writeUInt16LE(method, 8);
    localHeader.writeUInt16LE(FIXED_DOS_TIME, 10);
    localHeader.writeUInt16LE(FIXED_DOS_DATE, 12);
    localHeader.writeUInt32LE(crc, 14);
    localHeader.writeUInt32LE(payload.length, 18);
    localHeader.writeUInt32LE(raw.length, 22);
    localHeader.writeUInt16LE(nameBuf.length, 26);
    localHeader.writeUInt16LE(0, 28);

    localParts.push(localHeader, nameBuf, payload);

    const centralHeader = Buffer.alloc(46);
    centralHeader.writeUInt32LE(0x02014b50, 0);
    centralHeader.writeUInt16LE(20, 4);
    centralHeader.writeUInt16LE(20, 6);
    centralHeader.writeUInt16LE(0x0800, 8);
    centralHeader.writeUInt16LE(method, 10);
    centralHeader.writeUInt16LE(FIXED_DOS_TIME, 12);
    centralHeader.writeUInt16LE(FIXED_DOS_DATE, 14);
    centralHeader.writeUInt32LE(crc, 16);
    centralHeader.writeUInt32LE(payload.length, 20);
    centralHeader.writeUInt32LE(raw.length, 24);
    centralHeader.writeUInt16LE(nameBuf.length, 28);
    centralHeader.writeUInt16LE(0, 30);
    centralHeader.writeUInt16LE(0, 32);
    centralHeader.writeUInt16LE(0, 34);
    centralHeader.writeUInt16LE(0, 36);
    centralHeader.writeUInt32LE(0, 38);
    centralHeader.writeUInt32LE(offset, 42);

    centralParts.push(centralHeader, nameBuf);
    offset += localHeader.length + nameBuf.length + payload.length;
  }

  const centralBuf = Buffer.concat(centralParts);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(0, 4);
  eocd.writeUInt16LE(0, 6);
  eocd.writeUInt16LE(sorted.length, 8);
  eocd.writeUInt16LE(sorted.length, 10);
  eocd.writeUInt32LE(centralBuf.length, 12);
  eocd.writeUInt32LE(offset, 16);
  eocd.writeUInt16LE(0, 20);

  return Buffer.concat([...localParts, centralBuf, eocd]);
}

async function collectFiles(baseDir, relPath) {
  const full = path.join(baseDir, relPath);
  const stat = await fs.stat(full);
  if (stat.isFile()) {
    const data = await fs.readFile(full);
    const normalized = relPath.endsWith('.png') ? data : Buffer.from(data.toString('utf8').replace(/\r\n/g, '\n'), 'utf8');
    return [{ name: relPath.split(path.sep).join('/'), data: normalized }];
  }
  const entries = (await fs.readdir(full)).sort();
  const out = [];
  for (const entry of entries) {
    if (entry.startsWith('.') || entry.endsWith('~') || entry.endsWith('.map')) continue;
    out.push(...(await collectFiles(baseDir, path.join(relPath, entry))));
  }
  return out;
}

function parseSemver(value) {
  const m = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(String(value || '').trim());
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}

function compareSemver(left, right) {
  for (let i = 0; i < 3; i += 1) {
    if (left[i] !== right[i]) return left[i] - right[i];
  }
  return 0;
}

function defaultGitRunner(args, cwd) {
  return execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
}

export function verifyVersionBumpSinceTag({ rootDir = ROOT_DIR, version, gitRunner = defaultGitRunner } = {}) {
  const current = parseSemver(version);
  if (!current) throw new Error(`Invalid package.json version: ${version}`);
  let latestTag = '';
  try {
    latestTag = gitRunner(['describe', '--tags', '--match', 'v[0-9]*.[0-9]*.[0-9]*', '--abbrev=0'], rootDir);
  } catch {
    return; // No release tag exists yet.
  }
  const tagSemver = parseSemver(latestTag);
  if (!tagSemver) return;
  let changed = '';
  try {
    changed = gitRunner(['diff', '--name-only', latestTag, 'HEAD', '--', ...RUNTIME_ENTRIES], rootDir);
  } catch {
    return;
  }
  const files = changed.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (files.length > 0 && compareSemver(current, tagSemver) <= 0) {
    throw new Error(
      `Extension runtime files changed since ${latestTag} (${files.join(', ')}), ` +
        `but version (${version}) was not bumped above ${latestTag}.`,
    );
  }
}

export async function buildExtension({
  rootDir = ROOT_DIR,
  outDir = path.join(rootDir, 'dist'),
  gitRunner = defaultGitRunner,
} = {}) {
  const pkg = JSON.parse(await fs.readFile(path.join(rootDir, 'package.json'), 'utf8'));
  const manifest = JSON.parse(await fs.readFile(path.join(rootDir, 'manifest.json'), 'utf8'));

  if (!/^\d+\.\d+\.\d+$/.test(pkg.version || '')) {
    throw new Error(`Invalid package.json version: ${pkg.version}`);
  }
  if (manifest.version !== pkg.version) {
    throw new Error(`Version mismatch: manifest.json (${manifest.version}) !== package.json (${pkg.version})`);
  }
  verifyVersionBumpSinceTag({ rootDir, version: pkg.version, gitRunner });
  if (!manifest.key || typeof manifest.key !== 'string') {
    throw new Error('manifest.json is missing the fixed public key');
  }
  const extensionId = extensionIdFromKey(manifest.key);
  if (!/^[a-p]{32}$/.test(extensionId)) {
    throw new Error(`Derived extension id is invalid: ${extensionId}`);
  }

  await fs.rm(outDir, { recursive: true, force: true });
  await fs.mkdir(outDir, { recursive: true });

  const files = [];
  for (const entry of RUNTIME_ENTRIES) {
    files.push(...(await collectFiles(rootDir, entry)));
  }
  for (const file of files) {
    const dest = path.join(outDir, ...file.name.split('/'));
    await fs.mkdir(path.dirname(dest), { recursive: true });
    await fs.writeFile(dest, file.data);
  }

  const zipName = `ec-quote-extension-${pkg.version}.zip`;
  const zipPath = path.join(outDir, zipName);
  const zipBytes = createDeterministicZip(files);
  await fs.writeFile(zipPath, zipBytes);

  return {
    version: pkg.version,
    extensionId,
    origin: `chrome-extension://${extensionId}`,
    outDir,
    zipPath,
    files: files.map((f) => f.name).sort(),
    sha256: crypto.createHash('sha256').update(zipBytes).digest('hex'),
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const info = await buildExtension();
  console.log(`Built ${path.basename(info.zipPath)} (id=${info.extensionId}, sha256=${info.sha256.slice(0, 16)})`);
}
