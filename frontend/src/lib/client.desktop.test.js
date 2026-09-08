import { afterEach, describe, expect, it, vi } from "vitest";

import {
    ApiClient,
    configureApiRuntime,
    getApiBase,
    resetApiRuntime,
    validateApiBase,
} from "./client";

describe("desktop API runtime", () => {
    afterEach(() => {
        resetApiRuntime();
        vi.restoreAllMocks();
    });

    it("accepts only loopback runtime URLs and adds the per-launch session header", async () => {
        configureApiRuntime({
            apiBaseUrl: "http://127.0.0.1:43127/api/v1",
            sessionToken: "desktop-" + "x".repeat(43),
        });
        const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
            new Response(JSON.stringify({ status: "ready" }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            }),
        );

        await ApiClient.get("/health/ready");

        expect(fetchMock).toHaveBeenCalledWith(
            "http://127.0.0.1:43127/api/v1/health/ready",
            expect.objectContaining({
                redirect: "error",
                headers: expect.objectContaining({ "X-CareerOS-Session": "desktop-" + "x".repeat(43) }),
            }),
        );
    });

    it("rejects a non-loopback desktop service", () => {
        expect(() => configureApiRuntime({
            apiBaseUrl: "https://example.com/api/v1",
            sessionToken: "desktop-" + "x".repeat(43),
        })).toThrow(/loopback/i);
    });

    it.each([
        "",
        "jobs/",
        "//example.test/jobs",
        "https://example.test/jobs",
        "/../private",
        "/jobs/../../auth/logout",
        "/jobs/./entry",
        "/%2e%2e/private",
        "/jobs/.%2E/private",
        "/jobs/%2Fprivate",
        "/jobs/%5cprivate",
        "/jobs/\\private",
        "/jobs/#private",
        "/jobs/%ZZ",
        "/jobs/%00private",
        "/jobs/\nprivate",
        "/jobs/ private",
        null,
    ].flatMap((endpoint) => [[false, endpoint], [true, endpoint]]))(
        "rejects non-canonical request paths before attaching credentials (desktop=%s, path=%s)",
        async (desktop, endpoint) => {
            if (desktop) configureApiRuntime({
                apiBaseUrl: "http://127.0.0.1:43127/api/v1",
                sessionToken: "desktop-" + "x".repeat(43),
            });
            ApiClient.setToken("private-account-token");
            const headersSpy = vi.spyOn(ApiClient, "getHeaders");
            const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
                new Response(JSON.stringify({ accepted: true })),
            );

            await expect(ApiClient.get(endpoint)).rejects.toThrow(/API request path/);

            expect(fetchMock).not.toHaveBeenCalled();
            expect(headersSpy).not.toHaveBeenCalled();
            expect(ApiClient._activeControllers.size).toBe(0);
        },
    );

    it.each([false, true])("preserves encoded identifiers and query values (desktop=%s)", async (desktop) => {
        if (desktop) configureApiRuntime({
            apiBaseUrl: "http://[::1]:43127/api/v1",
            sessionToken: "desktop-" + "x".repeat(43),
        });
        const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
            new Response(JSON.stringify({ accepted: true })),
        );
        const endpoint = "/jobs/r%C3%A9sum%C3%A9?query=remote+work%2Fhybrid%23CH&next=%2Fjobs%2F";

        await expect(ApiClient.get(endpoint)).resolves.toEqual({ accepted: true });

        expect(fetchMock).toHaveBeenCalledWith(
            `${getApiBase()}${endpoint}`,
            expect.objectContaining({ redirect: "error" }),
        );
    });

    it.each([
        ["http://localhost:80/api/v1/", "http://localhost/api/v1"],
        ["https://127.0.0.1:443/api/v1", "https://127.0.0.1/api/v1"],
        ["http://[::1]:43127/api/v1", "http://[::1]:43127/api/v1"],
    ])("normalizes a strict loopback API origin (%s)", (candidate, expected) => {
        configureApiRuntime({
            apiBaseUrl: candidate,
            sessionToken: "desktop-" + "x".repeat(43),
        });

        expect(getApiBase()).toBe(expected);
    });

    it.each([
        "http://localhost.evil:43127/api/v1",
        "http://127.0.0.2:43127/api/v1",
        "http://user:password@localhost:43127/api/v1",
        "http://localhost:43127/api/v1?next=/private",
        "http://localhost:43127/api/v1#private",
        "http://localhost:43127/api/v1/extra",
        "http://localhost:43127/api/v1%2Fextra",
        "http://localhost:43127/other",
    ])("rejects a malformed or expanded API boundary (%s)", (candidate) => {
        expect(() => configureApiRuntime({
            apiBaseUrl: candidate,
            sessionToken: "desktop-" + "x".repeat(43),
        })).toThrow(/VITE_API_URL/);
    });

    it("accepts only the exact same-origin browser API path", () => {
        expect(validateApiBase("/api/v1")).toBe("/api/v1");
        expect(validateApiBase("/api/v1/")).toBe("/api/v1");
        for (const candidate of [
            "//localhost/api/v1",
            "/api/v1?next=/private",
            "/api/v1#private",
            "/api/v1/extra",
            "/api/v1%2Fextra",
        ]) {
            expect(() => validateApiBase(candidate)).toThrow(/exactly/);
        }
    });
});
