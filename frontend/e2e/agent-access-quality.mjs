import assert from "node:assert/strict";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const frontendRoot = resolve(fileURLToPath(new URL("../", import.meta.url)));
const distributionRoot = resolve(frontendRoot, "dist");
const axePath = resolve(frontendRoot, "node_modules/axe-core/axe.min.js");
const widths = [320, 390, 1440];
const languages = {
    en: {
        pageTitle: "Agent access",
        label: "Client label",
    },
    it: {
        pageTitle: "Accesso agenti",
        label: "Etichetta del client",
    },
};
const secretToken = "careeros_mcp_v1_BROWSER_QA_SECRET_abcdefghijklmnopqrstuvwxyz012345";
const existingGrant = {
    id: "0f439ba0-8f52-4a2f-b56d-902e38f73ee0",
    label: "Existing quality grant",
    scopes: ["system:read"],
    expires_at: "2030-08-29T10:00:00Z",
    revoked_at: null,
    created_at: "2026-07-30T00:00:00Z",
};
const issuedGrant = {
    ...existingGrant,
    id: "73c2e420-bf74-4fd9-b2f5-387114140d11",
    label: "Playwright quality client",
};
const contentTypes = new Map([
    [".avif", "image/avif"],
    [".css", "text/css; charset=utf-8"],
    [".html", "text/html; charset=utf-8"],
    [".js", "text/javascript; charset=utf-8"],
    [".json", "application/json; charset=utf-8"],
    [".png", "image/png"],
    [".svg", "image/svg+xml"],
    [".webp", "image/webp"],
]);

function distributionPath(requestUrl) {
    const pathname = decodeURIComponent(new URL(requestUrl ?? "/", "http://127.0.0.1").pathname);
    const requested = pathname === "/" ? "/index.html" : pathname;
    const candidate = resolve(distributionRoot, `.${requested}`);
    const relativePath = relative(distributionRoot, candidate);
    if (relativePath === ".." || relativePath.startsWith(`..${sep}`)) return null;
    return candidate;
}

function startServer() {
    const server = createServer(async (request, response) => {
        const requestUrl = request.url ?? "/";
        const pathname = new URL(requestUrl, "http://127.0.0.1").pathname;
        const requestedPath = pathname === "/__axe.js"
            ? axePath
            : distributionPath(requestUrl);
        let path = requestedPath;
        try {
            const metadata = path ? await stat(path) : null;
            if (!metadata?.isFile()) throw new Error("Not a file");
        } catch {
            path = extname(pathname) ? null : resolve(distributionRoot, "index.html");
        }
        if (!path) {
            response.writeHead(404).end("Not found");
            return;
        }
        try {
            const metadata = await stat(path);
            response.writeHead(200, {
                "Cache-Control": "no-store",
                "Content-Length": metadata.size,
                "Content-Type": contentTypes.get(extname(path)) ?? "application/octet-stream",
            });
            createReadStream(path).pipe(response);
        } catch {
            response.writeHead(404).end("Not found");
        }
    });
    return new Promise((resolveServer, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", () => resolveServer(server));
    });
}

function closeServer(server) {
    return new Promise((resolveClose, reject) => {
        server.close((error) => (error ? reject(error) : resolveClose()));
    });
}

function json(route, status, body) {
    return route.fulfill({
        status,
        contentType: "application/json",
        headers: {
            "Cache-Control": "no-store, max-age=0",
            Pragma: "no-cache",
        },
        body: JSON.stringify(body),
    });
}

