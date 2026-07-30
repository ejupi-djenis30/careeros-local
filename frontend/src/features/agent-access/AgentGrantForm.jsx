import { SCOPES } from "./agentAccessModel";

function ScopePicker({ scopes, disabled, onToggle, t }) {
    return (
        <fieldset className="agent-scope-picker" disabled={disabled}>
            <legend>{t("agentAccess.scopes")}</legend>
            <p>{t("agentAccess.scopesCopy")}</p>
            <div>
                {SCOPES.map((scope) => (
                    <label
                        key={scope}
                        className={`agent-scope-option ${scopes.includes(scope) ? "is-selected" : ""}`}
                    >
                        <input
                            type="checkbox"
                            checked={scopes.includes(scope)}
                            onChange={() => onToggle(scope)}
                        />
                        <span>
                            <strong>{t(`agentAccess.scope.${scope}.title`)}</strong>
                            <small>{t(`agentAccess.scope.${scope}.copy`)}</small>
                        </span>
                        <code>{scope}</code>
                    </label>
                ))}
            </div>
        </fieldset>
    );
}

export function AgentGrantForm({ state, actions, issueButtonRef, t }) {
    const registryUnavailable = state.loading || Boolean(state.loadError);
    const locked = Boolean(state.issued) || registryUnavailable;

    return (
        <section className="surface-section agent-grant-form" aria-labelledby="agent-grant-title">
            <div className="section-heading">
                <div>
                    <span className="section-kicker">{t("agentAccess.issueKicker")}</span>
                    <h2 id="agent-grant-title">{t("agentAccess.issueTitle")}</h2>
                </div>
                <span className="section-number">01</span>
            </div>
            <p className="section-intro">{t("agentAccess.issueCopy")}</p>
            <form onSubmit={actions.issueGrant}>
                <div className="form-grid form-grid--2">
                    <label className="field-stack">
                        <span>{t("agentAccess.label")}</span>
                        <input
                            className="form-control"
                            value={state.label}
                            onChange={(event) => actions.setLabel(event.target.value)}
                            minLength="1"
                            maxLength="120"
                            autoComplete="off"
                            placeholder={t("agentAccess.labelPlaceholder")}
                            disabled={locked}
                            required
                        />
                    </label>
                    <label className="field-stack">
                        <span>{t("agentAccess.lifetime")}</span>
                        <select
                            className="form-select"
                            value={state.lifetimeDays}
                            onChange={(event) => actions.setLifetimeDays(event.target.value)}
                            disabled={locked}
                        >
                            {[7, 30, 90, 365].map((days) => (
                                <option key={days} value={days}>
                                    {t("agentAccess.days", { count: days })}
                                </option>
                            ))}
                        </select>
                    </label>
                </div>
                <ScopePicker
                    scopes={state.scopes}
                    disabled={locked}
                    onToggle={actions.toggleScope}
                    t={t}
                />
                <label className="field-stack">
                    <span>{t("agentAccess.password")}</span>
                    <input
                        className="form-control"
                        type="password"
                        value={state.password}
                        onChange={(event) => actions.setPassword(event.target.value)}
                        autoComplete="current-password"
                        disabled={locked}
                        required
                    />
                    <small>{t("agentAccess.passwordCopy")}</small>
                </label>
                {state.scopes.length === 0 && (
                    <p className="agent-inline-error" role="alert">{t("agentAccess.scopeRequired")}</p>
                )}
                {state.createMessage && (
                    <p className="agent-inline-error" role="alert">{state.createMessage}</p>
                )}
                <button
                    ref={issueButtonRef}
                    className="button button--primary"
                    type="submit"
                    disabled={state.creating || locked || state.scopes.length === 0}
                >
                    <i className="bi bi-key" aria-hidden="true" />
                    {state.creating ? t("agentAccess.issuing") : t("agentAccess.issue")}
                </button>
            </form>
        </section>
    );
}
