import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { basename, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const repositoryRoot = resolve(fileURLToPath(new URL("../", import.meta.url)));
const distributionRoot = resolve(repositoryRoot, "frontend/dist");
const assetRoot = resolve(distributionRoot, "assets");
const noticesPath = resolve(repositoryRoot, "THIRD_PARTY_NOTICES.txt");
const budgets = Object.freeze({
    entryRaw: 350_000,
    entryGzip: 112_000,
    selectedLocaleRaw: 82_000,
    selectedLocaleGzip: 26_000,
    lifecycleCssRaw: 23_000,
    lifecycleCssGzip: 6_200,
    initialRaw: 440_000,
    initialGzip: 140_000,
    authenticatedWorkspaceCssRaw: 445_000,
    authenticatedWorkspaceCssGzip: 73_500,
    authenticatedWorkspaceJsRaw: 32_000,
    authenticatedWorkspaceJsGzip: 9_600,
});

function assetPaths(html, pattern) {
    return [...html.matchAll(pattern)].map((match) => match[1]);
}

async function measurement(relativePath) {
    const content = await readFile(resolve(distributionRoot, `.${relativePath}`));
    return {
        path: relativePath,
        raw: content.byteLength,
        gzip: gzipSync(content).byteLength,
    };
}

function within(actual, maximum, label) {
    assert(
        actual <= maximum,
        `${label} is ${actual.toLocaleString("en-US")} bytes; budget is ${maximum.toLocaleString("en-US")}`,
    );
}

const htmlContent = await readFile(resolve(distributionRoot, "index.html"));
const [sourceNotices, distributedNotices] = await Promise.all([
    readFile(noticesPath),
    readFile(resolve(distributionRoot, "THIRD_PARTY_NOTICES.txt")),
]);
assert.deepEqual(
    distributedNotices,
    sourceNotices,
    "Web distribution must contain the exact approved third-party notices",
);
const html = htmlContent.toString("utf8");
const entryScripts = assetPaths(
    html,
    /<script\b[^>]*\bsrc="(\/assets\/[^"]+\.js)"[^>]*><\/script>/g,
);
const stylesheets = assetPaths(
    html,
    /<link\b[^>]*\brel="stylesheet"[^>]*\bhref="(\/assets\/[^"]+\.css)"/g,
);
assert.equal(entryScripts.length, 1, "Distribution must expose one initial JavaScript entry");
assert.equal(
    stylesheets.length,
    1,
    "Login boot must expose one consolidated initial stylesheet",
);

const assets = await readdir(assetRoot);
const localeFiles = assets.filter((name) => /^(en|it)-.+\.js$/.test(name)).sort();
const authenticatedWorkspaceCssFiles = assets.filter(
    (name) => /^AuthenticatedWorkspace-.+\.css$/.test(name),
);
const authenticatedWorkspaceJsFiles = assets.filter(
    (name) => /^AuthenticatedWorkspace-.+\.js$/.test(name),
);
assert.deepEqual(
    localeFiles.map((name) => name.slice(0, 2)),
    ["en", "it"],
    "English and Italian must remain independently loadable chunks",
);
assert.equal(
    assets.filter((name) => /^bootstrap-icons-.+\.woff2?$/.test(name)).length,
    0,
    "The full Bootstrap Icons font must not be emitted",
);
assert.equal(
    authenticatedWorkspaceCssFiles.length,
    1,
    "Authenticated workspace styles must remain one lazy CSS asset",
);
assert(
    !stylesheets.some((path) => authenticatedWorkspaceCssFiles.includes(basename(path))),
    "Authenticated workspace Bootstrap must not be duplicated into login boot CSS",
);
assert.equal(
    authenticatedWorkspaceJsFiles.length,
    1,
    "Authenticated workspace shell must remain one lazy JavaScript asset",
);

const entry = await measurement(entryScripts[0]);
const css = await Promise.all(stylesheets.map(measurement));
const locales = await Promise.all(
    localeFiles.map((name) => measurement(`/assets/${name}`)),
);
const selectedLocale = locales.reduce((largest, candidate) =>
    candidate.raw > largest.raw ? candidate : largest);
