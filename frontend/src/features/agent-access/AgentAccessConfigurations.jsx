import { CLAUDE_CONFIG, CODEX_CONFIG } from "./agentAccessModel";
import { ConfigurationCard } from "./AgentAccessShared";

export function AgentAccessConfigurations({ onCopyResult, t }) {
    return (
        <section className="surface-section agent-configs" aria-labelledby="agent-configs-title">
            <div className="section-heading">
                <div>
                    <span className="section-kicker">{t("agentAccess.configKicker")}</span>
                    <h2 id="agent-configs-title">{t("agentAccess.configTitle")}</h2>
                </div>
                <span className="section-number">03</span>
            </div>
            <p className="section-intro">{t("agentAccess.configCopy")}</p>
            <div className="agent-config-grid">
                <ConfigurationCard
                    title={t("agentAccess.client.codex")}
                    copy={t("agentAccess.codexCopy")}
                    snippet={CODEX_CONFIG}
                    t={t}
                    onCopyResult={onCopyResult}
                />
                <ConfigurationCard
                    title={t("agentAccess.client.claude")}
                    copy={t("agentAccess.claudeCopy")}
                    snippet={CLAUDE_CONFIG}
                    t={t}
                    onCopyResult={onCopyResult}
                />
            </div>
            <div className="agent-config-note">
                <i className="bi bi-shield-check" aria-hidden="true" />
                <p>{t("agentAccess.configSafety")}</p>
            </div>
        </section>
    );
}
