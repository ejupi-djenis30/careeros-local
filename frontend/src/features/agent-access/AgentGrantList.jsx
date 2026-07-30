import { useEffect, useRef } from "react";

import { grantState } from "./agentAccessModel";

function RevokeForm({ grantId, state, actions, t }) {
    return (
        <form
            className="agent-revoke-form"
            onSubmit={(event) => actions.revokeGrant(event, grantId)}
        >
            <label className="field-stack">
                <span>{t("agentAccess.revokePassword")}</span>
                <input
                    className="form-control"
                    type="password"
                    value={state.revokePassword}
                    onChange={(event) => actions.setRevokePassword(event.target.value)}
                    autoComplete="current-password"
                    autoFocus
                    required
                />
            </label>
            {state.revokeMessage && (
                <p className="agent-inline-error" role="alert">{state.revokeMessage}</p>
            )}
            <div className="button-cluster">
                <button
                    type="submit"
                    className="button button--danger-subtle button--small"
                    disabled={state.revokeBusy}
                >
                    {state.revokeBusy ? t("agentAccess.revoking") : t("agentAccess.confirmRevoke")}
                </button>
                <button
                    type="button"
                    className="button button--secondary button--small"
                    onClick={actions.cancelRevoke}
                    disabled={state.revokeBusy}
                >
                    {t("agentAccess.cancel")}
                </button>
            </div>
        </form>
    );
}

function GrantCard({ grant, state, actions, locale, t }) {
    const status = grantState(grant, state.now);
    const revokeButtonRef = useRef(null);
    const statusRef = useRef(null);
    const wasRevoking = useRef(false);
    const isRevoking = state.revokingId === grant.id;

    useEffect(() => {
        if (wasRevoking.current && !isRevoking) {
            if (status === "active") {
                revokeButtonRef.current?.focus();
            } else {
                statusRef.current?.focus();
            }
        }
        wasRevoking.current = isRevoking;
    }, [isRevoking, status]);

    return (
        <article className={`agent-grant-card is-${status}`}>
            <div className="agent-grant-card__heading">
                <div>
                    <strong>{grant.label}</strong>
                    <span
                        ref={statusRef}
                        className={`agent-state is-${status}`}
                        tabIndex={-1}
                    >
                        {t(`agentAccess.state.${status}`)}
                    </span>
                </div>
                <time dateTime={grant.expires_at}>
                    {t("agentAccess.expires", {
                        date: new Date(grant.expires_at).toLocaleDateString(locale, {
                            day: "2-digit",
                            month: "short",
                            year: "numeric",
                        }),
                    })}
                </time>
            </div>
            <div className="agent-grant-card__scopes">
                {grant.scopes.map((scope) => <code key={scope}>{scope}</code>)}
            </div>
            {status === "active" && !isRevoking && (
                <button
                    ref={revokeButtonRef}
                    type="button"
                    className="button button--danger-subtle button--small"
                    onClick={() => actions.beginRevoke(grant.id)}
                    disabled={state.revokeBusy}
                >
                    {t("agentAccess.revoke")}
                </button>
            )}
            {isRevoking && (
                <RevokeForm grantId={grant.id} state={state} actions={actions} t={t} />
            )}
        </article>
    );
}

function GrantListContent({ state, actions, locale, t }) {
    if (state.loading) {
        return <p className="agent-list-state" role="status">{t("agentAccess.loading")}</p>;
    }
    if (state.loadError) {
        return (
            <div className="agent-list-state" role="alert">
                <p>{state.loadError}</p>
                <button
                    type="button"
                    className="button button--secondary button--small"
                    onClick={actions.retryLoad}
                >
                    {t("agentAccess.retry")}
                </button>
            </div>
        );
    }
    if (state.grants.length === 0) {
        return (
            <div className="agent-list-state">
                <i className="bi bi-shield-lock" aria-hidden="true" />
                <strong>{t("agentAccess.emptyTitle")}</strong>
                <p>{t("agentAccess.emptyCopy")}</p>
            </div>
        );
    }
    return (
        <div className="agent-grant-list">
            {state.grants.map((grant) => (
                <GrantCard
                    key={grant.id}
                    grant={grant}
                    state={state}
                    actions={actions}
                    locale={locale}
                    t={t}
                />
            ))}
        </div>
    );
}

export function AgentGrantList({ state, actions, locale, t }) {
    return (
        <section className="surface-section agent-grants" aria-labelledby="agent-grants-title">
            <div className="section-heading">
                <div>
                    <span className="section-kicker">{t("agentAccess.grantsKicker")}</span>
                    <h2 id="agent-grants-title">{t("agentAccess.grantsTitle")}</h2>
                </div>
                <span className="section-number">02</span>
            </div>
            <GrantListContent state={state} actions={actions} locale={locale} t={t} />
        </section>
    );
}
