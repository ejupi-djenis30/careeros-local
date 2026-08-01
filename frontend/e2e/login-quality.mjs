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
const contentTypes = new Map([
    [".css", "text/css; charset=utf-8"],
    [".html", "text/html; charset=utf-8"],
    [".js", "text/javascript; charset=utf-8"],
    [".json", "application/json; charset=utf-8"],
    [".svg", "image/svg+xml"],
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
        const pathname = new URL(request.url ?? "/", "http://127.0.0.1").pathname;
        const path = pathname === "/__axe.js" ? axePath : distributionPath(request.url);
        if (!path) {
            response.writeHead(403).end("Forbidden");
            return;
        }
        try {
            const metadata = await stat(path);
            if (!metadata.isFile()) throw new Error("Not a file");
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

async function createLoginPage(browser, baseUrl, language, contextOverrides = {}) {
    const context = await browser.newContext({
        colorScheme: "dark",
        reducedMotion: "reduce",
        viewport: { width: 390, height: 844 },
        ...contextOverrides,
    });
    await context.addInitScript((savedLanguage) => {
        window.localStorage.setItem("careeros.interface-language", savedLanguage);
    }, language);
    const page = await context.newPage();
    const consoleProblems = [];
    const pageErrors = [];
    page.on("console", (message) => {
        if (["error", "warning"].includes(message.type())) consoleProblems.push(message.text());
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
    }));
    await page.goto(baseUrl, { waitUntil: "networkidle" });
    return { context, page, consoleProblems, pageErrors };
}

async function createWorkspacePage(browser, baseUrl, viewport) {
    const context = await browser.newContext({
        colorScheme: "dark",
        reducedMotion: "no-preference",
        viewport,
    });
    await context.addInitScript(() => {
        window.localStorage.setItem("careeros.interface-language", "en");
    });
    const page = await context.newPage();
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.route("**/api/v1/**", (route) => {
        const pathname = new URL(route.request().url()).pathname;
        if (pathname === "/api/v1/auth/refresh") {
            return route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({
                    access_token: "workspace-access-token",
                    token_type: "bearer",
                    username: "local-user",
                }),
            });
        }
        return route.fulfill({
            status: 503,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Local fixture unavailable" }),
        });
    });
    await page.goto(baseUrl, { waitUntil: "networkidle" });
    return { context, page, pageErrors };
}

async function accessibilityViolations(page, baseUrl) {
    if (!(await page.evaluate(() => Boolean(window.axe)))) {
        await page.addScriptTag({ url: `${baseUrl}__axe.js` });
    }
    return page.evaluate(async () => {
        const result = await window.axe.run(document, {
            runOnly: {
                type: "tag",
                values: ["wcag2a", "wcag2aa", "wcag21aa"],
            },
        });
        return result.violations.map((violation) => ({
            id: violation.id,
            impact: violation.impact,
            targets: violation.nodes.flatMap((node) => node.target),
        }));
    });
}

async function visualMetrics(page) {
    return page.evaluate(() => {
        const parseColor = (value) => {
            const parts = value.match(/[\d.]+/g)?.map(Number) ?? [];
            return {
                r: parts[0] ?? 0,
                g: parts[1] ?? 0,
                b: parts[2] ?? 0,
                a: parts[3] ?? 1,
            };
        };
        const composite = (foreground, background) => {
            const alpha = foreground.a + background.a * (1 - foreground.a);
            if (alpha === 0) return { r: 0, g: 0, b: 0, a: 0 };
            return {
                r: (foreground.r * foreground.a
                    + background.r * background.a * (1 - foreground.a)) / alpha,
                g: (foreground.g * foreground.a
                    + background.g * background.a * (1 - foreground.a)) / alpha,
                b: (foreground.b * foreground.a
                    + background.b * background.a * (1 - foreground.a)) / alpha,
                a: alpha,
            };
        };
        const background = (element) => {
            const chain = [];
            for (let node = element; node; node = node.parentElement) chain.unshift(node);
            return chain.reduce(
                (result, node) => composite(parseColor(getComputedStyle(node).backgroundColor), result),
                { r: 255, g: 255, b: 255, a: 1 },
            );
        };
        const luminance = ({ r, g, b }) => {
            const channel = (value) => {
                const normalized = value / 255;
                return normalized <= 0.04045
                    ? normalized / 12.92
                    : ((normalized + 0.055) / 1.055) ** 2.4;
            };
            return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
        };
        const contrast = (element) => {
            const foregroundLuminance = luminance(parseColor(getComputedStyle(element).color));
            const backgroundLuminance = luminance(background(element));
            return (Math.max(foregroundLuminance, backgroundLuminance) + 0.05)
                / (Math.min(foregroundLuminance, backgroundLuminance) + 0.05);
        };
        const italian = document.querySelector('[aria-label="Italian"]');
        const privacy = document.querySelector(".login-privacy > span");
        const icon = document.querySelector(".login-lock .bi-lock");
        const iconStyle = getComputedStyle(icon, "::before");
        const languageBounds = [...document.querySelectorAll(".language-switcher button")]
            .map((button) => {
                const bounds = button.getBoundingClientRect();
                return { width: bounds.width, height: bounds.height };
            });
        return {
            italianContrast: contrast(italian),
            privacyContrast: contrast(privacy),
            iconMask: iconStyle.webkitMaskImage || iconStyle.maskImage,
            iconWidth: Number.parseFloat(iconStyle.width),
            iconHeight: Number.parseFloat(iconStyle.height),
            languageBounds,
        };
    });
}

