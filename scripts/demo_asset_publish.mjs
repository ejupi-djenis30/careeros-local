/** Transactional validation and publication for the generated demo media. */

import { rename, rm, stat, mkdtemp } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";

export const demoAssetNames = Object.freeze([
    "careeros-demo.webm",
    "careeros-workspace.png",
    "careeros-vault.png",
    "careeros-resume-studio.png",
    "careeros-applications.png",
    "careeros-demo.gif",
    "careeros-demo-poster.jpg",
]);

export const maxDemoVideoBytes = 10 * 1024 * 1024;

function assertChildPath(target, parent) {
    const resolvedTarget = resolve(target);
    const resolvedParent = resolve(parent);
    const child = relative(resolvedParent, resolvedTarget);
    if (!child || child.startsWith("..") || isAbsolute(child)) {
        throw new Error(`Expected ${resolvedTarget} to be inside ${resolvedParent}`);
    }
}

async function fileStats(path, name) {
    try {
        const result = await stat(path);
        if (!result.isFile() || result.size === 0) {
            throw new Error(`Staged demo asset is not a non-empty file: ${name}`);
        }
        return result;
    } catch (error) {
        if (error.code === "ENOENT") throw new Error(`Missing staged demo asset: ${name}`, { cause: error });
        throw error;
    }
}

export async function validateStagedDemoAssets(stagingDir) {
    const validated = {};
    for (const name of demoAssetNames) {
        const path = join(stagingDir, name);
        assertChildPath(path, stagingDir);
        validated[name] = await fileStats(path, name);
    }

    const videoStats = validated["careeros-demo.webm"];
    if (videoStats.size > maxDemoVideoBytes) {
        throw new Error(
            `Demo video is ${(videoStats.size / 1024 / 1024).toFixed(1)} MiB; keep it below 10 MiB for GitHub.`,
        );
    }
    return validated;
}

async function moveExisting(source, destination, renameFile) {
    try {
        await renameFile(source, destination);
        return true;
    } catch (error) {
        if (error.code === "ENOENT") return false;
        throw error;
    }
}

/**
 * Publish a fully rendered demo asset set as one recoverable transaction.
 *
 * All staged files are validated before any destination is changed. Existing
 * assets are retained in a same-filesystem backup until every replacement is
 * installed. A failed install removes partial replacements and restores the
 * previous set before the error is returned.
 */
export async function publishDemoAssets(stagingDir, destinationDir, options = {}) {
    const renameFile = options.renameFile ?? rename;
    await validateStagedDemoAssets(stagingDir);

    const destinationParent = dirname(destinationDir);
    const backupDir = await mkdtemp(join(destinationParent, ".careeros-demo-backup-"));
    const backedUp = [];
    const published = [];
    let retainBackup = false;

    try {
        for (const name of demoAssetNames) {
            const destination = join(destinationDir, name);
            const backup = join(backupDir, name);
            assertChildPath(destination, destinationDir);
            assertChildPath(backup, backupDir);
            if (await moveExisting(destination, backup, renameFile)) backedUp.push(name);
        }

        for (const name of demoAssetNames) {
            const staged = join(stagingDir, name);
            const destination = join(destinationDir, name);
            await renameFile(staged, destination);
            published.push(name);
        }
    } catch (publishError) {
        const rollbackErrors = [];
        for (const name of published.reverse()) {
            try {
                await rm(join(destinationDir, name), { force: true });
            } catch (error) {
                rollbackErrors.push(error);
            }
        }
        for (const name of backedUp.reverse()) {
            try {
                await renameFile(join(backupDir, name), join(destinationDir, name));
            } catch (error) {
                rollbackErrors.push(error);
            }
        }
        if (rollbackErrors.length) {
            retainBackup = true;
            throw new AggregateError(
                [publishError, ...rollbackErrors],
                `Demo asset publication failed and could not be rolled back completely; recovery files remain in ${backupDir}`,
            );
        }
        throw publishError;
    } finally {
        if (!retainBackup) await rm(backupDir, { recursive: true, force: true });
    }
}
