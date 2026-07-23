#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const DEFAULT_LOCKFILE = new URL("../frontend/package-lock.json", import.meta.url);
const ALLOWED_LICENSES = new Set(["MIT", "MIT OR Apache-2.0", "Apache-2.0 OR MIT"]);

function packageName(path, metadata) {
  if (typeof metadata.name === "string" && metadata.name.length > 0) return metadata.name;
  return path.split("/node_modules/").at(-1).replace(/^node_modules\//, "");
}

export function buildLicenseInventory(lockfile) {
  if (lockfile.lockfileVersion !== 3 || typeof lockfile.packages !== "object") {
    throw new Error("Expected an npm lockfileVersion 3 package inventory.");
  }

  const packages = Object.entries(lockfile.packages)
    .filter(([path, metadata]) => path.startsWith("node_modules/") && metadata.dev !== true)
    .map(([path, metadata]) => {
      const name = packageName(path, metadata);
      const { version, license, integrity, resolved } = metadata;
      if (![name, version, license, integrity, resolved].every((value) => typeof value === "string" && value.length > 0)) {
        throw new Error(`Incomplete production package metadata: ${path}`);
      }
      if (!ALLOWED_LICENSES.has(license)) {
        throw new Error(`Disallowed production license: ${name}@${version} (${license})`);
      }
      if (!resolved.startsWith("https://registry.npmjs.org/") || !integrity.startsWith("sha512-")) {
        throw new Error(`Unpinned production package source: ${name}@${version}`);
      }
      return { name, version, license, integrity, resolved };
    })
    .sort((left, right) => {
      const leftKey = `${left.name}@${left.version}`;
      const rightKey = `${right.name}@${right.version}`;
      return leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0;
    });

  if (packages.length === 0) throw new Error("No production packages were found in the lockfile.");
  return {
    schemaVersion: 1,
    source: "frontend/package-lock.json",
    packageCount: packages.length,
    packages,
  };
}

function argumentsFor(argv) {
  const result = { lockfile: DEFAULT_LOCKFILE, output: null };
  for (let index = 0; index < argv.length; index += 1) {
    const option = argv[index];
    if (option !== "--lockfile" && option !== "--output") throw new Error(`Unknown option: ${option}`);
    const value = argv[index + 1];
    if (!value) throw new Error(`Missing value for ${option}`);
    result[option.slice(2)] = value;
    index += 1;
  }
  if (!result.output) throw new Error("Usage: audit_frontend_licenses.mjs --output <path> [--lockfile <path>]");
  return result;
}

async function main() {
  const options = argumentsFor(process.argv.slice(2));
  const lockfile = JSON.parse(await readFile(options.lockfile, "utf8"));
  const inventory = buildLicenseInventory(lockfile);
  await writeFile(options.output, `${JSON.stringify(inventory, null, 2)}\n`, "utf8");
  process.stdout.write(`FRONTEND_LICENSES_OK packages=${inventory.packageCount}\n`);
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  await main();
}
