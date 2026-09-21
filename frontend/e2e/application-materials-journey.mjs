/** Real local API journey. The only agent simulation submits the public MCP bridge DTO. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(frontend, "..");
const localPython = join(
    root,
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const python = process.env.CAREEROS_E2E_PYTHON || (existsSync(localPython) ? localPython : "python");
const temp = await mkdtemp(join(tmpdir(), "careeros-materials-vault-"));
const artifacts = await mkdtemp(join(tmpdir(), "careeros-materials-qa-"));
const services = [];
const username = "mira_demo";
const password = "MiraDemo2026!";
let browser;
let page;
let stage = "initialization";
const pause = (ms) => new Promise((done) => setTimeout(done, ms));

async function freePort() {
    return new Promise((done, reject) => {
        const server = createServer();
        server.on("error", reject);
        server.listen(0, "127.0.0.1", () => {
            const port = server.address().port;
            server.close(() => done(port));
        });
    });
}

function start(command, args, env, cwd = root) {
    const child = spawn(command, args, { cwd, env: { ...process.env, ...env }, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
    let output = "";
    child.stdout.on("data", (chunk) => { output = (output + chunk).slice(-6000); });
    child.stderr.on("data", (chunk) => { output = (output + chunk).slice(-6000); });
    child.failure = () => output;
    services.push(child);
    return child;
}

async function run(command, args, env) {
    const child = start(command, args, env);
    const code = await new Promise((done, reject) => { child.once("error", reject); child.once("exit", done); });
    assert.equal(code, 0, `Command failed during ${stage}: ${child.failure()}`);
}

async function ready(url, child) {
    const end = Date.now() + 45_000;
    while (Date.now() < end) {
        assert.equal(child.exitCode, null, `Local service stopped during ${stage}: ${child.failure()}`);
        try { if ((await fetch(url)).ok) return; } catch { /* Startup polling only. */ }
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

async function cleanOwned(target) {
    const child = relative(resolve(tmpdir()), resolve(target));
    assert(child && !child.startsWith("..") && !isAbsolute(child));
    await rm(target, { recursive: true, force: true, maxRetries: 4, retryDelay: 500 });
}

async function launch() {
    for (const channel of [undefined, "chrome", "msedge"]) {
        try { return await chromium.launch({ headless: true, ...(channel ? { channel } : {}) }); }
        catch { /* Try another already-installed browser; never download. */ }
    }
    throw new Error("No installed Chromium browser available");
}

