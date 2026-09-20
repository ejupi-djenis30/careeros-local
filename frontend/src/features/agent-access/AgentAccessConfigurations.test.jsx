import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { assertAccessible } from "../../test/accessibility";

const desktopBridge = vi.hoisted(() => ({
    getDesktopMcpSetup: vi.fn(),
    isDesktopShell: vi.fn(),
}));

vi.mock("../../platform/desktop", () => desktopBridge);

import { AgentAccessConfigurations } from "./AgentAccessConfigurations";

const messages = {
    "agentAccess.configKicker": "Connect a client",
    "agentAccess.configTitle": "Token-free configuration",
    "agentAccess.configCopy": "Development configuration",
    "agentAccess.configCopyDesktop": "Installed configuration",
    "agentAccess.configLoading": "Preparing installed launcher",
    "agentAccess.configError": "Installed launcher unavailable",
    "agentAccess.configRetry": "Retry launcher check",
    "agentAccess.client.codex": "Codex",
    "agentAccess.client.claude": "Claude Code",
    "agentAccess.codexCopy": "Codex copy",
    "agentAccess.claudeCopy": "Claude command copy",
    "agentAccess.claudeCopyDesktop": "Claude JSON copy",
    "agentAccess.copyConfig": "Copy configuration",
    "agentAccess.copied": "Copied",
    "agentAccess.configSafety": "No credential is included.",
};
const t = (key) => messages[key] ?? key;

function installedConfiguration() {
    return {
        command: "C:\\Program Files\\CareerOS\\careeros-mcp.exe",
        args: [
            "--connection-file",
            "C:\\Users\\Demo\\CareerOS\\mcp\\connection.json",
            "--acknowledge-agent-disclosure",
        ],
        connectionFile: "C:\\Users\\Demo\\CareerOS\\mcp\\connection.json",
        tokenEnvironmentVariable: "CAREEROS_MCP_TOKEN",
        codexToml: "[mcp_servers.careeros]\ncommand = \"C:\\\\Program Files\\\\CareerOS\\\\careeros-mcp.exe\"\n",
        claudeJson: '{"mcpServers":{"careeros":{"command":"C:\\\\Program Files\\\\CareerOS\\\\careeros-mcp.exe"}}}',
    };
}

describe("AgentAccessConfigurations", () => {
    beforeEach(() => {
        desktopBridge.isDesktopShell.mockReset().mockReturnValue(false);
        desktopBridge.getDesktopMcpSetup.mockReset();
    });

    it("keeps an explicit browser-development configuration available", async () => {
        const { container } = render(
            <AgentAccessConfigurations onCopyResult={vi.fn()} t={t} />,
        );

        expect(screen.getByText("Development configuration")).toBeInTheDocument();
        expect(screen.getAllByText(/--desktop-url/)).toHaveLength(2);
        expect(screen.getAllByText(/--acknowledge-agent-disclosure/)).toHaveLength(2);
        expect(desktopBridge.getDesktopMcpSetup).not.toHaveBeenCalled();
        await assertAccessible(container);
    });

    it("shows only native-verified installed snippets in the desktop shell", async () => {
        desktopBridge.isDesktopShell.mockReturnValue(true);
        const setup = installedConfiguration();
        desktopBridge.getDesktopMcpSetup.mockResolvedValue(setup);
        const { container } = render(
            <AgentAccessConfigurations onCopyResult={vi.fn()} t={t} />,
        );

        expect(screen.getByRole("status")).toHaveTextContent("Preparing installed launcher");
        await waitFor(() => expect(container.querySelectorAll(".agent-config-card code")).toHaveLength(2));
        const snippets = [...container.querySelectorAll(".agent-config-card code")]
            .map((element) => element.textContent);
        expect(snippets).toEqual([setup.codexToml, setup.claudeJson]);
        expect(screen.getByText("Installed configuration")).toBeInTheDocument();
        expect(screen.getByText("Claude JSON copy")).toBeInTheDocument();
        expect(screen.queryByText(/--desktop-url/)).not.toBeInTheDocument();
        expect(desktopBridge.getDesktopMcpSetup).toHaveBeenCalledTimes(1);
        await assertAccessible(container);
    });

    it("fails closed in desktop mode and retries the native launcher check", async () => {
        desktopBridge.isDesktopShell.mockReturnValue(true);
        const setup = installedConfiguration();
        desktopBridge.getDesktopMcpSetup
            .mockRejectedValueOnce(new Error("native path detail"))
            .mockResolvedValueOnce(setup);
        const { container } = render(
            <AgentAccessConfigurations onCopyResult={vi.fn()} t={t} />,
        );

        const alert = await screen.findByRole("alert");
        expect(alert).toHaveTextContent("Installed launcher unavailable");
        expect(alert).not.toHaveTextContent("native path detail");
        expect(screen.queryByRole("heading", { name: "Codex" })).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Retry launcher check" }));

        expect(screen.getByRole("status")).toHaveTextContent("Preparing installed launcher");
        await waitFor(() => expect(container.querySelector(".agent-config-card code")?.textContent)
            .toBe(setup.codexToml));
        expect(desktopBridge.getDesktopMcpSetup).toHaveBeenCalledTimes(2);
    });

    it("aborts a pending native request when the configuration view unmounts", async () => {
        desktopBridge.isDesktopShell.mockReturnValue(true);
        let ownerSignal;
        desktopBridge.getDesktopMcpSetup.mockImplementation(({ signal }) => {
            ownerSignal = signal;
            return new Promise(() => {});
        });
        const view = render(<AgentAccessConfigurations onCopyResult={vi.fn()} t={t} />);
        await waitFor(() => expect(ownerSignal).toBeInstanceOf(AbortSignal));

        view.unmount();

        expect(ownerSignal.aborted).toBe(true);
    });
});
