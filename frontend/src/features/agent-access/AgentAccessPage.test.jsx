import { StrictMode } from "react";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, Link, RouterProvider } from "react-router";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CAREEROS_BEFORE_LOGOUT_EVENT } from "../../lib/events";
import { assertAccessible } from "../../test/accessibility";
import { renderWithI18n } from "../../test/renderWithI18n";
import { AutomationService } from "../../services/automation";
import { AgentAccessPage } from "./AgentAccessPage";

vi.mock("../../services/automation", () => ({
    AutomationService: {
        listGrants: vi.fn(),
        issueGrant: vi.fn(),
        revokeGrant: vi.fn(),
    },
}));

const grant = {
    id: "0f439ba0-8f52-4a2f-b56d-902e38f73ee0",
    label: "Personal Codex",
    scopes: ["system:read", "career:read"],
    expires_at: "2030-08-29T10:00:00Z",
    revoked_at: null,
    created_at: "2026-07-30T00:00:00Z",
};

const token = "obviously-fake-one-time-token";

function renderPage(
    element = <AgentAccessPage />,
    {
        initialEntries = ["/agent-access"],
        initialIndex,
    } = {},
) {
    const router = createMemoryRouter(
        [
            { path: "/agent-access", element },
            { path: "/profile", element: <p>Profile route</p> },
        ],
        { initialEntries, initialIndex },
    );
    return {
        ...renderWithI18n(<RouterProvider router={router} />),
        router,
    };
}

