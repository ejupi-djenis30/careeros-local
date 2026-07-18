/** Record a deterministic portfolio tour against an isolated local CareerOS vault. */

import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { createServer } from "node:net";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const frontendDir = join(repoRoot, "frontend");
const assetsDir = join(repoRoot, "docs", "assets");
const requireFromFrontend = createRequire(join(frontendDir, "package.json"));
const { chromium } = requireFromFrontend("playwright");

const demoUsername = "ada_demo";
const demoPassword = "AdaDemo2026!";
const viewport = { width: 1600, height: 900 };
const videoSize = { width: 1280, height: 720 };
const maxVideoBytes = 10 * 1024 * 1024;
const services = [];

function assertOwnedPath(target, parent) {
    const resolvedTarget = resolve(target);
    const resolvedParent = resolve(parent);
    const child = relative(resolvedParent, resolvedTarget);
    if (!child || child.startsWith("..") || isAbsolute(child)) {
        throw new Error(`Refusing to clean path outside ${resolvedParent}: ${resolvedTarget}`);
    }
}

function pythonExecutable() {
    const override = process.env.CAREEROS_DEMO_PYTHON;
    if (override) return resolve(repoRoot, override);
    const candidates = process.platform === "win32"
        ? [join(repoRoot, ".venv", "Scripts", "python.exe")]
        : [join(repoRoot, ".venv", "bin", "python")];
    const selected = candidates.find(existsSync);
    if (!selected) throw new Error("Create .venv and install requirements-dev.lock before recording the demo.");
    return selected;
}

async function freePort() {
    return new Promise((resolvePort, reject) => {
        const server = createServer();
        server.unref();
        server.on("error", reject);
        server.listen(0, "127.0.0.1", () => {
            const address = server.address();
            if (!address || typeof address === "string") return reject(new Error("Could not allocate a loopback port"));
            server.close(() => resolvePort(address.port));
        });
    });
}

function collectOutput(child, label) {
    const lines = [];
    const collect = (chunk) => {
        lines.push(...String(chunk).split(/\r?\n/).filter(Boolean));
        if (lines.length > 80) lines.splice(0, lines.length - 80);
    };
    child.stdout?.on("data", collect);
    child.stderr?.on("data", collect);
    child.demoOutput = () => lines.map((line) => `[${label}] ${line}`).join("\n");
    return child;
}

function startService(label, command, args, options = {}) {
    const child = collectOutput(spawn(command, args, {
        cwd: repoRoot,
        env: { ...process.env, ...options.env },
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
    }), label);
    services.push(child);
    return child;
}

async function runCommand(label, command, args, options = {}) {
    const child = collectOutput(spawn(command, args, {
        cwd: repoRoot,
        env: { ...process.env, ...options.env },
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
    }), label);
    const exitCode = await new Promise((resolveExit, reject) => {
        child.once("error", reject);
        child.once("exit", resolveExit);
    });
    if (exitCode !== 0) throw new Error(`${label} failed with exit code ${exitCode}\n${child.demoOutput()}`);
    return child.demoOutput();
}

async function waitFor(url, service, label, timeoutMs = 45_000) {
    const deadline = Date.now() + timeoutMs;
    let lastError = "not ready";
    while (Date.now() < deadline) {
        if (service.exitCode !== null) throw new Error(`${label} stopped early\n${service.demoOutput()}`);
        try {
            const response = await fetch(url, { redirect: "error" });
            if (response.ok) return;
            lastError = `HTTP ${response.status}`;
        } catch (error) {
            lastError = error.message;
        }
        await new Promise((resolveWait) => setTimeout(resolveWait, 250));
    }
    throw new Error(`${label} did not become ready: ${lastError}\n${service.demoOutput()}`);
}

async function terminate(child) {
    if (!child || child.exitCode !== null || !Number.isInteger(child.pid)) return;
    if (process.platform === "win32") {
        await new Promise((resolveExit) => {
            const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
                stdio: "ignore",
                windowsHide: true,
            });
            killer.once("exit", resolveExit);
            killer.once("error", resolveExit);
        });
        return;
    }
    child.kill("SIGTERM");
    await Promise.race([
        new Promise((resolveExit) => child.once("exit", resolveExit)),
        new Promise((resolveWait) => setTimeout(resolveWait, 2_000)),
    ]);
    if (child.exitCode === null) child.kill("SIGKILL");
}

async function launchBrowser() {
    const attempts = [
        { name: "bundled Chromium", options: {} },
        { name: "Google Chrome", options: { channel: "chrome" } },
        { name: "Microsoft Edge", options: { channel: "msedge" } },
    ];
    const failures = [];
    for (const attempt of attempts) {
        try {
            return await chromium.launch({ headless: process.env.CAREEROS_DEMO_HEADED !== "1", ...attempt.options });
        } catch (error) {
            failures.push(`${attempt.name}: ${error.message}`);
        }
    }
    throw new Error(`No compatible local Chromium browser could start.\n${failures.join("\n")}`);
}

