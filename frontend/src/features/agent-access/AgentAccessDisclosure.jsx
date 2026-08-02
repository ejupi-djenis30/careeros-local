export function AgentAccessDisclosure({ activeCount, t }) {
    const countAvailable = Number.isInteger(activeCount);

    return (
        <section className="agent-access-disclosure" aria-labelledby="agent-access-disclosure-title">
            <div className="agent-access-disclosure__mark" aria-hidden="true">
                <i className="bi bi-terminal" />
            </div>
            <div>
                <span className="section-kicker">{t("agentAccess.disclosureKicker")}</span>
                <h2 id="agent-access-disclosure-title">{t("agentAccess.disclosureTitle")}</h2>
                <p>{t("agentAccess.disclosureCopy")}</p>
                <ul>
                    <li><i className="bi bi-gear" aria-hidden="true" />{t("agentAccess.scopedOperations")}</li>
                    <li><i className="bi bi-hdd" aria-hidden="true" />{t("agentAccess.localBoundary")}</li>
                    <li><i className="bi bi-door-closed" aria-hidden="true" />{t("agentAccess.leaseBoundary")}</li>
                    <li>
                        <i className="bi bi-exclamation-triangle" aria-hidden="true" />
                        {t("agentAccess.interruptedIssuance")}
                    </li>
                </ul>
            </div>
            <div
                className="agent-access-disclosure__metric"
                role="group"
                aria-label={countAvailable
                    ? t("agentAccess.activeCount", { count: activeCount })
                    : t("agentAccess.activeUnavailable")}
            >
                <strong>{countAvailable ? activeCount : "—"}</strong>
                <span>{t(countAvailable
                    ? "agentAccess.active"
                    : "agentAccess.unavailable")}
                </span>
            </div>
        </section>
    );
}