async function installApiMock(page) {
    let grants = [{ ...existingGrant }];
    await page.route("**/api/v1/**", async (route) => {
        const request = route.request();
        const url = new URL(request.url());
        const path = url.pathname.replace(/^\/api\/v1/, "");
        if (path === "/auth/refresh") {
            return json(route, 200, {
                access_token: "browser-quality-access-token",
                token_type: "bearer",
                username: "quality-user",
            });
        }
        if (path === "/search/status/all") return json(route, 200, {});
        if (path === "/local-model/status") {
            return json(route, 200, {
                available: true,
                ready: true,
                configured_model: "quality-local-model",
                installed_models: ["quality-local-model"],
                error_code: null,
                runtime: "llama.cpp",
            });
        }
        if (path === "/automation/grants" && request.method() === "GET") {
            return json(route, 200, grants);
        }
        if (path === "/automation/grants" && request.method() === "POST") {
            const payload = request.postDataJSON();
            if (payload.password !== "CurrentPassword1") {
                return json(route, 403, {
                    detail: {
                        code: "authentication_failed",
                        message: "Current CareerOS password verification failed",
                    },
                });
            }
            grants = [
                { ...issuedGrant },
                ...grants.filter((grant) => grant.id !== issuedGrant.id),
            ];
            return json(route, 201, {
                grant: { ...issuedGrant },
                token: secretToken,
                token_environment_variable: "CAREEROS_MCP_TOKEN",
                warning: (
                    "This token is shown once. Store it in your OS credential manager "
                    + "and never commit it."
                ),
            });
        }
        const revokeMatch = path.match(/^\/automation\/grants\/([^/]+)\/revoke$/);
        if (revokeMatch && request.method() === "POST") {
            const payload = request.postDataJSON();
            if (payload.password !== "CurrentPassword1") {
                return json(route, 403, {
                    detail: {
                        code: "authentication_failed",
                        message: "Current CareerOS password verification failed",
                    },
                });
            }
            const grant = grants.find((item) => item.id === revokeMatch[1]);
            if (!grant) {
                return json(route, 404, {
                    detail: {
                        code: "grant_not_found",
                        message: "Automation grant not found",
                    },
                });
            }
            const revoked = {
                ...grant,
                revoked_at: grant.revoked_at ?? "2026-07-31T00:20:00Z",
            };
            grants = grants.map((item) => item.id === revoked.id ? revoked : item);
            return json(route, 200, revoked);
        }
        if (path === "/career-profile") {
            return json(route, 200, {
                revision: 0,
                display_name: "quality-user",
                headline: null,
                summary: null,
                email: null,
                phone: null,
                location: {},
                birth_date: null,
                nationality: null,
                work_authorization: [],
                website: null,
                linkedin: null,
                github: null,
                preferences: {},
                facts: [],
                goals: [],
                analysis: null,
            });
        }
        if (path === "/search/sources" || path === "/resumes/versions") {
            return json(route, 200, []);
        }
        return json(route, 200, {});
    });
}