const authenticatedWorkspaceCss = await measurement(
    `/assets/${authenticatedWorkspaceCssFiles[0]}`,
);
const authenticatedWorkspaceJs = await measurement(
    `/assets/${authenticatedWorkspaceJsFiles[0]}`,
);
const [initialCssPayloads, authenticatedWorkspaceCssPayload] = await Promise.all([
    Promise.all(
        stylesheets.map((path) => readFile(resolve(distributionRoot, `.${path}`), "utf8")),
    ),
    readFile(
        resolve(assetRoot, authenticatedWorkspaceCssFiles[0]),
        "utf8",
    ),
]);
assert(
    initialCssPayloads.every((payload) => !payload.includes("@layer careeros-bootstrap")),
    "Bootstrap must not be duplicated into login boot CSS",
);
for (const requiredSelector of [".login-shell", ".recovery-shell", ".desktop-boot"]) {
    assert(
        initialCssPayloads.some((payload) => payload.includes(requiredSelector)),
        `Lifecycle CSS must retain ${requiredSelector}`,
    );
}
for (const workspaceSelector of [".workspace-layout", ".home-grid", ".agent-access-grid"]) {
    assert(
        initialCssPayloads.every((payload) => !payload.includes(workspaceSelector)),
        `${workspaceSelector} must remain outside login, recovery and desktop boot CSS`,
    );
    assert(
        authenticatedWorkspaceCssPayload.includes(workspaceSelector),
        `Authenticated workspace CSS must retain ${workspaceSelector}`,
    );
}
assert(
    initialCssPayloads.some((payload) => payload.includes("forced-colors:active")),
    "Lifecycle CSS must retain its forced-colors contract",
);
assert(
    initialCssPayloads.some((payload) => payload.includes("prefers-reduced-motion:reduce")),
    "Lifecycle CSS must retain its reduced-motion contract",
);
for (const viewport of ["(max-width:991.98px)", "(max-width:480px)"]) {
    assert(
        initialCssPayloads.some((payload) => payload.includes(viewport)),
        `Lifecycle CSS must retain its ${viewport} responsive contract`,
    );
}
assert(
    authenticatedWorkspaceCssPayload.includes("@layer careeros-bootstrap"),
    "Authenticated workspace CSS must retain the isolated Bootstrap layer",
);
for (const workspaceContract of [
    "@media print",
    "forced-colors:active",
    "prefers-reduced-motion:reduce",
    "(max-width:1450px)",
    "(max-width:720px)",
    "(max-width:480px)",
]) {
    assert(
        authenticatedWorkspaceCssPayload.includes(workspaceContract),
        `Authenticated workspace CSS must retain ${workspaceContract}`,
    );
}
const cssTotals = css.reduce(
    (totals, item) => ({ raw: totals.raw + item.raw, gzip: totals.gzip + item.gzip }),
    { raw: 0, gzip: 0 },
);
const initial = {
    raw: htmlContent.byteLength + entry.raw + selectedLocale.raw + cssTotals.raw,
    gzip: gzipSync(htmlContent).byteLength + entry.gzip + selectedLocale.gzip + cssTotals.gzip,
};

within(entry.raw, budgets.entryRaw, "Initial JavaScript entry (raw)");
within(entry.gzip, budgets.entryGzip, "Initial JavaScript entry (gzip)");
within(selectedLocale.raw, budgets.selectedLocaleRaw, "Largest selected locale (raw)");
within(selectedLocale.gzip, budgets.selectedLocaleGzip, "Largest selected locale (gzip)");
within(cssTotals.raw, budgets.lifecycleCssRaw, "Lifecycle CSS (raw)");
within(cssTotals.gzip, budgets.lifecycleCssGzip, "Lifecycle CSS (gzip)");
within(initial.raw, budgets.initialRaw, "Login initial resources (raw)");
within(initial.gzip, budgets.initialGzip, "Login initial resources (gzip)");
within(
    authenticatedWorkspaceCss.raw,
    budgets.authenticatedWorkspaceCssRaw,
    "Authenticated workspace CSS (raw)",
);
within(
    authenticatedWorkspaceCss.gzip,
    budgets.authenticatedWorkspaceCssGzip,
    "Authenticated workspace CSS (gzip)",
);
within(
    authenticatedWorkspaceJs.raw,
    budgets.authenticatedWorkspaceJsRaw,
    "Authenticated workspace shell (raw)",
);
within(
    authenticatedWorkspaceJs.gzip,
    budgets.authenticatedWorkspaceJsGzip,
    "Authenticated workspace shell (gzip)",
);

console.log([
    `Frontend bundle budget passed:`,
    `entry ${basename(entry.path)} ${entry.raw} B raw / ${entry.gzip} B gzip;`,
    `largest locale ${basename(selectedLocale.path)} ${selectedLocale.raw} B / ${selectedLocale.gzip} B;`,
    `lifecycle CSS ${cssTotals.raw} B / ${cssTotals.gzip} B;`,
    `initial ${initial.raw} B / ${initial.gzip} B;`,
    `authenticated workspace CSS ${authenticatedWorkspaceCss.raw} B / ${authenticatedWorkspaceCss.gzip} B;`,
    `shell ${authenticatedWorkspaceJs.raw} B / ${authenticatedWorkspaceJs.gzip} B.`,
].join(" "));
