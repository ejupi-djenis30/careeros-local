import assert from "node:assert/strict";
import { rename, mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { basename, dirname, join, resolve, sep } from "node:path";
import test from "node:test";
import { tmpdir } from "node:os";

import {
    demoAssetNames,
    publishDemoAssets,
    validateStagedDemoAssets,
} from "./demo_asset_publish.mjs";

async function fixture() {
    const root = await mkdtemp(join(tmpdir(), "careeros-demo-publish-test-"));
    const staging = join(root, "staging");
    const destination = join(root, "docs", "assets");
    await mkdir(staging);
    await mkdir(destination, { recursive: true });
    return { root, staging, destination };
}

async function writeAssetSet(directory, prefix, names = demoAssetNames) {
    await Promise.all(names.map((name) => writeFile(join(directory, name), `${prefix}:${name}`)));
}

async function assertAssetSet(directory, prefix) {
    for (const name of demoAssetNames) {
        assert.equal(await readFile(join(directory, name), "utf8"), `${prefix}:${name}`);
    }
}

test("publishes the complete staged demo set and preserves unrelated assets", async () => {
    const paths = await fixture();
    try {
        await writeAssetSet(paths.staging, "new");
        await writeAssetSet(paths.destination, "old");
        await writeFile(join(paths.destination, "unrelated.svg"), "keep me");

        await publishDemoAssets(paths.staging, paths.destination);

        await assertAssetSet(paths.destination, "new");
        assert.equal(await readFile(join(paths.destination, "unrelated.svg"), "utf8"), "keep me");
    } finally {
        await rm(paths.root, { recursive: true, force: true });
    }
});

test("rejects an incomplete stage before changing published assets", async () => {
    const paths = await fixture();
    try {
        await writeAssetSet(paths.staging, "new", demoAssetNames.slice(0, -1));
        await writeAssetSet(paths.destination, "old");

        await assert.rejects(validateStagedDemoAssets(paths.staging), /Missing staged demo asset/);
        await assert.rejects(publishDemoAssets(paths.staging, paths.destination), /Missing staged demo asset/);

        await assertAssetSet(paths.destination, "old");
    } finally {
        await rm(paths.root, { recursive: true, force: true });
    }
});

test("restores every previous asset when publication fails part-way", async () => {
    const paths = await fixture();
    try {
        await writeAssetSet(paths.staging, "new");
        await writeAssetSet(paths.destination, "old");
        let injected = false;
        const stagedRoot = `${resolve(paths.staging)}${sep}`;
        const failingRename = async (source, destination) => {
            if (!injected && resolve(source).startsWith(stagedRoot) && basename(source) === demoAssetNames[2]) {
                injected = true;
                throw new Error("injected publication failure");
            }
            await rename(source, destination);
        };

        await assert.rejects(
            publishDemoAssets(paths.staging, paths.destination, { renameFile: failingRename }),
            /injected publication failure/,
        );

        await assertAssetSet(paths.destination, "old");
        const leftovers = (await readdir(dirname(paths.destination)))
            .filter((name) => name.startsWith(".careeros-demo-backup-"));
        assert.deepEqual(leftovers, []);
    } finally {
        await rm(paths.root, { recursive: true, force: true });
    }
});