async function assertCleanPage(page, runtimeErrors) {
    const visibleErrors = page.locator('[role="alert"]:visible, .state-panel--danger:visible, .inline-alert--danger:visible');
    if (await visibleErrors.count()) {
        throw new Error(`Visible UI error: ${(await visibleErrors.first().innerText()).trim()}`);
    }
    if (runtimeErrors.length) throw new Error(`Browser error: ${runtimeErrors.join(" | ")}`);
}

async function showScene(page, runtimeErrors, { navigation, heading, chapter, description, screenshot, waitForSavedDraft = false }) {
    if (navigation) await page.getByRole("link", { name: navigation, exact: true }).click();
    await page.getByRole("heading", { name: heading, level: 1 }).waitFor({ state: "visible" });
    await page.evaluate(() => {
        window.scrollTo({ top: 0, left: 0, behavior: "instant" });
        document.querySelector(".workspace-nav")?.scrollTo({ top: 0, left: 0, behavior: "instant" });
    });
    if (waitForSavedDraft) {
        // The editable canvas normalizes its initial document after mount, then
        // persists that single deterministic revision through the real autosave.
        await page.waitForTimeout(1_300);
        await page.waitForFunction(() => {
            const text = document.body.innerText;
            return !text.includes("Autosave in attesa")
                && !text.includes("Salvataggio automatico")
                && !text.includes("Modifiche non salvate");
        }, null, { timeout: 15_000 });
    }
    await page.waitForTimeout(500);
    await page.screencast.showChapter(chapter, { description, duration: 1_400 });
    await page.waitForTimeout(1_650);
    await page.evaluate(() => {
        window.scrollTo({ top: 0, left: 0, behavior: "instant" });
        document.querySelector(".workspace-nav")?.scrollTo({ top: 0, left: 0, behavior: "instant" });
        document.activeElement?.blur();
    });
    await page.waitForTimeout(150);
    await assertCleanPage(page, runtimeErrors);
    await page.screenshot({ path: screenshot, animations: "disabled" });
    await page.waitForTimeout(450);
}

async function recordTour(frontendUrl, python) {
    const rawVideo = join(assetsDir, "careeros-demo.webm");
    const screenshots = {
        workspace: join(assetsDir, "careeros-workspace.png"),
        vault: join(assetsDir, "careeros-vault.png"),
        resume: join(assetsDir, "careeros-resume-studio.png"),
        applications: join(assetsDir, "careeros-applications.png"),
    };
    const runtimeErrors = [];
    let authenticated = false;
    const browser = await launchBrowser();
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: "dark" });
    const page = await context.newPage();
    page.on("pageerror", (error) => runtimeErrors.push(`pageerror: ${error.message}`));
    page.on("console", (message) => {
        if (message.type() !== "error") return;
        const text = message.text();
        const expectedAnonymousRefresh = !authenticated
            && text.includes("Failed to load resource")
            && text.includes("401");
        const expectedMetaCspNotice = text.includes("'frame-ancestors' is ignored when delivered via a <meta>");
        if (!expectedAnonymousRefresh && !expectedMetaCspNotice) runtimeErrors.push(`console: ${text}`);
    });
    page.on("response", (response) => {
        const expectedAnonymousRefresh = !authenticated
            && response.status() === 401
            && response.url().endsWith("/auth/refresh");
        if (!expectedAnonymousRefresh && response.status() >= 400 && response.url().includes("/api/")) {
            runtimeErrors.push(`HTTP ${response.status()}: ${response.url()}`);
        }
    });

    try {
        await page.screencast.start({ path: rawVideo, size: videoSize, quality: 72 });
        await page.screencast.showActions({ position: "bottom-right", duration: 700, fontSize: 15 });
        await page.goto(frontendUrl, { waitUntil: "domcontentloaded" });
        await page.getByRole("heading", { name: "Bentornato" }).waitFor({ state: "visible" });
        await page.screencast.showChapter("CareerOS Local", {
            description: "A private, local-first workspace for the complete career journey",
            duration: 1_700,
        });
        await page.waitForTimeout(1_900);
        await page.getByLabel("Nome utente").fill(demoUsername);
        await page.getByLabel("Password").fill(demoPassword);
        await page.getByRole("button", { name: /Accedi al workspace/ }).click();
        await page.getByRole("heading", { name: "Il tuo spazio carriera", level: 1 }).waitFor({ state: "visible" });
        authenticated = true;

        await showScene(page, runtimeErrors, {
            heading: "Il tuo spazio carriera",
            chapter: "One private workspace",
            description: "Verified facts, resumes and applications stay on this device",
            screenshot: screenshots.workspace,
        });
        await showScene(page, runtimeErrors, {
            navigation: "Career Vault",
            heading: "Career Vault",
            chapter: "Verified career facts",
            description: "Every reusable claim has provenance, revision history and explicit status",
            screenshot: screenshots.vault,
        });
        await showScene(page, runtimeErrors, {
            navigation: "CV Studio",
            heading: "CV Studio",
            chapter: "Evidence-backed resumes",
            description: "ATS-ready drafts are generated only from confirmed profile facts",
            screenshot: screenshots.resume,
            waitForSavedDraft: true,
        });
        await showScene(page, runtimeErrors, {
            navigation: "Candidature",
            heading: "Candidature",
            chapter: "Immutable application pipeline",
            description: "Each opportunity keeps a local snapshot and append-only timeline",
            screenshot: screenshots.applications,
        });
        await page.screencast.showChapter("CareerOS Local", {
            description: "Private by design. Useful even without an AI model.",
            duration: 1_800,
        });
        await page.waitForTimeout(2_000);
        await assertCleanPage(page, runtimeErrors);
        await page.screencast.stop();
    } catch (error) {
        try { await page.screencast.stop(); } catch { /* recorder was not active */ }
        throw error;
    } finally {
        await context.close();
        await browser.close();
    }

    const videoStats = await stat(rawVideo);
    if (videoStats.size > maxVideoBytes) {
        throw new Error(`Demo video is ${(videoStats.size / 1024 / 1024).toFixed(1)} MiB; keep it below 10 MiB for GitHub.`);
    }
    await runCommand("demo previews", python, [
        join(repoRoot, "scripts", "render_demo_assets.py"),
        "--frames", screenshots.workspace, screenshots.vault, screenshots.resume, screenshots.applications,
        "--gif", join(assetsDir, "careeros-demo.gif"),
        "--poster", join(assetsDir, "careeros-demo-poster.jpg"),
    ]);
    return { rawVideo, screenshots };
}