describe("AgentAccessPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        AutomationService.listGrants.mockResolvedValue([]);
        Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: { writeText: vi.fn().mockResolvedValue(undefined) },
        });
    });

    it("issues a least-privilege grant and exposes its token only after re-authentication", async () => {
        const user = userEvent.setup();
        const clipboardWrite = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
        const storageWrite = vi.spyOn(Storage.prototype, "setItem");
        AutomationService.issueGrant.mockResolvedValue({
            grant,
            token,
            token_environment_variable: "CAREEROS_MCP_TOKEN",
        });
        const { container } = renderPage();
        await screen.findByText("No grants issued");

        await user.type(screen.getByLabelText("Client label"), "Personal Codex");
        expect(screen.getByRole("checkbox", { name: /System status/ })).toBeChecked();
        expect(screen.getByRole("checkbox", { name: /Career summary/ })).not.toBeChecked();
        await user.click(screen.getByRole("checkbox", { name: /Career summary/ }));
        await user.type(screen.getByLabelText(/Current CareerOS password/), "CurrentPassword1");
        await user.click(screen.getByRole("button", { name: "Create grant" }));

        const tokenHeading = await screen.findByRole("heading", { name: "Save this token now" });
        expect(tokenHeading).toHaveFocus();
        expect(screen.getByRole("status", {
            name: "",
        })).toHaveTextContent(
            "The grant is ready. Save its one-time token before you continue.",
        );
        expect(screen.getByRole("status", { name: "" })).not.toHaveTextContent(token);
        expect(AutomationService.issueGrant).toHaveBeenCalledWith({
            label: "Personal Codex",
            scopes: ["system:read", "career:read"],
            lifetime_days: 30,
            password: "CurrentPassword1",
        });
        expect(screen.getByLabelText("New agent token")).toHaveValue(token);
        expect(clipboardWrite).not.toHaveBeenCalled();
        expect(storageWrite).not.toHaveBeenCalled();
        expect(screen.getByLabelText(/Current CareerOS password/)).toHaveValue("");
        await assertAccessible(container);

        await user.click(screen.getByRole("button", { name: "Copy token" }));
        expect(clipboardWrite).toHaveBeenCalledWith(token);
        await user.click(screen.getByRole("button", { name: "I saved it securely" }));
        expect(screen.queryByText(token)).not.toBeInTheDocument();
        const createGrantButton = screen.getByRole("button", { name: "Create grant" });
        expect(createGrantButton).toBeEnabled();
        expect(createGrantButton).toHaveFocus();
        storageWrite.mockRestore();
    });

    it("requires the current password to revoke an active grant", async () => {
        const user = userEvent.setup();
        AutomationService.listGrants.mockResolvedValue([grant]);
        AutomationService.revokeGrant.mockResolvedValue({
            ...grant,
            revoked_at: "2026-07-30T00:10:00Z",
        });
        const { container } = renderPage();
        await screen.findByText("Personal Codex");

        await user.click(screen.getByRole("button", { name: "Revoke access" }));
        const passwordInput = screen.getByLabelText(
            "Enter your current password to revoke this grant",
        );
        expect(passwordInput).toHaveFocus();
        await assertAccessible(container);
        await user.click(screen.getByRole("button", { name: "Cancel" }));
        const revokeButton = screen.getByRole("button", { name: "Revoke access" });
        await waitFor(() => expect(revokeButton).toHaveFocus());

        await user.click(revokeButton);
        await user.type(
            screen.getByLabelText("Enter your current password to revoke this grant"),
            "CurrentPassword1",
        );
        await user.click(screen.getByRole("button", { name: "Confirm revocation" }));

        await waitFor(() => expect(AutomationService.revokeGrant).toHaveBeenCalledWith(
            grant.id,
            "CurrentPassword1",
        ));
        const revokedStatus = await screen.findByText("Revoked");
        await waitFor(() => expect(revokedStatus).toHaveFocus());
        expect(screen.getByRole("status")).toHaveTextContent(
            "Access for Personal Codex was revoked.",
        );
        expect(screen.queryByRole("button", { name: "Revoke access" })).not.toBeInTheDocument();
        await assertAccessible(container);
    });

    it("keeps other revocation controls locked while one password check is running", async () => {
        const user = userEvent.setup();
        const secondGrant = {
            ...grant,
            id: "73c2e420-bf74-4fd9-b2f5-387114140d11",
            label: "Claude Code",
        };
        let resolveRevocation;
        AutomationService.listGrants.mockResolvedValue([grant, secondGrant]);
        AutomationService.revokeGrant.mockImplementation(() => new Promise((resolve) => {
            resolveRevocation = resolve;
        }));
        renderPage();
        await screen.findByText("Personal Codex");

        const openers = screen.getAllByRole("button", { name: "Revoke access" });
        await user.click(openers[0]);
        await user.type(
            screen.getByLabelText("Enter your current password to revoke this grant"),
            "CurrentPassword1",
        );
        await user.click(screen.getByRole("button", { name: "Confirm revocation" }));

        await waitFor(() => expect(AutomationService.revokeGrant).toHaveBeenCalled());
        expect(screen.getByRole("button", { name: "Revoke access" })).toBeDisabled();

        resolveRevocation({
            ...grant,
            revoked_at: "2026-07-30T00:10:00Z",
        });
        await screen.findByText("Revoked");
        expect(screen.getByRole("button", { name: "Revoke access" })).toBeEnabled();
    });

    it("announces an ordinary revocation if the user dismisses the token while it is pending", async () => {
        const user = userEvent.setup();
        let resolveRevocation;
        AutomationService.issueGrant.mockResolvedValue({
            grant,
            token,
            token_environment_variable: "CAREEROS_MCP_TOKEN",
        });
        AutomationService.revokeGrant.mockImplementation(() => new Promise((resolve) => {
            resolveRevocation = resolve;
        }));
        renderPage();
        await screen.findByText("No grants issued");

        await user.type(screen.getByLabelText("Client label"), grant.label);
        await user.type(screen.getByLabelText(/Current CareerOS password/), "CurrentPassword1");
        await user.click(screen.getByRole("button", { name: "Create grant" }));
        await screen.findByLabelText("New agent token");
        await user.click(screen.getByRole("button", { name: "Revoke access" }));
        await user.type(
            screen.getByLabelText("Enter your current password to revoke this grant"),
            "CurrentPassword1",
        );
        await user.click(screen.getByRole("button", { name: "Confirm revocation" }));
        await user.click(screen.getByRole("button", { name: "I saved it securely" }));

        await act(async () => {
            resolveRevocation({
                ...grant,
                revoked_at: "2026-07-30T00:10:00Z",
            });
        });

        expect(await screen.findByText("Access for Personal Codex was revoked."))
            .toHaveAttribute("role", "status");
        expect(screen.queryByText(/unsaved token was discarded/)).not.toBeInTheDocument();
    });

    it("keeps issuance single-flight across synchronous duplicate submissions", async () => {
        const user = userEvent.setup();
        let resolveIssuance;
        AutomationService.issueGrant.mockImplementation(() => new Promise((resolve) => {
            resolveIssuance = resolve;
        }));
        renderPage();
        await screen.findByText("No grants issued");

        await user.type(screen.getByLabelText("Client label"), "Single flight");
        await user.type(screen.getByLabelText(/Current CareerOS password/), "CurrentPassword1");
        const form = screen.getByRole("button", { name: "Create grant" }).closest("form");
        fireEvent.submit(form);
        fireEvent.submit(form);

        expect(AutomationService.issueGrant).toHaveBeenCalledTimes(1);
        await act(async () => {
            resolveIssuance({
                grant,
                token,
                token_environment_variable: "CAREEROS_MCP_TOKEN",
            });
        });
        expect(await screen.findByLabelText("New agent token")).toHaveValue(token);
    });

    it("preserves non-secret choices after failed re-authentication and clears the password", async () => {
        const user = userEvent.setup();
        AutomationService.issueGrant.mockRejectedValue({
            message: "Current CareerOS password verification failed",
            details: { detail: { code: "authentication_failed" } },
        });
        renderPage();
        await screen.findByText("No grants issued");

        await user.type(screen.getByLabelText("Client label"), "Claude review");
        await user.click(screen.getByRole("checkbox", { name: /Resume catalogue/ }));
        await user.type(screen.getByLabelText(/Current CareerOS password/), "WrongPassword1");
        await user.click(screen.getByRole("button", { name: "Create grant" }));

        expect(await screen.findByRole("alert")).toHaveTextContent(
            "That password did not match this local CareerOS account.",
        );
        expect(screen.getByLabelText("Client label")).toHaveValue("Claude review");
        expect(screen.getByRole("checkbox", { name: /Resume catalogue/ })).toBeChecked();
        expect(screen.getByLabelText(/Current CareerOS password/)).toHaveValue("");
    });

    it("removes an undismissed bearer when the route unmounts without persisting it", async () => {
        const user = userEvent.setup();
        const storageWrite = vi.spyOn(Storage.prototype, "setItem");
        AutomationService.issueGrant.mockResolvedValue({
            grant,
            token,
            token_environment_variable: "CAREEROS_MCP_TOKEN",
        });
        const { unmount } = renderPage();
        await screen.findByText("No grants issued");

        await user.type(screen.getByLabelText("Client label"), "Temporary agent");
        await user.type(screen.getByLabelText(/Current CareerOS password/), "CurrentPassword1");
        await user.click(screen.getByRole("button", { name: "Create grant" }));
        await waitFor(() => expect(screen.getByLabelText("New agent token")).toHaveValue(token));
        unmount();

        expect(screen.queryByLabelText("New agent token")).not.toBeInTheDocument();
        expect(storageWrite).not.toHaveBeenCalled();
        storageWrite.mockRestore();
    });

    it("keeps a completed issuance visible through the StrictMode effect replay", async () => {
        const user = userEvent.setup();
        AutomationService.issueGrant.mockResolvedValue({
            grant,
            token,
            token_environment_variable: "CAREEROS_MCP_TOKEN",
        });
        renderPage(<StrictMode><AgentAccessPage /></StrictMode>);
        await screen.findByText("No grants issued");

        await user.type(screen.getByLabelText("Client label"), "Strict mode agent");
        await user.type(screen.getByLabelText(/Current CareerOS password/), "CurrentPassword1");
        await user.click(screen.getByRole("button", { name: "Create grant" }));

        expect(await screen.findByLabelText("New agent token")).toHaveValue(token);
        expect(AutomationService.issueGrant).toHaveBeenCalledTimes(1);
        expect(AutomationService.revokeGrant).not.toHaveBeenCalled();
    });

    it("revokes a grant that finishes after the page is forcibly unmounted", async () => {
        const user = userEvent.setup();
        let resolveIssuance;
        AutomationService.issueGrant.mockImplementation(() => new Promise((resolve) => {
            resolveIssuance = resolve;
        }));
        AutomationService.revokeGrant.mockResolvedValue({
            ...grant,
            revoked_at: "2026-07-30T00:10:00Z",
        });
        const { unmount } = renderPage();
        await screen.findByText("No grants issued");

        await user.type(screen.getByLabelText("Client label"), "Late agent");
        await user.type(screen.getByLabelText(/Current CareerOS password/), "CurrentPassword1");
        await user.click(screen.getByRole("button", { name: "Create grant" }));
        unmount();
        await act(async () => {
            resolveIssuance({
                grant,
                token,
                token_environment_variable: "CAREEROS_MCP_TOKEN",
            });
        });

        await waitFor(() => expect(AutomationService.revokeGrant).toHaveBeenCalledWith(
            grant.id,
            "CurrentPassword1",
        ));
        expect(screen.queryByLabelText("New agent token")).not.toBeInTheDocument();
    });

    it("waits for compensating revocation before a forced logout may continue", async () => {
        const user = userEvent.setup();
        let resolveIssuance;
        AutomationService.issueGrant.mockImplementation(() => new Promise((resolve) => {
            resolveIssuance = resolve;
        }));
        AutomationService.revokeGrant.mockResolvedValue({
            ...grant,
            revoked_at: "2026-07-30T00:10:00Z",
        });
        renderPage();
        await screen.findByText("No grants issued");

        await user.type(screen.getByLabelText("Client label"), "Forced logout agent");
        await user.type(screen.getByLabelText(/Current CareerOS password/), "CurrentPassword1");
        await user.click(screen.getByRole("button", { name: "Create grant" }));

        const waiters = [];
        const logoutEvent = new CustomEvent(CAREEROS_BEFORE_LOGOUT_EVENT, {
            cancelable: true,
            detail: {
                force: true,
                waitUntil(waiter) {
                    waiters.push(waiter);
                },
            },
        });
        expect(window.dispatchEvent(logoutEvent)).toBe(false);
        expect(waiters).toHaveLength(1);

        await act(async () => {
            resolveIssuance({
                grant,
                token,
                token_environment_variable: "CAREEROS_MCP_TOKEN",
            });
            await Promise.all(waiters);
        });

        expect(AutomationService.revokeGrant).toHaveBeenCalledWith(
            grant.id,
            "CurrentPassword1",
        );
        expect(screen.queryByLabelText("New agent token")).not.toBeInTheDocument();
    });

    it("blocks normal navigation and logout while one-time token issuance is pending", async () => {
        const user = userEvent.setup();
        const closeMobileMenu = vi.fn();
        AutomationService.issueGrant.mockImplementation(() => new Promise(() => {}));
        const { router } = renderPage(
            <div>
                <a href="#agent-access-content">Skip to Agent access</a>
                <Link to="/profile" onClick={closeMobileMenu}>Router profile link</Link>
                <a href="/profile">Leave Agent access</a>
                <div id="agent-access-content">
                    <AgentAccessPage />
                </div>
            </div>,
            {
                initialEntries: ["/profile", "/agent-access"],
                initialIndex: 1,
            },
        );
        await screen.findByText("No grants issued");

        await user.type(screen.getByLabelText("Client label"), "Pending agent");
        await user.type(screen.getByLabelText(/Current CareerOS password/), "CurrentPassword1");
        await user.click(screen.getByRole("button", { name: "Create grant" }));

        const logoutEvent = new Event("careeros:before-logout", { cancelable: true });
        expect(window.dispatchEvent(logoutEvent)).toBe(false);
        expect(logoutEvent.defaultPrevented).toBe(true);
        await act(async () => {
            await router.navigate("/profile");
        });
        await waitFor(() => expect(router.state.location.pathname).toBe("/agent-access"));
        await act(async () => {
            await router.navigate(-1);
        });
        await waitFor(() => expect(router.state.location.pathname).toBe("/agent-access"));
        await user.click(screen.getByRole("link", { name: "Router profile link" }));
        expect(closeMobileMenu).toHaveBeenCalledTimes(1);
        await waitFor(() => expect(router.state.location.pathname).toBe("/agent-access"));
        await user.click(screen.getByRole("link", { name: "Skip to Agent access" }));
        expect(router.state.location.pathname).toBe("/agent-access");
        await user.click(screen.getByRole("link", { name: "Leave Agent access" }));
        expect(screen.getByRole("alert")).toHaveTextContent(
            "CareerOS is finishing this grant.",
        );

        const unloadEvent = new Event("beforeunload", { cancelable: true });
        expect(window.dispatchEvent(unloadEvent)).toBe(false);
        expect(unloadEvent.defaultPrevented).toBe(true);
    });

    it.each([
        ["is unavailable", undefined],
        ["rejects the write", { writeText: vi.fn().mockRejectedValue(new Error("denied")) }],
    ])("focuses and selects the token when clipboard access %s", async (_case, clipboard) => {
        const user = userEvent.setup();
        Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: clipboard,
        });
        AutomationService.issueGrant.mockResolvedValue({
            grant,
            token,
            token_environment_variable: "CAREEROS_MCP_TOKEN",
        });
        renderPage();
        await screen.findByText("No grants issued");

        await user.type(screen.getByLabelText("Client label"), "Manual copy");
        await user.type(screen.getByLabelText(/Current CareerOS password/), "CurrentPassword1");
        await user.click(screen.getByRole("button", { name: "Create grant" }));
        const tokenField = await screen.findByLabelText("New agent token");
        await user.click(screen.getByRole("button", { name: "Copy token" }));

        await waitFor(() => expect(tokenField).toHaveFocus());
        expect(tokenField.selectionStart).toBe(0);
        expect(tokenField.selectionEnd).toBe(token.length);
        expect(screen.getByText(
            "Clipboard access is unavailable. Select and copy the text manually.",
        )).toHaveAttribute("role", "status");
    });

    it("discards the displayed bearer when its grant is revoked", async () => {
        const user = userEvent.setup();
        AutomationService.issueGrant.mockResolvedValue({
            grant,
            token,
            token_environment_variable: "CAREEROS_MCP_TOKEN",
        });
        AutomationService.revokeGrant.mockResolvedValue({
            ...grant,
            revoked_at: "2026-07-30T00:10:00Z",
        });
        renderPage();
        await screen.findByText("No grants issued");

        await user.type(screen.getByLabelText("Client label"), grant.label);
        await user.type(screen.getByLabelText(/Current CareerOS password/), "CurrentPassword1");
        await user.click(screen.getByRole("button", { name: "Create grant" }));
        expect(await screen.findByLabelText("New agent token")).toHaveValue(token);
        await user.click(screen.getByRole("button", { name: "Revoke access" }));
        await user.type(
            screen.getByLabelText("Enter your current password to revoke this grant"),
            "CurrentPassword1",
        );
        await user.click(screen.getByRole("button", { name: "Confirm revocation" }));

        expect(await screen.findByText("Revoked")).toHaveFocus();
        expect(screen.queryByLabelText("New agent token")).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Copy token" })).not.toBeInTheDocument();
        expect(screen.getByRole("status")).toHaveTextContent(
            "its unsaved token was discarded",
        );
        expect(screen.getByRole("button", { name: "Create grant" })).not.toHaveFocus();
    });

    it("keeps token-free client snippets and passes the accessibility gate", async () => {
        const { container } = renderPage(
            <main><h1>Agent access test</h1><AgentAccessPage /></main>,
        );
        await screen.findByText("No grants issued");

        expect(screen.getByText("[mcp_servers.careeros]", { exact: false })).not.toHaveTextContent(token);
        expect(screen.getByText("claude mcp add", { exact: false })).not.toHaveTextContent(token);
        expect(container).not.toHaveTextContent("careeros_mcp_v1_");
        await assertAccessible(container);
    });

    it("does not report zero active grants when the register is unavailable", async () => {
        AutomationService.listGrants.mockRejectedValue(new Error("Database unavailable"));
        const { container } = renderPage();

        expect(await screen.findByRole("alert")).toHaveTextContent("Database unavailable");
        const unavailable = screen.getByLabelText("Agent grant count unavailable");
        expect(unavailable).toHaveTextContent("—");
        expect(unavailable).toHaveTextContent("unavailable");
        expect(screen.queryByLabelText("0 active agent grants")).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Create grant" })).toBeDisabled();
        await assertAccessible(container);
    });

    it("does not enable grant creation before the access register is loaded", async () => {
        let resolveRegister;
        AutomationService.listGrants.mockImplementation(() => new Promise((resolve) => {
            resolveRegister = resolve;
        }));
        renderPage();

        expect(screen.getByRole("button", { name: "Create grant" })).toBeDisabled();
        expect(screen.getByLabelText("Client label")).toBeDisabled();
        expect(AutomationService.issueGrant).not.toHaveBeenCalled();

        resolveRegister([]);
        await screen.findByText("No grants issued");
        expect(screen.getByRole("button", { name: "Create grant" })).toBeEnabled();
        expect(screen.getByLabelText("Client label")).toBeEnabled();
    });
});
