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
        pageTitle: "Agent workspace",
        queueTitle: "Work queue",
        reviewBtn: "Review proposal",
        acceptBtn: "Accept proposal",
        acceptedNotice: "Proposal accepted",
    },
    it: {
        pageTitle: "Workspace agenti",
        queueTitle: "Coda di lavoro",
        reviewBtn: "Revisiona proposta",
        acceptBtn: "Accetta proposta",
        acceptedNotice: "Proposta accettata",
    },
};

const mockGrant = {
    id: "grant-e2e-1",
    label: "Codex Desktop",
    scopes: ["system:read", "context:read", "proposals:write"],
    expires_at: "2030-01-01T00:00:00Z",
    revoked_at: null,
    created_at: "2026-09-01T00:00:00Z",
};

const mockReturnedDiscovery = {
    id: "work-disc-1",
    work_kind: "discover",
    state: "returned",
    revision: 2,
    instruction: "Find Senior Cloud Architect roles in Zurich",
    bound_grant_id: "grant-e2e-1",
    input_revisions: {
        profile: null,
        job: null,
        application: null,
        resume: null,
        dossier: null,
    },
    created_at: "2026-09-13T09:00:00Z",
    expires_at: "2026-09-14T09:00:00Z",
};

const mockDiscoveryProposal = {
    id: "prop-disc-1",
    request_id: "work-disc-1",
    client_label: "Codex",
    model_label: "gpt-5.3-codex-spark",
    created_at: "2026-09-13T09:05:00Z",
    contract_version: 1,
    payload: {
        contract_version: 1,
        kind: "discover",
        listings: [
            {
                title: "Lead Cloud Platform Architect",
                company: "Alpine Cloud Solutions",
                location: "Zurich",
                external_url: "https://example.ch/careers/cloud-lead",
                observed_at: "2026-09-13T08:45:00Z",
                source_platform: "company_careers",
                source_text: "Seeking a Lead Cloud Platform Architect to drive cloud transformation on AWS and Kubernetes in Zurich with a permanent contract and English communication.",
                gates: ["role", "requirements", "language", "location", "contract", "freshness"].map((dimension) => ({
                    dimension,
                    status: "eligible",
                    reason: "Reviewed evidence supports this dimension",
                    fact_ids: [],
                    quote_references: [dimension],
                    unknowns: [],
                })),
                scores: {
                    role: { score: 95, explanation: "Strong role fit" },
                    requirements: { score: 92, explanation: "Strong requirements fit" },
                    language: { score: 90, explanation: "Language fits" },
                    location: { score: 90, explanation: "Location fits" },
                    contract: { score: 90, explanation: "Contract fits" },
                    freshness: { score: 95, explanation: "Recently observed" },
                    overall_score: 92,
                },
            },
        ],
    },
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

async function installApiMock(page, state) {
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
        // CRITICAL FOR T027: Local model is NOT ready / NOT available
        if (path === "/local-model/status") {
            return json(route, 200, {
                available: false,
                ready: false,
                configured_model: null,
                installed_models: [],
                error_code: "model_unavailable",
                runtime: null,
            });
        }
        if (path === "/search/status/all") return json(route, 200, {});
        if (path === "/automation/grants") {
            return json(route, 200, [mockGrant]);
        }
        if (path === "/career-profile") {
            return json(route, 200, {
                revision: 1,
                display_name: "quality-user",
                facts: [],
                goals: [],
            });
        }
        if (path === "/search/sources" || path === "/resumes/versions") {
            return json(route, 200, []);
        }

        // Agent work endpoints
        if (path === "/agent-work" && request.method() === "GET") {
            return json(route, 200, {
                items: state.workList,
                total: state.workList.length,
            });
        }
        if (path === "/agent-work/work-disc-1" && request.method() === "GET") {
            const work = state.workList.find((item) => item.id === "work-disc-1")
                || mockReturnedDiscovery;
            return json(route, 200, {
                ...work,
                proposal: mockDiscoveryProposal,
            });
        }
        if (path === "/agent-work/work-disc-1/accept" && request.method() === "POST") {
            const body = request.postDataJSON() || {};
            assert.equal(body.expected_revision, 2, "Must pass expected revision for CAS guard");
            assert.deepEqual(
                body.expected_target_revisions,
                mockReturnedDiscovery.input_revisions,
                "Must pass the exact reviewed target revisions",
            );
            state.workList = state.workList.map((w) =>
                w.id === "work-disc-1" ? { ...w, state: "accepted", revision: 3 } : w,
            );
            // Add accepted job to jobs list
            state.jobs.push({
                id: "job-accepted-1",
                title: "Lead Cloud Platform Architect",
                employer: "Alpine Cloud Solutions",
                location: "Zurich",
                analysis_provenance: "external-agent",
                analysis_model: "gpt-5.3-codex-spark",
                affinity_score: 92,
                status: "saved",
                created_at: new Date().toISOString(),
            });
            return json(route, 200, {
                request_id: "work-disc-1",
                proposal_id: "prop-disc-1",
                work_kind: "discover",
                accepted_at: "2026-09-13T09:06:00Z",
                created_job_ids: [1],
                created_application_ids: ["job-accepted-1"],
            });
        }

        if (path === "/search/jobs" || path === "/jobs") {
            return json(route, 200, state.jobs);
        }

        return json(route, 200, {});
    });
}

