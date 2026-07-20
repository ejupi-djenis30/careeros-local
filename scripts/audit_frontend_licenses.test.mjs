import assert from "node:assert/strict";
import test from "node:test";

import { buildLicenseInventory } from "./audit_frontend_licenses.mjs";

function lockfile(packages) {
  return { lockfileVersion: 3, packages: { "": { name: "app", version: "1.0.0" }, ...packages } };
}

function metadata({ license = "MIT", version = "1.0.0" } = {}) {
  return {
    version,
    license,
    resolved: `https://registry.npmjs.org/example/-/example-${version}.tgz`,
    integrity: "sha512-example",
  };
}

test("builds a deterministic, privacy-safe production inventory", () => {
  const inventory = buildLicenseInventory(lockfile({
    "node_modules/parent/node_modules/zeta": metadata(),
    "node_modules/dev-only": { ...metadata(), dev: true },
    "node_modules/@scope/alpha": metadata({ license: "Apache-2.0 OR MIT", version: "2.0.0" }),
  }));

  assert.equal(inventory.packageCount, 2);
  assert.deepEqual(inventory.packages.map(({ name }) => name), ["@scope/alpha", "zeta"]);
  assert.equal(JSON.stringify(inventory).includes("email"), false);
  assert.equal(JSON.stringify(inventory).includes("publisher"), false);
});

test("rejects disallowed or incomplete package records", () => {
  assert.throws(
    () => buildLicenseInventory(lockfile({ "node_modules/restricted": metadata({ license: "GPL-3.0" }) })),
    /Disallowed production license/,
  );
  assert.throws(
    () => buildLicenseInventory(lockfile({ "node_modules/incomplete": { version: "1.0.0", license: "MIT" } })),
    /Incomplete production package metadata/,
  );
});

test("rejects mutable package sources and unsupported lockfiles", () => {
  assert.throws(
    () => buildLicenseInventory(lockfile({
      "node_modules/local": { ...metadata(), resolved: "file:../local" },
    })),
    /Unpinned production package source/,
  );
  assert.throws(() => buildLicenseInventory({ lockfileVersion: 2, packages: {} }), /lockfileVersion 3/);
});
