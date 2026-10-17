import { afterEach, describe, expect, it, vi } from "vitest";

const { createRootSpy, renderSpy, navigationSpy } = vi.hoisted(() => {
    const renderSpy = vi.fn();
    return { createRootSpy: vi.fn(() => ({ render: renderSpy })), renderSpy, navigationSpy: vi.fn() };
});
vi.mock("react-dom/client", () => ({ createRoot: createRootSpy }));
vi.mock("./platform/navigation.js", () => ({ installExternalNavigation: navigationSpy }));

afterEach(() => { vi.restoreAllMocks(); document.body.replaceChildren(); });

describe("renderer root privacy wiring", () => {
    it("installs safe handlers for all React error channels at the actual entry point", async () => {
        document.body.innerHTML = '<div id="root"></div>';
        const error = vi.spyOn(console, "error").mockImplementation(() => {});
        await import("./main.jsx");
        expect(navigationSpy).toHaveBeenCalledOnce();
        expect(createRootSpy).toHaveBeenCalledOnce();
        expect(createRootSpy.mock.calls[0][0]).toBe(document.getElementById("root"));
        expect(renderSpy).toHaveBeenCalledOnce();
        const handlers = createRootSpy.mock.calls[0][1];
        expect(handlers).toEqual(expect.objectContaining({
            onCaughtError: expect.any(Function),
            onUncaughtError: expect.any(Function),
            onRecoverableError: expect.any(Function),
        }));
        const privateError = new Error("synthetic-private-render-error");
        const details = { componentStack: "synthetic-private-component-stack", errorBoundary: privateError };
        handlers.onCaughtError(privateError, details);
        handlers.onUncaughtError(privateError, details);
        handlers.onRecoverableError(privateError, details);
        expect(error.mock.calls).toEqual([
            ["ui_failure code=react_caught"],
            ["ui_failure code=react_uncaught"],
            ["ui_failure code=react_recoverable"],
        ]);
    });
});