try {
    const backendPort = await freePort();
    const frontendPort = await freePort();
    const backend = `http://127.0.0.1:${backendPort}`;
    const origin = `http://127.0.0.1:${frontendPort}`;
    const env = {
        DATABASE_URL: `sqlite:///${join(temp, "vault.db").replaceAll("\\", "/")}`,
        DATA_DIR: temp, SECRET_KEY: "synthetic-materials-journey-secret-key-local-only",
        OFFLINE_MODE: "true", LOCAL_INFERENCE_URL: "http://127.0.0.1:9",
        LOG_LEVEL: "WARNING", PYTHONUTF8: "1", CORS_ORIGINS: JSON.stringify([origin]),
    };
    stage = "isolated database migration";
    await run(python, ["-m", "alembic", "upgrade", "head"], env);
    const apiServer = start(python, ["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", String(backendPort), "--log-level", "warning"], env);
    await ready(`${backend}/api/v1/health/ready`, apiServer);
    stage = "synthetic profile and CV fixture";
    await run(python, ["scripts/seed_demo.py", "--base-url", backend, "--username", username, "--password", password], env);
    const login = await fetch(`${backend}/api/v1/auth/login`, { method: "POST", body: new URLSearchParams({ username, password }) });
    assert(login.ok);
    const ownerToken = (await login.json()).access_token;
    async function api(path, body, token = ownerToken, method = body ? "POST" : "GET") {
        const response = await fetch(`${backend}/api/v1${path}`, { method, headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
        assert(response.ok, `API ${method} ${path} returned ${response.status} during ${stage}`);
        return response.json();
    }
    const drafts = await api("/resumes");
    const baseline = await api(`/resumes/${drafts[0].id}`);
    const grant = await api("/automation/grants", { label: "Synthetic MCP journey", scopes: ["context:read", "proposals:write"], lifetime_days: 1, password, acknowledge_external_disclosure: true });
    const webServer = start(process.execPath, [join(frontend, "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", String(frontendPort), "--strictPort"], { VITE_API_URL: `${backend}/api/v1` }, frontend);
    await ready(origin, webServer);
    browser = await launch();
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true, locale: "en-GB" });
    const forbidden = [];
    await context.route("**/*", (route) => {
        const url = new URL(route.request().url());
        if ([origin, backend].includes(url.origin) || ["data:", "blob:"].includes(url.protocol)) return route.continue();
        forbidden.push(url.origin); return route.abort();
    });
    page = await context.newPage();
    page.setDefaultTimeout(15_000);
    stage = "browser login";
    await page.goto(origin);
    await page.getByLabel("Username", { exact: true }).fill(username);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Open workspace" }).click();
    await page.getByRole("heading", { name: "Your career workspace", level: 1 }).waitFor();
    stage = "manual opportunity creation";
    await page.goto(`${origin}/applications`);
    await page.getByRole("button", { name: "Add application", exact: true }).click();
    const form = page.locator("form.create-application");
    await form.getByLabel("Title", { exact: true }).fill("Python systems engineer");
    await form.getByLabel("Company", { exact: true }).fill("Synthetic Systems");
    await form.getByLabel("Location", { exact: true }).fill("Zurich");
    await form.getByLabel("Job URL").fill("https://example.test/jobs/python");
    await form.getByLabel("Job description").fill("Build reliable Python services, automated tests, and local systems. Work with the engineering team on production reliability, thoughtful documentation, and practical delivery. The role uses Python and supports clear technical communication.");
    await form.getByLabel("Resume version").selectOption(baseline.versions[0].id);
    const createdResponse = page.waitForResponse((response) => response.url() === `${backend}/api/v1/applications` && response.request().method() === "POST");
    await form.getByRole("button", { name: "Create application", exact: true }).click();
    const application = await (await createdResponse).json();
    assert(application.id);
    await page.getByRole("dialog").waitFor();
    stage = "targeted material request";
    await page.getByRole("link", { name: "Request materials via MCP" }).click();
    const requestDialog = page.getByRole("dialog");
    assert.equal(await requestDialog.getByRole("combobox", { name: /^Application/ }).inputValue(), application.id);
    assert.equal(await requestDialog.getByRole("combobox", { name: /^CV draft/ }).inputValue(), baseline.id);
    await requestDialog.getByRole("textbox", { name: /^Instructions/ }).fill("Prepare a short application from the confirmed Python skill. Keep every career statement cited.");
    const createdWork = page.waitForResponse((response) => response.url() === `${backend}/api/v1/agent-work` && response.request().method() === "POST");
    await requestDialog.getByRole("button", { name: "Create request", exact: true }).click();
    const work = await (await createdWork).json();
    assert.equal(work.target_application_id, application.id);
    assert.equal(work.target_resume_id, baseline.id);
    stage = "real MCP bridge context and proposal";
    const frozen = await api(`/agent-bridge/work-requests/${work.id}/context`, null, grant.token);
    const skill = frozen.facts.find((fact) => fact.title.includes("Python"));
    assert(skill, "Confirmed Python evidence must be present in the bounded context");
    const materialText = skill.title;
    const cited = (id) => ({ id, text: materialText, fact_ids: [skill.id] });
    await api(`/agent-bridge/work-requests/${work.id}/result`, {
        request_id: work.id, input_digest: work.input_digest, idempotency_key: "material-browser-journey-1", client: "Synthetic MCP test", model: "fixture",
        result: { contract_version: 1, kind: "materials", preset_id: work.preset_id, preset_version: work.preset_version, locale: work.locale,
            cv_selected_fact_ids: baseline.selected_fact_ids, cv_cited_overrides: [], cover_letter: [cited("letter-1")],
            email: { mode: "short", subject: "Application", body: [cited("email-1")], attachment_names: ["resume.pdf", "cover_letter.pdf"] },
            questions_answers: [{ ...cited("answer-1"), question: "Which skill?" }],
            requirements_to_evidence: [{ requirement: "Python", quote_text: "Python", fact_ids: [skill.id] }],
        },
    }, grant.token);
    stage = "owner proposal review and acceptance";
    await page.goto(`${origin}/agent-work`);
    await page.getByRole("button", { name: "Review proposal", exact: true }).click();
    await page.getByRole("button", { name: "Accept proposal", exact: true }).click();
    await page.getByRole("link", { name: "Open accepted application materials" }).click();
    const accepted = await api(`/applications/${application.id}/dossier-draft`);
    assert.equal(accepted.resume_draft_id, baseline.id);
    assert.equal(accepted.content.cover_letter, materialText);
    await page.waitForFunction((text) => Array.from(document.querySelectorAll("textarea")).some((node) => node.value === text), materialText);
    assert.equal(await page.getByRole("textbox", { name: /^Cover letter/ }).inputValue(), materialText);
    assert.equal(accepted.content.generation_provenance.source, "external-agent");
    assert.equal((await api(`/resumes/${baseline.id}`)).versions.length, baseline.versions.length, "Agent acceptance must never publish a CV");
    stage = "explicit publication of the exact approved CV";
    await page.getByRole("link", { name: "Open this CV in Resume Studio" }).click();
    await page.getByRole("button", { name: "Publish PDF + DOCX", exact: true }).waitFor();
    const publishedCv = page.waitForResponse((response) => response.url().endsWith(`/resumes/${baseline.id}/publish`) && response.request().method() === "POST");
    await page.getByRole("button", { name: "Publish PDF + DOCX", exact: true }).click();
    assert.equal((await publishedCv).status(), 201);
    const updatedCv = await api(`/resumes/${baseline.id}`);
    const approved = updatedCv.versions.find((version) => version.draft_revision === accepted.resume_draft_revision);
    assert(approved, "Publication must prove the exact approved draft revision");
    stage = "complete saved dossier editing";
    await page.goto(`${origin}/applications?applicationId=${application.id}`);
    await page.getByLabel("Approved CV version for the packet").selectOption(approved.id);
    await page.getByLabel("Include formatted letter documents").check();
    await page.getByLabel("Letter recipient", { exact: true }).fill("Synthetic Systems");
    await page.getByLabel("Letter date", { exact: true }).fill("2026-09-13");
    await page.getByLabel("Letter subject (optional)", { exact: true }).fill("Application — Python engineer");
    await page.getByRole("combobox", { name: /^Email style/ }).selectOption("motivational");
    await page.getByRole("textbox", { name: /^Email subject/ }).fill("Application — reviewed locally");
    await page.getByRole("textbox", { name: /^Email body/ }).fill(`${materialText}\n\nThank you for your consideration.`);
    const lastSave = page.waitForResponse((response) => response.url().endsWith(`/applications/${application.id}/dossier-draft`)
        && response.request().method() === "PUT" && response.request().postDataJSON()?.content?.answers?.[0]?.answer === `${materialText}.`);
    await page.getByRole("textbox", { name: /^Your answer/ }).fill(`${materialText}.`);
    assert.equal((await lastSave).status(), 200);
    await page.getByText("Draft saved on this device.", { exact: true }).waitFor();
    const saved = await api(`/applications/${application.id}/dossier-draft`);
    assert.equal(saved.content.email_draft.mode, "motivational");
    assert.equal(saved.content.email_draft.subject, "Application — reviewed locally");
    assert.equal(saved.content.answers[0].answer, `${materialText}.`);
    stage = "accessibility and responsive editor";
    await page.addScriptTag({ url: `${origin}/node_modules/axe-core/axe.min.js` });
    const violations = await page.evaluate(async () => (await window.axe.run(document.querySelector('[role="dialog"]'), { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } })).violations.map((item) => ({ id: item.id, impact: item.impact, targets: item.nodes.map((node) => node.target) })));
    assert.deepEqual(violations, []);
    assert(await page.locator(".applications-workspace__background").evaluate((node) => node.inert));
    assert(await page.locator("#root").evaluate((node) => node.inert), "Sidebar and all background controls must be inert");
    await page.locator(".dossier-materials").evaluate((node) => node.scrollIntoView({ block: "start" }));
    await page.screenshot({ path: join(artifacts, "dossier-desktop.png") });
    for (const width of [390, 320]) {
        await page.setViewportSize({ width, height: 900 });
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Viewport overflow at ${width}`);
        await page.getByRole("dialog").focus();
        for (let i = 0; i < 5; i++) await page.keyboard.press("Shift+Tab");
        assert(await page.evaluate(() => Boolean(document.activeElement.closest('[role="dialog"]'))));
        assert(await page.getByRole("dialog").evaluate((node) => node.scrollWidth <= node.clientWidth + 1), `Editor overflow at ${width}`);
        await page.locator(".dossier-materials").evaluate((node) => node.scrollIntoView({ block: "start" }));
        const mobileViolations = await page.evaluate(async () => (await window.axe.run(document.querySelector('[role="dialog"]'), { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } })).violations.map((item) => item.id));
        assert.deepEqual(mobileViolations, []);
        await page.screenshot({ path: join(artifacts, `dossier-${width}.png`) });
        await page.locator(".dossier-materials > fieldset").nth(1).evaluate((node) => node.scrollIntoView({ block: "start" }));
        await page.screenshot({ path: join(artifacts, `email-${width}.png`) });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    stage = "immutable dossier publication and download";
    const packetResponse = page.waitForResponse((response) => response.url().endsWith(`/applications/${application.id}/dossiers`) && response.request().method() === "POST");
    await page.getByRole("button", { name: "Publish dossier version", exact: true }).click();
    const publishedResponse = await packetResponse;
    assert.equal(publishedResponse.status(), 201);
    const published = await publishedResponse.json();
    assert.equal(published.current_stage, "saved");
    const downloads = {};
    for (const name of ["resume.pdf", "resume.docx", "cover_letter.pdf", "cover_letter.docx", "email_draft.eml", "email_checklist.txt", "ZIP"]) {
        const downloadEvent = page.waitForEvent("download");
        await page.getByRole("button", { name: `Download ${name}`, exact: false }).click();
        const download = await downloadEvent;
        const path = join(artifacts, name === "ZIP" ? "packet.zip" : name);
        await download.saveAs(path);
        downloads[name] = createHash("sha256").update(await readFile(path)).digest("hex");
    }
    const immutableId = published.dossiers[0].id;
    const redownload = await fetch(`${backend}/api/v1/applications/${application.id}/dossiers/${immutableId}/download`, { headers: { Authorization: `Bearer ${ownerToken}` } });
    assert(redownload.ok);
    assert.equal(createHash("sha256").update(Buffer.from(await redownload.arrayBuffer())).digest("hex"), downloads.ZIP);
    assert.deepEqual(forbidden, [], "No browser request may leave the isolated loopback services");
    await run(python, ["frontend/e2e/verify_material_packet.py", artifacts], env);
    console.log(`PASS real local material journey; desktop/390/320 screenshots and verified documents: ${artifacts}`);
} catch (error) {
    if (page) {
        console.error(await page.evaluate(() => ({ url: location.pathname, textareas: document.querySelectorAll("textarea").length,
            labels: Array.from(document.querySelectorAll("textarea")).map((node) => ({ label: node.closest("label")?.querySelector("span")?.textContent, ariaLabel: node.getAttribute("aria-label") })),
            alerts: document.querySelectorAll('[role="alert"]').length,
        })).catch(() => ({ diagnostics: "unavailable" })));
        await page.locator('[aria-labelledby="dossier-title"]').screenshot({ path: join(artifacts, "dossier-failure.png"), timeout: 1000 }).catch(() => {});
    }
    if (page) await page.screenshot({ path: join(artifacts, "failure.png"), fullPage: true }).catch(() => {});
    console.error(`FAIL during ${stage}; synthetic QA artifacts: ${artifacts}`);
    throw error;
} finally {
    await browser?.close();
    for (const child of services.reverse()) await stop(child);
    await cleanOwned(temp);
}
