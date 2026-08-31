#!/usr/bin/env node
/**
 * Syncs package.json's "version" field from services/VERSION -- the single source of truth for
 * ALFR3D's version number (also what service_api's /api/health reports, which is what the
 * Nexus/Core UI tooltip actually displays).
 *
 * services/VERSION lives outside the frontend's own Docker build context, so inside a container
 * build this is a no-op (package.json already carries whatever version was committed). Run: npm
 * run sync:version (also wired into predev / prebuild for local dev).
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const VERSION_PATH = join(__dirname, '..', '..', 'VERSION');
const PACKAGE_JSON_PATH = join(__dirname, '..', 'package.json');

if (existsSync(VERSION_PATH)) {
  const version = readFileSync(VERSION_PATH, 'utf-8').trim();
  const pkg = JSON.parse(readFileSync(PACKAGE_JSON_PATH, 'utf-8'));

  if (version && pkg.version !== version) {
    pkg.version = version;
    writeFileSync(PACKAGE_JSON_PATH, JSON.stringify(pkg, null, 2) + '\n');
  }
}
