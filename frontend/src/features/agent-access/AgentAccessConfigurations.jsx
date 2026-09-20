import { useEffect, useMemo, useState } from "react";
import { getDesktopMcpSetup, isDesktopShell } from "../../platform/desktop";
import { getClaudeConfig, getCodexConfig } from "./agentAccessModel";
import { ConfigurationCard } from "./AgentAccessShared";

export function AgentAccessConfigurations({ onCopyResult, t }) {
    const desktop = isDesktopShell();
    const browserConfiguration = useMemo(() => ({
        codexSnippet: getCodexConfig(),
        claudeSnippet: getClaudeConfig(),
    }), []);
    const [desktopConfiguration, setDesktopConfiguration] = useState({ status: "loading" });
    const [attempt, setAttempt] = useState(0);

    useEffect(() => {
        if (!desktop) return undefined;
        const controller = new AbortController();
        getDesktopMcpSetup({ signal: controller.signal })
            .then((configuration) => {
                if (!controller.signal.aborted) {
                    setDesktopConfiguration({
                        status: "ready",
                        codexSnippet: configuration.codexToml,
                        claudeSnippet: configuration.claudeJson,
                    });
                }
            })
            .catch((error) => {
                if (!controller.signal.aborted && error?.name !== "AbortError") {
                    setDesktopConfiguration({ status: "error" });
                }
            });
        return () => controller.abort();
    }, [attempt, desktop]);

    const configuration = desktop
        ? desktopConfiguration
        : { status: "ready", ...browserConfiguration };
    const retry = () => {
        setDesktopConfiguration({ status: "loading" });
        setAttempt((value) => value + 1);
    };

    return (
        <section className="surface-section agent-configs" aria-labelledby="agent-configs-title">
            <div className="section-heading">
                <div>
                    <span className="section-kicker">{t("agentAccess.configKicker")}</span>
                    <h2 id="agent-configs-title">{t("agentAccess.configTitle")}</h2>
                </div>
                <span className="section-number">03</span>
            </div>
            <p className="section-intro">
                {t(desktop ? "agentAccess.configCopyDesktop" : "agentAccess.configCopy")}
            </p>
            {configuration.status === "loading" && (
                <div className="agent-config-state" role="status" aria-live="polite">
                    <span className="spinner-border spinner-border-sm" aria-hidden="true" />
                    <p>{t("agentAccess.configLoading")}</p>
                </div>
            )}
            {configuration.status === "error" && (
                <div className="inline-alert inline-alert--danger" role="alert">
                    <span>{t("agentAccess.configError")}</span>
                    <button type="button" className="button button--secondary" onClick={retry}>
                        {t("agentAccess.configRetry")}
                    </button>
                </div>
            )}
            {configuration.status === "ready" && (
                <div className="agent-config-grid">
                    <ConfigurationCard
                        title={t("agentAccess.client.codex")}
                        copy={t("agentAccess.codexCopy")}
                        snippet={configuration.codexSnippet}
                        t={t}
                        onCopyResult={onCopyResult}
                    />
                    <ConfigurationCard
                        title={t("agentAccess.client.claude")}
                        copy={t(desktop ? "agentAccess.claudeCopyDesktop" : "agentAccess.claudeCopy")}
                        snippet={configuration.claudeSnippet}
                        t={t}
                        onCopyResult={onCopyResult}
                    />
                </div>
            )}
            <div className="agent-config-note">
                <i className="bi bi-shield-check" aria-hidden="true" />
                <p>{t("agentAccess.configSafety")}</p>
            </div>
        </section>
    );
}