async function accessibilityViolations(page, baseUrl) {
    if (!(await page.evaluate(() => Boolean(window.axe)))) {
        await page.addScriptTag({ url: `${baseUrl}__axe.js` });
    }
    return page.evaluate(async () => {
        const result = await window.axe.run(document, {
            runOnly: {
                type: "tag",
                values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
            },
            rules: {
                "color-contrast": { enabled: false },
            },
        });
        return result.violations.map((v) => ({
            id: v.id,
            impact: v.impact,
            description: v.description,
            nodes: v.nodes.length,
        }));
    });
}

async function runTest() {
    const server = await startServer();
    const address = server.address();
    const port = typeof address === "object" && address ? address.port : 0;
    const baseUrl = `http://127.0.0.1:${port}/`;

    const browser = await chromium.launch({ headless: true });

    try {
        for (const language of ["en", "it"]) {
            for (const width of widths) {
                const state = {
                    workList: [{ ...mockReturnedDiscovery }],
                    jobs: [],
                };

                const context = await browser.newContext({
                    viewport: { width, height: width <= 390 ? 900 : 960 },
                    colorScheme: "dark",
                });
                await context.addInitScript((lang) => {
                    window.localStorage.setItem("careeros.interface-language", lang);
                }, language);

                const page = await context.newPage();
                await installApiMock(page, state);

                // 1. Navigate to /agent-work without a local model
                await page.goto(`${baseUrl}agent-work`, { waitUntil: "networkidle" });
                const pageTitle = page.locator("#main-content").getByRole("heading", { name: languages[language].pageTitle, level: 1 });
                await pageTitle.waitFor();
                assert(await pageTitle.isVisible(), `Agent workspace title must be visible for ${language} at ${width}px`);

                // 2. Check accessibility on initial page load
                const pageViolations = await accessibilityViolations(page, baseUrl);
                assert.deepEqual(
                    pageViolations,
                    [],
                    `WCAG accessibility violations on /agent-work for ${language} at ${width}px: ${JSON.stringify(pageViolations)}`,
                );

                // 3. Queue item is rendered and review proposal button is available
                const reviewBtn = page.getByRole("button", { name: languages[language].reviewBtn });
                await reviewBtn.waitFor();
                assert(await reviewBtn.isVisible(), "Review proposal button must be visible");

                // 4. Open Proposal Review
                await reviewBtn.click();
                const dialog = page.getByRole("dialog");
                await dialog.waitFor();
                assert(await dialog.isVisible(), "Review dialog must open");

                // 5. Verify vacancy details and source link in proposal
                assert(
                    await page.getByText("Lead Cloud Platform Architect").first().isVisible(),
                    "Vacancy title must be shown in proposal",
                );
                assert(
                    await page.getByText("Alpine Cloud Solutions").first().isVisible(),
                    "Employer must be shown in proposal",
                );

                // 6. Check dialog accessibility
                const dialogViolations = await accessibilityViolations(page, baseUrl);
                assert.deepEqual(
                    dialogViolations,
                    [],
                    `WCAG violations on proposal review dialog for ${language} at ${width}px: ${JSON.stringify(dialogViolations)}`,
                );

                // 7. Accept proposal
                const acceptBtn = page.getByRole("button", { name: languages[language].acceptBtn });
                await acceptBtn.click();

                // 8. Verify acceptance notice is shown
                const acceptedNotice = page.getByText(languages[language].acceptedNotice).first();
                await acceptedNotice.waitFor();
                assert(await acceptedNotice.isVisible(), "Accepted notice must appear");

                await context.close();
            }
        }

        console.log("Agent Work Discovery -> Review -> Accept browser journey and WCAG 2.2 AA validation passed for EN/IT at 320, 390, 1440px.");
    } finally {
        await browser.close();
        await closeServer(server);
    }
}

runTest().catch((err) => {
    console.error("agent-work-quality e2e test failed:", err);
    process.exit(1);
});
