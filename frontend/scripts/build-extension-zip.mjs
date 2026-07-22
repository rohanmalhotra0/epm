// Package the browser-agent extension into a downloadable .zip, so users can
// grab it straight from the web app's "Browser Agent" page instead of cloning
// the repo. Mirrors extension/scripts/package.sh: the same files ship, with the
// manifest at the archive root, so the result is loadable via
// chrome://extensions → "Load unpacked" once unzipped.
//
// Deliberately dependency-free (a tiny store-only ZIP writer) to keep the
// frontend's install footprint and local-first promise intact — no archiver,
// no CDN, no build-time network.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = fileURLToPath(new URL(".", import.meta.url));
// frontend/scripts → repo root → extension/
const EXTENSION_DIR = resolve(HERE, "..", "..", "extension");

// Everything the manifest references (kept in sync with package.sh's include[]).
const INCLUDE = ["manifest.json", "background", "common", "content", "sidepanel", "icons"];
// Editor/OS cruft and sourcemaps never belong in the shipped extension.
const EXCLUDE = [/(^|\/)\.DS_Store$/, /(^|\/)Thumbs\.db$/, /\.map$/];

/** CRC-32 (IEEE 802.3), computed on demand — table built once per process. */
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/** Recursively collect { archivePath, data } for every included file. */
function collect() {
  const files = [];
  const walk = (abs, archive) => {
    const st = statSync(abs);
    if (st.isDirectory()) {
      for (const name of readdirSync(abs).sort()) {
        walk(join(abs, name), archive ? `${archive}/${name}` : name);
      }
      return;
    }
    if (EXCLUDE.some((re) => re.test(archive))) return;
    files.push({ archivePath: archive, data: readFileSync(abs) });
  };
  for (const entry of INCLUDE) {
    const abs = join(EXTENSION_DIR, entry);
    walk(abs, relative(EXTENSION_DIR, abs).split("\\").join("/"));
  }
  return files;
}

// Fixed DOS timestamp (2020-01-01 00:00:00) → deterministic, reproducible zips.
const DOS_TIME = 0;
const DOS_DATE = ((2020 - 1980) << 9) | (1 << 5) | 1;

/**
 * Build the extension zip fully in memory (STORE method, no compression).
 * @returns {{ fileName: string, buffer: Buffer, version: string }}
 */
export function buildExtensionZip() {
  const manifest = JSON.parse(readFileSync(join(EXTENSION_DIR, "manifest.json"), "utf8"));
  const version = String(manifest.version || "0.0.0");
  const files = collect();

  const locals = [];
  const central = [];
  let offset = 0;

  for (const { archivePath, data } of files) {
    const name = Buffer.from(archivePath, "utf8");
    const crc = crc32(data);

    const local = Buffer.alloc(30 + name.length);
    local.writeUInt32LE(0x04034b50, 0); // local file header signature
    local.writeUInt16LE(20, 4); // version needed
    local.writeUInt16LE(0, 6); // flags
    local.writeUInt16LE(0, 8); // method: store
    local.writeUInt16LE(DOS_TIME, 10);
    local.writeUInt16LE(DOS_DATE, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18); // compressed size
    local.writeUInt32LE(data.length, 22); // uncompressed size
    local.writeUInt16LE(name.length, 26);
    local.writeUInt16LE(0, 28); // extra length
    name.copy(local, 30);
    locals.push(local, data);

    const cd = Buffer.alloc(46 + name.length);
    cd.writeUInt32LE(0x02014b50, 0); // central directory signature
    cd.writeUInt16LE(20, 4); // version made by
    cd.writeUInt16LE(20, 6); // version needed
    cd.writeUInt16LE(0, 8); // flags
    cd.writeUInt16LE(0, 10); // method
    cd.writeUInt16LE(DOS_TIME, 12);
    cd.writeUInt16LE(DOS_DATE, 14);
    cd.writeUInt32LE(crc, 16);
    cd.writeUInt32LE(data.length, 20);
    cd.writeUInt32LE(data.length, 24);
    cd.writeUInt16LE(name.length, 28);
    cd.writeUInt16LE(0, 30); // extra
    cd.writeUInt16LE(0, 32); // comment
    cd.writeUInt16LE(0, 34); // disk number start
    cd.writeUInt16LE(0, 36); // internal attrs
    cd.writeUInt32LE(0, 38); // external attrs
    cd.writeUInt32LE(offset, 42); // local header offset
    name.copy(cd, 46);
    central.push(cd);

    offset += local.length + data.length;
  }

  const cdBuf = Buffer.concat(central);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0); // end of central directory signature
  eocd.writeUInt16LE(0, 4); // disk number
  eocd.writeUInt16LE(0, 6); // disk with CD
  eocd.writeUInt16LE(files.length, 8); // entries this disk
  eocd.writeUInt16LE(files.length, 10); // total entries
  eocd.writeUInt32LE(cdBuf.length, 12); // CD size
  eocd.writeUInt32LE(offset, 16); // CD offset
  eocd.writeUInt16LE(0, 20); // comment length

  return {
    fileName: `epm-wizard-extension-${version}.zip`,
    version,
    buffer: Buffer.concat([...locals, cdBuf, eocd]),
  };
}