async function waitForHeading(page, name, diagnostics) {
    try {
        await page.getByRole("heading", { name }).waitFor({ timeout: 10_000 });
    } catch (error) {
        const body = (await page.locator("body").innerText()).slice(0, 1_000);
        throw new Error([
            error.message,
            `Body: ${body}`,
            `Console: ${diagnostics.consoleProblems.join(" | ") || "none"}`,
            `Page errors: ${diagnostics.pageErrors.join(" | ") || "none"}`,
        ].join("\n"));
    }
}

const server = await startServer();
const address = server.address();
assert(address && typeof address !== "string", "Static login server did not expose a port");
const baseUrl = `http://127.0.0.1:${address.port}/`;
const browser = await chromium.launch({ headless: true });

try {
    const english = await createLoginPage(browser, baseUrl, "en");
    try {
        await waitForHeading(english.page, "Welcome back", english);
        assert.equal(await english.page.locator("html").getAttribute("lang"), "en");
        assert.equal(await english.page.getByLabel("Username").getAttribute("name"), "username");
        assert.equal(await english.page.getByLabel("Password").getAttribute("name"), "password");
        const initialResources = await english.page.evaluate(() =>
            performance.getEntriesByType("resource").map((entry) => new URL(entry.name).pathname));
        assert.deepEqual(
            initialResources.filter((path) => /\/assets\/(en|it)-.+\.js$/.test(path))
                .map((path) => path.match(/\/assets\/(en|it)-/)[1]),
            ["en"],
            "English login must load only the English catalogue",
        );
        assert.equal(
            initialResources.filter((path) => /\.woff2?$/.test(path)).length,
            0,
            "Login must not fetch the full icon font",
        );

        const metrics = await visualMetrics(english.page);
        assert(metrics.italianContrast >= 4.5, `Italian control contrast is ${metrics.italianContrast}`);
        assert(metrics.privacyContrast >= 4.5, `Privacy copy contrast is ${metrics.privacyContrast}`);
        assert.match(metrics.iconMask, /^url\(/, "Subset icon must render through an SVG mask");
        assert(metrics.iconWidth > 0 && metrics.iconHeight > 0, "Subset icon must have visible geometry");
        for (const bounds of metrics.languageBounds) {
            assert(bounds.width >= 44, `Language target width is ${bounds.width}px`);
            assert(bounds.height >= 44, `Language target height is ${bounds.height}px`);
        }
        console.log(
            `Login contrast: language ${metrics.italianContrast.toFixed(2)}:1; `
            + `privacy ${metrics.privacyContrast.toFixed(2)}:1.`,
        );

        const submit = english.page.getByRole("button", { name: "Open workspace" });
        assert(await submit.isDisabled(), "Empty login form must keep submit disabled");
        assert(Number(await submit.evaluate((button) => getComputedStyle(button).opacity)) <= 0.5);
        await english.page.keyboard.press("Shift+Tab");
        const focusedLanguage = english.page.getByRole("button", { name: "Italian" });
        assert(await focusedLanguage.evaluate((button) => button === document.activeElement));
        const focusOutline = await focusedLanguage.evaluate((button) => {
            const style = getComputedStyle(button);
            return { style: style.outlineStyle, width: Number.parseFloat(style.outlineWidth) };
        });
        assert.notEqual(focusOutline.style, "none");
        assert(focusOutline.width >= 3);

        await english.page.getByLabel("Username").fill("local-user");
        assert(await submit.isDisabled(), "Password is still required");
        await english.page.getByLabel("Password").fill("Password1");
        assert(!(await submit.isDisabled()), "Complete local credentials must enable submit");

        assert.deepEqual(await accessibilityViolations(english.page, baseUrl), []);
        await english.page.getByRole("button", { name: "Italian" }).click();
        await english.page.getByRole("heading", { name: "Bentornato" }).waitFor();
        assert.equal(await english.page.locator("html").getAttribute("lang"), "it");
        assert.deepEqual(await accessibilityViolations(english.page, baseUrl), []);
        assert.deepEqual(english.consoleProblems, []);
        assert.deepEqual(english.pageErrors, []);
    } finally {
        await english.context.close();
    }

    const italian = await createLoginPage(browser, baseUrl, "it");
    try {
        await waitForHeading(italian.page, "Bentornato", italian);
        assert.equal(await italian.page.locator("html").getAttribute("lang"), "it");
        const initialResources = await italian.page.evaluate(() =>
            performance.getEntriesByType("resource").map((entry) => new URL(entry.name).pathname));
        assert.deepEqual(
            initialResources.filter((path) => /\/assets\/(en|it)-.+\.js$/.test(path))
                .map((path) => path.match(/\/assets\/(en|it)-/)[1]),
            ["it"],
            "Persisted Italian login must load only the Italian catalogue",
        );
        assert.deepEqual(await accessibilityViolations(italian.page, baseUrl), []);
        assert.deepEqual(italian.consoleProblems, []);
        assert.deepEqual(italian.pageErrors, []);
    } finally {
        await italian.context.close();
    }

    const recovery = await createLoginPage(browser, baseUrl, "en");
    try {
        const apiRequests = [];
        recovery.page.on("request", (request) => {
            const pathname = new URL(request.url()).pathname;
            if (pathname.startsWith("/api/v1/")) apiRequests.push(pathname);
        });
        await recovery.page.route("**/api/v1/auth/login", (route) => route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                access_token: "maintenance-token",
                token_type: "bearer",
                username: "local-user",
                session_state: "restore_pending",
            }),
        }));
        await recovery.page.route("**/api/v1/portability/restore", (route) => route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ restored_files: 1, restored_records: { profiles: 1 } }),
        }));
        await recovery.page.route("**/api/v1/auth/logout", async (route) => {
            assert.equal(
                route.request().headers().authorization,
                "Bearer maintenance-token",
                "Terminal recovery must preserve the maintenance bearer only for backend logout",
            );
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({}),
            });
        });

        await recovery.page.getByLabel("Username").fill("local-user");
        await recovery.page.getByLabel("Password").fill("Password1");
        await recovery.page.getByRole("button", { name: "Open workspace" }).click();
        await recovery.page.getByRole("heading", { name: "Restore is incomplete" }).waitFor();

        assert.equal(await recovery.page.locator(".workspace-layout").count(), 0);
        assert.equal(await recovery.page.locator("#main-content").count(), 0);
        assert.equal(await recovery.page.getByText("Your career workspace").count(), 0);
        const recoveryArchiveInput = recovery.page.getByLabel(
            "Same CareerOS backup ZIP used for the pending restore",
        );
        assert.equal(
            await recoveryArchiveInput.getAttribute("tabindex"),
            "-1",
            "The proxy file input must not create an invisible keyboard stop",
        );
        const recoveryPrimary = recovery.page.getByRole("button", {
            name: "Choose the same backup ZIP",
        });
        await recoveryPrimary.focus();
        await recovery.page.keyboard.press("Tab");
        assert(
            await recovery.page.locator("#recovery-erase-phrase").evaluate(
                (input) => input === document.activeElement,
            ),
            "Keyboard focus must move from the file-picker control to the visible erasure field",
        );
        for (const width of [320, 390, 768]) {
            await recovery.page.setViewportSize({ width, height: 844 });
            const geometry = await recovery.page.evaluate(() => {
                const panel = document.querySelector(".recovery-panel").getBoundingClientRect();
                const targets = [...document.querySelectorAll(
                    ".recovery-panel button:not([disabled]), .recovery-panel input:not([type='file'])",
                )].map((element) => {
                    const bounds = element.getBoundingClientRect();
                    return { height: bounds.height, width: bounds.width };
                });
                const offenders = [...document.querySelectorAll(".recovery-panel *")]
                    .map((element) => {
                        const bounds = element.getBoundingClientRect();
                        return {
                            element: `${element.tagName.toLowerCase()}.${element.className || ""}`,
                            left: bounds.left,
                            right: bounds.right,
                            scrollWidth: element.scrollWidth,
                            text: (element.textContent || "").trim().slice(0, 60),
                        };
                    })
                    .filter((item) => item.left < -1 || item.right > document.documentElement.clientWidth + 1);
                return {
                    clientWidth: document.documentElement.clientWidth,
                    scrollWidth: document.documentElement.scrollWidth,
                    panelLeft: panel.left,
                    panelRight: panel.right,
                    targets,
                    offenders,
                };
            });
            assert.equal(
                geometry.scrollWidth,
                geometry.clientWidth,
                `${width}px recovery must not overflow horizontally: ${JSON.stringify(geometry.offenders)}`,
            );
            assert(
                geometry.panelLeft >= -1 && geometry.panelRight <= geometry.clientWidth + 1,
                `${width}px recovery panel must remain inside the viewport`,
            );
            for (const target of geometry.targets) {
                assert(
                    target.height >= 43,
                    `${width}px recovery target height is only ${target.height}px`,
                );
            }
        }
        await recovery.page.setViewportSize({ width: 390, height: 844 });
        assert.deepEqual(await accessibilityViolations(recovery.page, baseUrl), []);
        const recoveryResources = await recovery.page.evaluate(() =>
            performance.getEntriesByType("resource").map((entry) => new URL(entry.name).pathname));
        assert.equal(
            recoveryResources.some((path) => /AuthenticatedWorkspace-.*\.js$/.test(path)),
            false,
            "Pending login must not fetch the private workspace chunk",
        );

        await recoveryArchiveInput.setInputFiles({
            name: "private-career-history.zip",
            mimeType: "application/zip",
            buffer: Buffer.from("PK recovery fixture"),
        });

        await recovery.page.getByRole("heading", { name: "Welcome back" }).waitFor();
        await recovery.page.getByText(
            "Local data recovery completed. Sign in again to continue.",
        ).waitFor();
        assert.equal(await recovery.page.locator(".workspace-layout").count(), 0);
        assert.equal(await recovery.page.locator("#main-content").count(), 0);
        assert.equal(await recovery.page.getByText("private-career-history.zip").count(), 0);
        assert.deepEqual(apiRequests, [
            "/api/v1/auth/login",
            "/api/v1/portability/restore",
            "/api/v1/auth/logout",
        ]);
        assert.deepEqual(recovery.consoleProblems, []);
        assert.deepEqual(recovery.pageErrors, []);
    } finally {
        await recovery.context.close();
    }

    const workspace = await createWorkspacePage(
        browser,
        baseUrl,
        { width: 390, height: 844 },
    );
    try {
        await workspace.page.getByRole("heading", {
            name: "Your career workspace",
            level: 1,
        }).waitFor();
        const productionIntroWidths = [];
        for (const width of [320, 390, 768, 1280]) {
            await workspace.page.setViewportSize({ width, height: 844 });
            await workspace.page.evaluate(() => new Promise((resolveFrame) =>
                requestAnimationFrame(() => requestAnimationFrame(resolveFrame))));
            const geometry = await workspace.page.evaluate(() => {
                const bounds = (selector) => {
                    const rect = document.querySelector(selector).getBoundingClientRect();
                    return {
                        bottom: rect.bottom,
                        left: rect.left,
                        right: rect.right,
                        top: rect.top,
                        width: rect.width,
                    };
                };
                return {
                    clientWidth: document.documentElement.clientWidth,
                    scrollWidth: document.documentElement.scrollWidth,
                    header: bounds(".workspace-header"),
                    menu: bounds(".workspace-menu"),
                    brand: bounds(".workspace-header__brand"),
                    context: bounds(".workspace-header__context"),
                    heading: bounds(".workspace-header__context h1"),
                };
            });
            assert(
                geometry.header.left >= -1
                && geometry.header.right <= geometry.clientWidth + 1,
                `${width}px production header must stay inside the viewport`,
            );
            assert(
                geometry.heading.width >= geometry.context.width - 1,
                `${width}px production heading must fill its intro column`,
            );
            productionIntroWidths.push({
                viewport: width,
                layout: geometry.clientWidth,
                intro: geometry.context.width,
            });
            if (width < 992) {
                assert(
                    geometry.context.width >= geometry.clientWidth - 64,
                    `${width}px production intro is only ${geometry.context.width}px`,
                );
                assert(
                    geometry.context.top >= Math.max(
                        geometry.menu.bottom,
                        geometry.brand.bottom,
                    ) - 1,
                    `${width}px production intro must sit below menu and brand`,
                );
            } else {
                assert(
                    geometry.context.width >= (geometry.clientWidth - 272) * 0.55,
                    `${width}px production intro lost its desktop reading width`,
                );
            }
        }
        await workspace.page.setViewportSize({ width: 390, height: 844 });
        const viewportCapture = await workspace.page.screenshot({ fullPage: false });
        assert(viewportCapture.length > 1_000, "Standard viewport screenshot must be non-empty");

        const menu = workspace.page.getByRole("button", { name: "Open menu" });
        await menu.click();
        await workspace.page.waitForTimeout(250);
        const closeMenu = workspace.page.getByRole("button", { name: "Close menu" });
        assert(await closeMenu.evaluate((button) => button === document.activeElement));
        assert.equal(await workspace.page.locator(".workspace-main[inert]").count(), 1);
        assert.equal(await workspace.page.locator(".skip-link[inert]").count(), 1);
        await workspace.page.keyboard.press("Escape");
        await workspace.page.waitForFunction(() => document.activeElement?.matches(".workspace-menu"));
        assert(await menu.evaluate((button) => button === document.activeElement));
        assert.deepEqual(workspace.pageErrors, []);
        console.log(`Production workspace intro widths: ${JSON.stringify(productionIntroWidths)}.`);
    } finally {
        await workspace.context.close();
    }

    const forcedColors = await createLoginPage(
        browser,
        baseUrl,
        "en",
        { forcedColors: "active" },
    );
    try {
        await waitForHeading(forcedColors.page, "Welcome back", forcedColors);
        await forcedColors.page.getByLabel("Username").fill("local-user");
        await forcedColors.page.getByLabel("Password").fill("Password1");
        const forcedSubmit = forcedColors.page.getByRole("button", { name: "Open workspace" });
        await forcedSubmit.focus();
        const report = await forcedColors.page.evaluate(() => {
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
                };
            };
            return {
                active: matchMedia("(forced-colors: active)").matches,
                body: styleOf("body"),
                input: styleOf('input[autocomplete="username"]'),
                lock: styleOf(".login-lock"),
                submit: styleOf(".login-panel form .button--primary"),
            };
        });
        assert.equal(report.active, true);
        assert.notEqual(report.body.background, "rgba(0, 0, 0, 0)");
        assert.notEqual(report.body.background, report.body.color);
        assert.equal(report.input.borderStyle, "solid");
        assert(report.input.borderWidth >= 2);
        assert.notEqual(report.input.background, report.input.color);
        assert.equal(report.submit.forcedColorAdjust, "none");
        assert.equal(report.submit.borderStyle, "solid");
        assert(report.submit.borderWidth >= 2);
        assert.notEqual(report.submit.background, report.submit.color);
        assert.equal(report.lock.borderStyle, "solid");
        assert(report.lock.borderWidth >= 1);
        assert.notEqual(report.submit.outlineStyle, "none");
        assert(report.submit.outlineWidth >= 3);
        assert.deepEqual(await accessibilityViolations(forcedColors.page, baseUrl), []);
        assert.deepEqual(forcedColors.consoleProblems, []);
        assert.deepEqual(forcedColors.pageErrors, []);
    } finally {
        await forcedColors.context.close();
    }

    for (const width of [1280, 1440]) {
        const desktop = await createLoginPage(
            browser,
            baseUrl,
            "en",
            { viewport: { width, height: 720 } },
        );
        try {
            await waitForHeading(desktop.page, "Welcome back", desktop);
            const geometry = await desktop.page.evaluate(() => {
                const panel = document.querySelector(".login-panel").getBoundingClientRect();
                return {
                    clientWidth: document.documentElement.clientWidth,
                    scrollWidth: document.documentElement.scrollWidth,
                    panelLeft: panel.left,
                    panelRight: panel.right,
                };
            });
            assert(
                geometry.scrollWidth <= geometry.clientWidth,
                `${width}px login overflows horizontally: ${JSON.stringify(geometry)}`,
            );
            assert(
                geometry.panelLeft >= 0 && geometry.panelRight <= geometry.clientWidth,
                `${width}px login panel escapes the viewport: ${JSON.stringify(geometry)}`,
            );
            assert.deepEqual(desktop.consoleProblems, []);
            assert.deepEqual(desktop.pageErrors, []);
        } finally {
            await desktop.context.close();
        }
    }

    console.log(
        "Login quality validation passed at 390px, 1280px, and 1440px.",
    );
} finally {
    await browser.close();
    await closeServer(server);
}
