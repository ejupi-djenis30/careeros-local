import { useEffect, useRef } from "react";

import { CopyButton } from "./AgentAccessShared";

export function AgentAccessTokenPanel({ issued, onCopyResult, onDismiss, t }) {
    const titleRef = useRef(null);
    const tokenRef = useRef(null);

    useEffect(() => {
        if (issued) titleRef.current?.focus();
    }, [issued]);

    if (!issued) return null;

    return (
        <section className="agent-token-panel" aria-labelledby="agent-token-title">
            <p className="visually-hidden" role="status">
                {t("agentAccess.tokenIssuedAnnouncement")}
            </p>
            <div className="agent-token-panel__heading">
                <div>
                    <span className="section-kicker">{t("agentAccess.tokenKicker")}</span>
                    <h2 id="agent-token-title" ref={titleRef} tabIndex="-1">
                        {t("agentAccess.tokenTitle")}
                    </h2>
                    <p>{t("agentAccess.tokenCopy")}</p>
                </div>
                <i className="bi bi-eye-slash" aria-hidden="true" />
            </div>
            <textarea
                ref={tokenRef}
                className="agent-token"
                aria-label={t("agentAccess.tokenLabel")}
                value={issued.token}
                readOnly
                rows="3"
                spellCheck="false"
                onFocus={(event) => event.currentTarget.select()}
            />
            <div className="agent-token-panel__actions">
                <CopyButton
                    value={issued.token}
                    label={t("agentAccess.copyToken")}
                    copiedLabel={t("agentAccess.copied")}
                    onResult={onCopyResult}
                    fallbackRef={tokenRef}
                />
                <button
                    type="button"
                    className="button button--primary button--small"
                    onClick={onDismiss}
                >
                    {t("agentAccess.dismissToken")}
                </button>
            </div>
            <p className="agent-token-warning">
                <i className="bi bi-exclamation-triangle" aria-hidden="true" />
                {t("agentAccess.tokenWarning", {
                    variable: issued.token_environment_variable,
                })}
            </p>
        </section>
    );
}
