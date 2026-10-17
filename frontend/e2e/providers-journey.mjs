/** Real authenticated provider API and browser journey with all acquisition offline. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(frontend, "..");
const python = process.env.CAREEROS_E2E_PYTHON || "python";
const vault = await mkdtemp(join(tmpdir(), "careeros-provider-vault-"));
const artifacts = await mkdtemp(join(tmpdir(), "careeros-provider-qa-"));
const services = [];
const pause = (ms) => new Promise((done) => setTimeout(done, ms));
const username = "synthetic_provider_owner";
const password = `${randomUUID()}Aa1!`;
let browser;
let page;
let stage = "initialization";

async function freePort() {
    return new Promise((done, reject) => {
        const server = createServer();
        server.once("error", reject);
        server.listen(0, "127.0.0.1", () => {
            const port = server.address().port;
            server.close(() => done(port));
        });
    });
}
function start(command, args, env, cwd = root) {
    const child = spawn(command, args, { cwd, env: { ...process.env, ...env }, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
    let output = "";
    child.stdout.on("data", (chunk) => { output = (output + chunk).slice(-4000); });
    child.stderr.on("data", (chunk) => { output = (output + chunk).slice(-4000); });
    child.failure = () => output;
    services.push(child);
    return child;
}
async function ready(url, child) {
    const deadline = Date.now() + 45_000;
    while (Date.now() < deadline) {
        assert.equal(child.exitCode, null, `Local service stopped during ${stage}: ${child.failure()}`);
        try { if ((await fetch(url, { signal: AbortSignal.timeout(2000) })).ok) return; } catch { /* Startup polling. */ }
        await pause(200);
    }
    throw new Error(`Local service did not become ready during ${stage}`);
}
async function stop(child) {
    if (child.exitCode !== null || !child.pid) return;
    if (process.platform === "win32") {
        await new Promise((done) => {
            const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], { windowsHide: true, stdio: "ignore" });
            killer.once("error", done); killer.once("exit", done);
        });
    } else child.kill("SIGTERM");
    await Promise.race([new Promise((done) => child.once("exit", done)), pause(1500)]);
    if (child.exitCode === null) child.kill("SIGKILL");
}
async function cleanVault() {
    const contained = relative(resolve(tmpdir()), resolve(vault));
    assert(contained && !contained.startsWith("..") && !isAbsolute(contained));
    await rm(vault, { recursive: true, force: true, maxRetries: 4, retryDelay: 500 });
}
async function launch() {
    for (const channel of [undefined, "chrome", "msedge"]) {
        try { return await chromium.launch({ headless: true, ...(channel ? { channel } : {}) }); }
        catch { /* Use only an already installed browser. */ }
    }
    throw new Error("No installed Chromium browser available");
}

