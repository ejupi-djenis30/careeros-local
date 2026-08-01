import { readdir, readFile, writeFile } from "node:fs/promises";
import { extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = resolve(fileURLToPath(new URL("../", import.meta.url)));
const sourceRoot = resolve(repositoryRoot, "frontend/src");
const iconRoot = resolve(repositoryRoot, "frontend/node_modules/bootstrap-icons/icons");
const outputPath = resolve(sourceRoot, "bootstrap-icons-subset.css");
const shellOutputPath = resolve(sourceRoot, "shell-icons.css");
const shellSourcePaths = [
    resolve(sourceRoot, "components/DesktopBoot.jsx"),
    resolve(sourceRoot, "components/Login.jsx"),
    resolve(sourceRoot, "components/RecoveryShell.jsx"),
    resolve(sourceRoot, "context/AuthContext.jsx"),
    resolve(sourceRoot, "i18n/LanguageSwitcher.jsx"),
];
const checkOnly = process.argv.includes("--check");
const iconPattern = /(?<![A-Za-z0-9-])bi-([a-z0-9]+(?:-[a-z0-9]+)*)/g;

async function sourceFiles(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    const nested = await Promise.all(entries.map(async (entry) => {
        const path = resolve(directory, entry.name);
        if (entry.isDirectory()) return sourceFiles(path);
        return [".js", ".jsx"].includes(extname(entry.name)) ? [path] : [];
    }));
    return nested.flat();
}

function optimizeSvg(svg, iconName) {
    const match = svg.match(/<svg\b[^>]*>([\s\S]*?)<\/svg>/);
    if (!match) throw new Error(`Bootstrap icon is not a valid SVG: ${iconName}`);
    const body = match[1]
        .replace(/<!--[\s\S]*?-->/g, "")
        .replace(/>\s+</g, "><")
        .trim();
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">${body}</svg>`;
}

function svgDataUrl(svg) {
    const payload = svg
        .replaceAll("%", "%25")
        .replaceAll("#", "%23")
        .replaceAll('"', "'")
        .replaceAll("<", "%3C")
        .replaceAll(">", "%3E");
    return `url("data:image/svg+xml,${payload}")`;
}

async function referencedIcons(files) {
    const names = new Set();
    const candidates = files ?? await sourceFiles(sourceRoot);
    for (const file of candidates) {
        const source = await readFile(file, "utf8");
        if (/bi-\$\{/.test(source) || /["']bi-["']\s*\+/.test(source)) {
            throw new Error(
                `Computed Bootstrap icon name in ${file}. Use explicit bi-* tokens so the subset is auditable.`,
            );
        }
        for (const match of source.matchAll(iconPattern)) names.add(match[0]);
    }
    return [...names].sort();
}

async function renderStylesheet(files) {
    const names = await referencedIcons(files);
    const rules = [];
    for (const className of names) {
        const iconName = className.slice(3);
        let source;
        try {
            source = await readFile(resolve(iconRoot, `${iconName}.svg`), "utf8");
        } catch {
            throw new Error(`Referenced Bootstrap icon does not exist: ${className}`);
        }
        rules.push(`.${className} { --careeros-icon: ${svgDataUrl(optimizeSvg(source, iconName))}; }`);
    }

    return `/*!
 * Generated from Bootstrap Icons v1.13.1 (https://icons.getbootstrap.com/)
 * Copyright 2019-2024 The Bootstrap Authors · MIT License
 * Run: npm run icons:build
 */

.bi::before,
[class^="bi-"]::before,
[class*=" bi-"]::before {
  display: inline-block;
  width: 1em;
  height: 1em;
  background-color: currentColor;
  content: "";
  -webkit-mask: var(--careeros-icon) center / contain no-repeat;
  mask: var(--careeros-icon) center / contain no-repeat;
  vertical-align: -0.125em;
}

${rules.join("\n")}
`;
}

const expected = await renderStylesheet();
const shellExpected = await renderStylesheet(shellSourcePaths);
if (checkOnly) {
    const readCurrent = async (path) => {
        try {
            return await readFile(path, "utf8");
        } catch {
            return "";
        }
    };
    const [current, shellCurrent] = await Promise.all([
        readCurrent(outputPath),
        readCurrent(shellOutputPath),
    ]);
    if (current !== expected || shellCurrent !== shellExpected) {
        throw new Error("Frontend icon subset is stale. Run `npm run icons:build`.");
    }
    console.log(
        `Frontend icon subsets are current (${(expected.match(/^\.bi-/gm) ?? []).length} workspace, `
        + `${(shellExpected.match(/^\.bi-/gm) ?? []).length} lifecycle icons).`,
    );
} else {
    await Promise.all([
        writeFile(outputPath, expected, "utf8"),
        writeFile(shellOutputPath, shellExpected, "utf8"),
    ]);
    console.log(`Wrote ${outputPath} and ${shellOutputPath}`);
}