async function createPage(browser, baseUrl, language, width, contextOverrides = {}) {
    const context = await browser.newContext({
        bypassCSP: true,
        colorScheme: "dark",
        reducedMotion: "reduce",
        viewport: { width, height: width <= 390 ? 900 : 960 },
        ...contextOverrides,
    });
    await context.addInitScript((savedLanguage) => {
        window.localStorage.setItem("careeros.interface-language", savedLanguage);
        window.__careerosClipboardWrites = [];
        Object.defineProperty(window.navigator, "clipboard", {
            configurable: true,
            value: {
                writeText: async (value) => {
                    window.__careerosClipboardWrites.push(value);
                },
            },
        });
    }, language);
    const page = await context.newPage();
    const consoleProblems = [];
    const pageErrors = [];
    page.on("console", (message) => {
        if (["error", "warning"].includes(message.type())) {
            consoleProblems.push(message.text());
        }
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await installApiMock(page);
    await page.goto(`${baseUrl}agent-access`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: languages[language].pageTitle, level: 1 }).waitFor();
    return { context, page, consoleProblems, pageErrors };
}

async function accessibilityViolations(page, baseUrl) {
    if (!(await page.evaluate(() => Boolean(window.axe)))) {
        await page.addScriptTag({ url: `${baseUrl}__axe.js` });
    }
    return page.evaluate(async () => {
        const result = await window.axe.run(document, {
            runOnly: {
                type: "tag",
                values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"],
            },
        });
        return result.violations.map((violation) => ({
            id: violation.id,
            impact: violation.impact,
            targets: violation.nodes.flatMap((node) => node.target),
        }));
    });
}

async function layoutReport(page) {
    return page.evaluate(() => {
        const isVisible = (element) => {
            const style = getComputedStyle(element);
            const bounds = element.getBoundingClientRect();
            return (
                style.display !== "none"
                && style.visibility !== "hidden"
                && bounds.width > 0
                && bounds.height > 0
                && bounds.right > 0
                && bounds.left < document.documentElement.clientWidth
                && bounds.bottom > 0
                && bounds.top < document.documentElement.clientHeight
            );
        };
        const targetElements = [
            ...document.querySelectorAll(
                ".agent-access-grid button, .agent-access-grid input, "
                + ".agent-access-grid select, .agent-access-grid pre[tabindex]",
            ),
        ].filter(isVisible);
        const targets = targetElements.map((element) => {
            const target = element.matches('input[type="checkbox"]')
                ? element.closest("label")
                : element;
            const bounds = target.getBoundingClientRect();
            return {
                label: element.getAttribute("aria-label")
                    || element.labels?.[0]?.innerText
                    || element.innerText
                    || element.tagName,
                width: bounds.width,
                height: bounds.height,
            };
        });
        const boxes = [...document.querySelectorAll(
            ".agent-access-grid, .agent-access-grid > section, "
            + ".agent-access-grid article, .agent-access-grid form",
        )].map((element) => {
            const bounds = element.getBoundingClientRect();
            return {
                label: `${element.tagName.toLowerCase()}.${element.className}`,
                left: bounds.left,
                right: bounds.right,
                width: bounds.width,
                height: bounds.height,
            };
        });
        return {
            viewportWidth: document.documentElement.clientWidth,
            documentWidth: document.documentElement.scrollWidth,
            bodyWidth: document.body.scrollWidth,
            sidebarVisibility: getComputedStyle(
                document.querySelector(".workspace-sidebar"),
            ).visibility,
            targets,
            boxes,
        };
    });
}

async function assertKeyboardEntry(page) {
    await page.evaluate(() => {
        document.body.tabIndex = -1;
        document.body.focus();
        document.body.removeAttribute("tabindex");
    });
    await page.keyboard.press("Tab");
    const activeElement = await page.evaluate(() => ({
        className: document.activeElement?.className ?? "",
        tagName: document.activeElement?.tagName ?? "",
    }));
    assert(
        await page.locator(".skip-link").evaluate((element) => element === document.activeElement),
        "The first keyboard stop must be the skip link, not the closed off-screen drawer "
        + `(received ${activeElement.tagName}.${activeElement.className})`,
    );
    const focusStyle = await page.locator(".skip-link").evaluate((element) => {
        const style = getComputedStyle(element);
        return {
            outlineStyle: style.outlineStyle,
            outlineWidth: Number.parseFloat(style.outlineWidth),
        };
    });
    assert.notEqual(focusStyle.outlineStyle, "none");
    assert(focusStyle.outlineWidth >= 2);
    await page.keyboard.press("Enter");
    assert(
        await page.locator("#main-content").evaluate((element) => element === document.activeElement),
        "Activating the skip link must focus the main workspace",
    );
}

const server = await startServer();
const address = server.address();
assert(address && typeof address !== "string", "Agent Access server did not expose a port");
const baseUrl = `http://127.0.0.1:${address.port}/`;
const browser = await chromium.launch({ headless: true });

try {
    for (const [language, copy] of Object.entries(languages)) {
        for (const width of widths) {
            const diagnostics = await createPage(browser, baseUrl, language, width);
            try {
                assert.equal(await diagnostics.page.locator("html").getAttribute("lang"), language);
                assert(await diagnostics.page.getByLabel(copy.label).isEnabled());
                const report = await layoutReport(diagnostics.page);
                assert.equal(report.documentWidth, report.viewportWidth, `${language}/${width}: document overflow`);
                assert.equal(report.bodyWidth, report.viewportWidth, `${language}/${width}: body overflow`);
                for (const box of report.boxes) {
                    assert(box.width > 0 && box.height > 0, `${language}/${width}: hidden ${box.label}`);
                    assert(box.left >= -1, `${language}/${width}: ${box.label} crosses left edge`);
                    assert(
                        box.right <= report.viewportWidth + 1,
                        `${language}/${width}: ${box.label} crosses right edge`,
                    );
                }
                for (const target of report.targets) {
                    assert(
                        target.width >= 24 && target.height >= 24,
                        `${language}/${width}: target ${target.label} is ${target.width}x${target.height}`,
                    );
                }
                if (width < 992) {
                    assert.equal(
                        report.sidebarVisibility,
                        "hidden",
                        `${language}/${width}: closed drawer must leave no off-screen focus targets`,
                    );
                } else {
                    assert.equal(report.sidebarVisibility, "visible");
                }
                assert.deepEqual(await accessibilityViolations(diagnostics.page, baseUrl), []);
                await assertKeyboardEntry(diagnostics.page);
                assert.deepEqual(diagnostics.consoleProblems, []);
                assert.deepEqual(diagnostics.pageErrors, []);
            } finally {
                await diagnostics.context.close();
            }
        }
    }

    const forcedColors = await createPage(
        browser,
        baseUrl,
        "en",
        390,
        { forcedColors: "active" },
    );
    try {
        const { page } = forcedColors;
        await page.getByRole("button", { name: "Open menu" }).click();
        await page.locator(".workspace-sidebar.is-open").waitFor({ state: "visible" });
        const sidebarReport = await page.locator(".workspace-sidebar").evaluate((element) => {
            const style = getComputedStyle(element);
            return {
                borderStyle: style.borderStyle,
                borderWidth: Number.parseFloat(style.borderWidth),
                visibility: style.visibility,
            };
        });
        await page.getByRole("button", { name: "Close menu" }).click();
        const createGrant = page.getByRole("button", { name: "Create grant" });
        let reachedCreateGrant = false;
        for (let index = 0; index < 80; index += 1) {
            await page.keyboard.press("Tab");
            reachedCreateGrant = await createGrant.evaluate(
                (element) => element === document.activeElement,
            );
            if (reachedCreateGrant) break;
        }
        assert(reachedCreateGrant, "Keyboard traversal did not reach the primary grant CTA");
        const report = await page.evaluate(() => {
            const styleOf = (selector) => {
                const element = document.querySelector(selector);
                const style = getComputedStyle(element);
                return {
                    background: style.backgroundColor,
                    borderStyle: style.borderStyle,
                    borderWidth: Number.parseFloat(style.borderWidth),
                    color: style.color,
                    forcedColorAdjust: style.forcedColorAdjust,
                    outlineStyle: style.outlineStyle,
                    outlineWidth: Number.parseFloat(style.outlineWidth),
                    visibility: style.visibility,
                };
            };
            return {
                active: matchMedia("(forced-colors: active)").matches,
                body: styleOf("body"),
                input: styleOf(".agent-grant-form input"),
                cta: styleOf(".agent-grant-form .button--primary"),
                status: styleOf(".agent-state"),
                disclosure: styleOf(".agent-access-disclosure"),
            };
        });
        assert.equal(report.active, true);
        assert.notEqual(report.body.background, report.body.color);
        assert.equal(sidebarReport.visibility, "visible");
        assert.equal(sidebarReport.borderStyle, "solid");
        assert(sidebarReport.borderWidth >= 2);
        assert.equal(report.input.borderStyle, "solid");
        assert(report.input.borderWidth >= 2);
        assert.notEqual(report.input.background, report.input.color);
        assert.equal(report.cta.forcedColorAdjust, "none");
        assert.equal(report.cta.borderStyle, "solid");
        assert(report.cta.borderWidth >= 2);
        assert.notEqual(report.cta.background, report.cta.color);
        assert.notEqual(report.cta.outlineStyle, "none");
        assert(report.cta.outlineWidth >= 3);
        assert.equal(report.status.borderStyle, "solid");
        assert(report.status.borderWidth >= 2);
        assert.equal(report.disclosure.borderStyle, "solid");
        assert(report.disclosure.borderWidth >= 1);
        assert.deepEqual(await accessibilityViolations(page, baseUrl), []);
        assert.deepEqual(forcedColors.consoleProblems, []);
        assert.deepEqual(forcedColors.pageErrors, []);
    } finally {
        await forcedColors.context.close();
    }

    const interactive = await createPage(browser, baseUrl, "en", 390);
    try {
        const { page } = interactive;
        await page.getByRole("button", { name: "Revoke access" }).click();
        const revokePassword = page.getByLabel(
            "Enter your current password to revoke this grant",
        );
        await revokePassword.fill("incorrect-password");
        await page.getByRole("button", { name: "Confirm revocation" }).click();
        await page.getByRole("alert").filter({
            hasText: "That password did not match this local CareerOS account.",
        }).waitFor();
        assert.equal(await revokePassword.inputValue(), "");
        await revokePassword.fill("CurrentPassword1");
        await page.getByRole("button", { name: "Confirm revocation" }).click();
        await page.getByText("Revoked", { exact: true }).waitFor();
        await page.getByRole("status").filter({
            hasText: "Access for Existing quality grant was revoked.",
        }).waitFor();

        await page.getByLabel("Client label").fill("Playwright quality client");
        const issuePassword = page.getByLabel("Current CareerOS password");
        await issuePassword.fill("incorrect-password");
        await page.getByRole("button", { name: "Create grant" }).click();
        await page.getByRole("alert").filter({
            hasText: "That password did not match this local CareerOS account.",
        }).waitFor();
        assert.equal(await issuePassword.inputValue(), "");
        assert.equal(
            await page.evaluate(() => window.__careerosClipboardWrites.length),
            0,
            "Creation must never copy the bearer automatically",
        );
        assert.deepEqual(interactive.consoleProblems, [
            "Failed to load resource: the server responded with a status of 403 (Forbidden)",
            "Failed to load resource: the server responded with a status of 403 (Forbidden)",
        ]);
        interactive.consoleProblems.length = 0;

        await issuePassword.fill("CurrentPassword1");
        await page.getByRole("button", { name: "Create grant" }).click();
        const tokenHeading = page.getByRole("heading", { name: "Save this token now" });
        await tokenHeading.waitFor();
        assert(await tokenHeading.evaluate((element) => element === document.activeElement));
        assert.equal(await page.getByLabel("New agent token").inputValue(), secretToken);
        assert.equal(await issuePassword.inputValue(), "");
        assert.equal(await page.evaluate(() => window.__careerosClipboardWrites.length), 0);
        const storageBeforeExit = await page.evaluate((token) => ({
            local: Object.entries(localStorage),
            session: Object.entries(sessionStorage),
            html: document.documentElement.outerHTML,
            values: [...document.querySelectorAll("input, textarea")].map((element) => element.value),
            containsTokenInText: document.body.innerText.includes(token),
        }), secretToken);
        assert.equal(storageBeforeExit.containsTokenInText, false);
        assert(!JSON.stringify(storageBeforeExit.local).includes(secretToken));
        assert(!JSON.stringify(storageBeforeExit.session).includes(secretToken));
        assert(storageBeforeExit.values.includes(secretToken));
        assert.deepEqual(await accessibilityViolations(page, baseUrl), []);

        await page.getByRole("button", { name: "Copy token" }).click();
        assert.deepEqual(
            await page.evaluate(() => window.__careerosClipboardWrites),
            [secretToken],
        );

        await page.getByRole("button", { name: "Open menu" }).click();
        await page.locator(".workspace-sidebar.is-open").waitFor({ state: "visible" });
        assert.equal(
            await page.locator(".workspace-sidebar").evaluate(
                (element) => getComputedStyle(element).visibility,
            ),
            "visible",
        );
        await page.getByRole("link", { name: "Career Vault" }).click();
        await page.waitForURL("**/profile");
        await page.getByRole("heading", { name: "Career Vault", level: 1 }).waitFor();
        const afterExit = await page.evaluate((token) => ({
            body: document.body.innerText,
            html: document.documentElement.outerHTML,
            local: Object.entries(localStorage),
            session: Object.entries(sessionStorage),
            values: [...document.querySelectorAll("input, textarea")].map((element) => element.value),
            clipboardWrites: window.__careerosClipboardWrites.length,
            containsToken: (
                document.body.innerText.includes(token)
                || document.documentElement.outerHTML.includes(token)
                || [...document.querySelectorAll("input, textarea")]
                    .some((element) => element.value.includes(token))
                || JSON.stringify(Object.entries(localStorage)).includes(token)
                || JSON.stringify(Object.entries(sessionStorage)).includes(token)
            ),
        }), secretToken);
        assert.equal(afterExit.containsToken, false);
        assert.equal(afterExit.clipboardWrites, 1, "Only the explicit clipboard write is retained");
        assert(!interactive.consoleProblems.join("\n").includes(secretToken));
        assert(!interactive.pageErrors.join("\n").includes(secretToken));
        assert.deepEqual(interactive.consoleProblems, []);
        assert.deepEqual(interactive.pageErrors, []);
    } finally {
        await interactive.context.close();
    }

    console.log(
        "Agent Access WCAG 2.2 AA, keyboard, lifecycle and secret-erasure validation "
        + `passed for EN/IT at ${widths.join(", ")}px.`,
    );
} finally {
    await browser.close();
    await closeServer(server);
}