async function main() {
    await mkdir(assetsDir, { recursive: true });

    const tempRoot = await mkdtemp(join(tmpdir(), "careeros-demo-"));
    const python = pythonExecutable();
    const backendPort = await freePort();
    const frontendPort = await freePort();
    const backendOrigin = `http://127.0.0.1:${backendPort}`;
    const frontendOrigin = `http://127.0.0.1:${frontendPort}`;
    const databasePath = join(tempRoot, "demo.db").replaceAll("\\", "/");
    const commonEnv = {
        DATABASE_URL: `sqlite:///${databasePath}`,
        DATA_DIR: join(tempRoot, "data"),
        SECRET_KEY: "career-os-portfolio-demo-local-secret-2026",
        OFFLINE_MODE: "true",
        LOCAL_INFERENCE_URL: "http://127.0.0.1:9",
        LOG_LEVEL: "WARNING",
        PYTHONUTF8: "1",
    };

    try {
        await runCommand("database migration", python, ["-m", "alembic", "upgrade", "head"], { env: commonEnv });
        const backend = startService("backend", python, [
            "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", String(backendPort), "--log-level", "warning",
        ], { env: commonEnv });
        await waitFor(`${backendOrigin}/api/v1/health/ready`, backend, "Backend");
        await runCommand("demo seed", python, [
            join(repoRoot, "scripts", "seed_demo.py"),
            "--base-url", backendOrigin,
            "--username", demoUsername,
            "--password", demoPassword,
        ], { env: commonEnv });

        const npmCli = process.env.npm_execpath;
        if (!npmCli) throw new Error("Run the recorder through npm so the local npm CLI can be resolved safely.");
        const frontend = startService("frontend", process.execPath, [
            npmCli, "--prefix", frontendDir, "run", "dev", "--", "--host", "127.0.0.1", "--port", String(frontendPort), "--strictPort",
        ], { env: { ...commonEnv, VITE_API_URL: `${backendOrigin}/api/v1` } });
        await waitFor(frontendOrigin, frontend, "Frontend");
        const result = await recordTour(frontendOrigin, python);
        const stats = await stat(result.rawVideo);
        console.log(`Demo recorded: ${relative(repoRoot, result.rawVideo)} (${(stats.size / 1024 / 1024).toFixed(1)} MiB)`);
    } finally {
        for (const child of services.reverse()) await terminate(child);
        assertOwnedPath(tempRoot, tmpdir());
        await rm(tempRoot, { recursive: true, force: true });
    }
}

main().catch((error) => {
    console.error(error.stack || error.message);
    process.exitCode = 1;
});
