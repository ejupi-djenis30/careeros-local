import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  isSupportedNodeVersion,
  parseNodeVersion,
  requireSupportedNodeVersion,
} from "./check_node_version.mjs";

const repositoryRoot = resolve(fileURLToPath(new URL("../", import.meta.url)));

test("accepts exactly the documented Node 24 floor and later Node 24 patches", () => {
  for (const version of ["24.18.0", "24.18.1", "24.99.0"]) {
    assert.equal(isSupportedNodeVersion(version), true, version);
    assert.equal(requireSupportedNodeVersion(version), version);
  }
});

test("rejects runtimes below the floor, Node 25 and non-release versions", () => {
  for (const version of [
    "24.17.99",
    "23.99.99",
    "25.0.0",
    "24.18.0-rc.1",
    "v24.18.0",
    "24.18",
    "not-a-version",
  ]) {
    assert.equal(isSupportedNodeVersion(version), false, version);
    assert.throws(
      () => requireSupportedNodeVersion(version),
      />=24\.18\.0 <25/,
    );
  }
});

test("parses only canonical three-part release versions", () => {
  assert.deepEqual(parseNodeVersion("24.18.0"), { major: 24, minor: 18, patch: 0 });
  assert.equal(parseNodeVersion("24.18.0.1"), null);
});

test("every public frontend command enforces the exact Node runtime contract", async () => {
  const [packageText, npmrc] = await Promise.all([
    readFile(resolve(repositoryRoot, "frontend/package.json"), "utf8"),
    readFile(resolve(repositoryRoot, "frontend/.npmrc"), "utf8"),
  ]);
  const manifest = JSON.parse(packageText);

  assert.deepEqual(manifest.engines, { node: ">=24.18.0 <25" });
  assert.equal(npmrc.trim(), "engine-strict=true");
  for (const scriptName of Object.keys(manifest.scripts)) {
    if (scriptName === "preflight:node" || scriptName.startsWith("pre")) continue;
    assert.equal(
      manifest.scripts[`pre${scriptName}`],
      "npm run preflight:node",
      `${scriptName} must fail fast before its executable command starts`,
    );
  }
});