try {
    const backendPort = await freePort();
    const frontendPort = await freePort();
    const backend = `http://127.0.0.1:${backendPort}`;
    const origin = `http://127.0.0.1:${frontendPort}`;
    const env = {
        DATABASE_URL: `sqlite:///${join(vault, "vault.db").replaceAll("\\", "/")}`,
        DATA_DIR: vault, SECRET_KEY: "synthetic-provider-journey-local-test-only",
        OFFLINE_MODE: "true", LOCAL_INFERENCE_URL: "http://127.0.0.1:9",
        LOG_LEVEL: "WARNING", PYTHONUTF8: "1", CORS_ORIGINS: JSON.stringify([origin]),
    };
    stage = "disposable database migration";
    const migration = start(python, ["-m", "alembic", "upgrade", "head"], env);
    const code = await new Promise((done, reject) => { migration.once("error", reject); migration.once("exit", done); });
    assert.equal(code, 0, `Migration failed: ${migration.failure()}`);
    const apiServer = start(python, ["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", String(backendPort), "--log-level", "warning"], env);
    await ready(`${backend}/api/v1/health/ready`, apiServer);
    const request = async (path, { method = "GET", body, token } = {}) => fetch(`${backend}/api/v1${path}`, {
        method, headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body ? { "Content-Type": "application/json" } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(15_000),
    });
    const register = async (name) => {
        const response = await request("/auth/register", { method: "POST", body: { username: name, password } });
        assert.equal(response.status, 200, "Synthetic account registration must succeed");
    };
    const loginToken = async (name) => {
        const response = await fetch(`${backend}/api/v1/auth/login`, { method: "POST", body: new URLSearchParams({ username: name, password }) });
        assert(response.ok, "Synthetic account authentication must succeed");
        return (await response.json()).access_token;
    };
    await register(username);
    const token = await loginToken(username);
    stage = "source browser server";
    const web = start(process.execPath, [join(frontend, "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", String(frontendPort), "--strictPort"], { VITE_API_URL: `${backend}/api/v1` }, frontend);
    await ready(origin, web);
    browser = await launch();
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: "en-GB", acceptDownloads: true });
    const forbidden = [];
    await context.route("**/*", (route) => {
        const url = new URL(route.request().url());
        if ([origin, backend].includes(url.origin) || ["data:", "blob:"].includes(url.protocol)) return route.continue();
        forbidden.push(url.origin);
        return route.abort();
    });
    page = await context.newPage();
    page.setDefaultTimeout(15_000);
    const providerLocales = [];
    page.on("request", (outgoing) => {
        const language = new URL(outgoing.url()).pathname.match(/\/providers-(en|it)\.js$/)?.[1];
        if (language) providerLocales.push(language);
    });
    stage = "authenticated provider navigation without a local model";
    await page.goto(`${origin}/providers`);
    await page.getByLabel("Username", { exact: true }).fill(username);
    await page.getByLabel("Password", { exact: true }).fill(password);
    assert.deepEqual(providerLocales, [], "Provider vocabulary must not load on login");
    await page.getByRole("button", { name: "Open workspace" }).click();
    await page.getByRole("heading", { name: "Bring your own job sources" }).waitFor();
    assert.deepEqual(providerLocales, ["en"], "Provider entry must load only the selected local language");
    assert.equal((await (await request("/job-providers", { token })).json()).installed.length, 0);
    assert.equal(await page.getByRole("checkbox", { name: /Enable imported providers immediately/ }).isChecked(), false);
    let tests = 0;
    page.on("request", (outgoing) => { if (outgoing.url().endsWith("/test") && outgoing.method() === "POST") tests += 1; });

    stage = "disabled creation and confidential-header redaction";
    await page.getByLabel("Display name", { exact: true }).fill("Synthetic Provider");
    await page.getByLabel("Stable key", { exact: true }).fill("synthetic_provider");
    await page.getByLabel("HTTPS origin", { exact: true }).fill("https://example.com");
    await page.locator(".provider-advanced summary").click();
    await page.getByLabel("Static headers (JSON)", { exact: false }).fill(JSON.stringify({ "X-API-Key": "synthetic-confidential-header" }));
    const createResponse = page.waitForResponse((response) => response.url() === `${backend}/api/v1/job-providers` && response.request().method() === "POST");
    await page.getByRole("button", { name: "Save provider", exact: true }).click();
    const createdResponse = await createResponse;
    assert.equal(createdResponse.status(), 201);
    const created = await createdResponse.json();
    assert.equal(created.enabled, false);
    assert.equal(created.revision, 1);
    assert.equal(created.request.headers["X-API-Key"], "••••••••");
    assert.equal(JSON.stringify(created).includes("synthetic-confidential-header"), false);
    await page.getByText("Provider saved. Enabled sources will join the next search.", { exact: true }).waitFor();
    assert.equal(tests, 0, "Saving must not acquire provider data");
    assert.equal(await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]).includes("synthetic-confidential-header")), false);

    stage = "provider-only backup through the real home controls";
    assert.equal((await request("/career-profile", { token })).status, 404);
    await page.goto(origin);
    await page.getByRole("heading", { name: "Your career workspace", level: 1 }).waitFor();
    const backup = page.getByRole("button", { name: "Create backup", exact: true });
    assert(await backup.isEnabled(), "Provider-only data must be exportable from the interface");
    const backupResponse = page.waitForResponse((response) => response.url().endsWith("/portability/export"));
    const backupDownload = page.waitForEvent("download");
    await backup.click();
    const exported = await backupResponse;
    assert.equal(exported.status(), 200);
    const download = await backupDownload;
    assert.equal(await download.failure(), null);
    assert.match(download.suggestedFilename(), /^careeros-backup-.*\.zip$/);
    const downloadedBytes = await readFile(await download.path());
    assert(downloadedBytes.byteLength > 4, "The actual browser download must contain the archive");
    assert.equal(downloadedBytes.subarray(0, 4).toString("hex"), "504b0304");
    const digest = createHash("sha256").update(downloadedBytes).digest("hex");
    assert.equal(exported.headers()["x-content-sha256"], digest);
    await page.getByText("Backup checked in memory and sent to your browser downloads. CareerOS cannot verify the browser’s final destination.", { exact: true }).waitFor();
    assert.equal((await request("/career-profile", { token })).status, 404, "Backup must not invent a career profile");
    await page.goto(`${origin}/providers`);
    await page.getByRole("heading", { name: "Bring your own job sources" }).waitFor();
    await page.locator(".provider-card").filter({ hasText: "Synthetic Provider" }).getByRole("button", { name: "Edit", exact: true }).click();

    stage = "private-network validation failure without mutation";
    await page.getByLabel("HTTPS origin", { exact: true }).fill("http://127.0.0.1");
    const validation = page.waitForResponse((response) => response.url().endsWith("/job-providers/validate") && response.request().method() === "POST");
    await page.getByRole("button", { name: "Save provider", exact: true }).click();
    assert.equal((await validation).status(), 422);
    await page.locator(".provider-workspace__message").waitFor();
    assert.equal((await (await request(`/job-providers/${created.id}`, { token })).json()).revision, 1);
    await page.getByLabel("HTTPS origin", { exact: true }).fill("https://example.com");

    stage = "optimistic revision conflict and owner retry";
    const configuration = {
        key: "synthetic_provider", display_name: "Changed in another owner tab", description: "",
        adapter_kind: "json", enabled: false,
        request: { ...created.request, headers: { "X-API-Key": "__CAREEROS_PRESERVE_SECRET__" } },
        extraction: created.extraction, capabilities: created.capabilities, expected_revision: 1,
    };
    const concurrent = await request(`/job-providers/${created.id}`, { method: "PUT", body: configuration, token });
    assert.equal(concurrent.status, 200);
    assert.equal((await concurrent.json()).revision, 2);
    const conflict = page.waitForResponse((response) => response.url().endsWith(`/job-providers/${created.id}`) && response.request().method() === "PUT");
    await page.getByRole("button", { name: "Save provider", exact: true }).click();
    assert.equal((await conflict).status(), 409);
    await page.reload();
    await page.getByRole("heading", { name: "Bring your own job sources" }).waitFor();
    const card = page.locator(".provider-card").filter({ hasText: "Changed in another owner tab" });
    await card.getByRole("button", { name: "Edit", exact: true }).click();
    await page.getByLabel("Display name", { exact: true }).fill("Reviewed Synthetic Provider");
    const updated = page.waitForResponse((response) => response.url().endsWith(`/job-providers/${created.id}`) && response.request().method() === "PUT");
    await page.getByRole("button", { name: "Save provider", exact: true }).click();
    const update = await updated;
    assert.equal(update.status(), 200);
    assert.equal((await update.json()).revision, 3);
    await page.getByText("Provider saved. Enabled sources will join the next search.", { exact: true }).waitFor();

    stage = "explicit activation and one-shot network consent with offline rejection";
    const reviewed = page.locator(".provider-card").filter({ hasText: "Reviewed Synthetic Provider" });
    await reviewed.getByRole("button", { name: "Enable network access", exact: true }).click();
    await page.getByText("Provider enabled. It can participate in the next search.", { exact: true }).waitFor();
    page.once("dialog", (dialog) => dialog.dismiss());
    await reviewed.getByRole("button", { name: "Test", exact: true }).click();
    assert.equal(tests, 0, "Declined consent must not call even the local test endpoint");
    page.once("dialog", (dialog) => { assert(dialog.message().includes("software engineer")); return dialog.accept(); });
    const offlineTest = page.waitForResponse((response) => response.url().endsWith(`/job-providers/${created.id}/test`));
    await reviewed.getByRole("button", { name: "Test", exact: true }).click();
    const tested = await offlineTest;
    assert.equal(tested.status(), 503);
    assert.equal(tested.request().postDataJSON().allow_network, true);
    await page.getByText("Provider network access is disabled", { exact: true }).waitFor();

    stage = "disabled JSON document and bundled pack import";
    const importedConfig = { ...configuration, key: "synthetic_import", display_name: "Imported Synthetic Provider", request: { ...configuration.request, headers: {} } };
    delete importedConfig.expected_revision;
    const document = { kind: "provider", format_version: 1, provider: { kind: "declarative", configuration: importedConfig } };
    const importedDocument = page.waitForResponse((response) => response.url().endsWith("/job-providers/import"));
    await page.getByLabel("Provider or provider-pack JSON file", { exact: false }).setInputFiles({ name: "synthetic-provider.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(document)) });
    assert.equal((await importedDocument).status(), 201);
    await page.getByText("Imported 1 provider(s).", { exact: true }).waitFor();
    const importedPack = page.waitForResponse((response) => /\/job-providers\/packs\/[^/]+\/import$/.test(response.url()));
    await page.getByRole("button", { name: "Import pack", exact: true }).click();
    assert.equal((await importedPack).status(), 201);
    const installed = (await (await request("/job-providers", { token })).json()).installed;
    assert(installed.length > 2);
    assert(installed.filter((item) => item.id !== created.id).every((item) => item.enabled === false));
    assert.equal(tests, 1);

    stage = "keyboard, accessibility and responsive source controls";
    await page.addScriptTag({ url: `${origin}/node_modules/axe-core/axe.min.js` });
    for (const width of [1440, 390, 320]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.getByLabel("Stable key", { exact: true }).focus();
        await page.keyboard.press("Tab");
        assert.equal(await page.evaluate(() => document.activeElement?.tagName), "TEXTAREA");
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Viewport overflow at ${width}`);
        const violations = await page.evaluate(async () => (await window.axe.run(document.querySelector("main"), {
            runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
        })).violations.map((item) => ({ id: item.id, impact: item.impact, targets: item.nodes.map((node) => node.target) })));
        assert.deepEqual(violations, []);
        await page.screenshot({ path: join(artifacts, `providers-${width}.png`), fullPage: true });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    stage = "account isolation and explicit deletion";
    await register("synthetic_provider_other");
    const otherToken = await loginToken("synthetic_provider_other");
    assert.equal((await request(`/job-providers/${created.id}`, { token: otherToken })).status, 404);
    assert.equal((await (await request("/job-providers", { token: otherToken })).json()).installed.length, 0);
    page.once("dialog", (dialog) => dialog.accept());
    const deleted = page.waitForResponse((response) => response.url().includes(`/job-providers/${created.id}?`) && response.request().method() === "DELETE");
    await page.locator(".provider-card").filter({ hasText: "Reviewed Synthetic Provider" }).getByRole("button", { name: "Delete", exact: true }).click();
    assert.equal((await deleted).status(), 204);
    assert.equal((await request(`/job-providers/${created.id}`, { token })).status, 404);
    stage = "local feature language switching without losing the draft";
    await page.getByLabel("Display name", { exact: true }).fill("Unsubmitted local draft");
    await page.getByRole("button", { name: "IT Italian", exact: true }).click();
    await page.getByRole("heading", { name: "Aggiungi le tue sorgenti di lavoro" }).waitFor();
    assert.equal(await page.getByLabel("Nome visualizzato", { exact: true }).inputValue(), "Unsubmitted local draft");
    assert.deepEqual([...new Set(providerLocales)].sort(), ["en", "it"]);
    assert.deepEqual(forbidden, [], "No browser request may leave the isolated loopback services");
    console.log(`PASS real provider CRUD/import/revision/consent/isolation journey; synthetic screenshots: ${artifacts}`);
} catch (error) {
    if (page) await page.screenshot({ path: join(artifacts, "failure.png"), fullPage: true }).catch(() => {});
    console.error(`FAIL provider journey during ${stage}; synthetic screenshots: ${artifacts}`);
    throw error;
} finally {
    await browser?.close();
    for (const child of services.reverse()) await stop(child);
    await cleanVault();
}
