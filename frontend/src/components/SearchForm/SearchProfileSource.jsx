import React from "react";
import { Link } from "react-router";
import { useI18n } from "../../i18n/useI18n";

export function SearchProfileSource({
    source,
    onSourceChange,
    vault,
    onRetryVault,
    cvReady,
    isUploading,
    onUpload,
    error,
}) {
    const { t } = useI18n();
    const vaultReady = vault.status === "ready";

    return (
        <section className="search-profile-source" aria-labelledby="search-profile-source-title">
            <div className="search-profile-source__heading">
                <div>
                    <p className="search-section-label">{t("searchForm.profileSource.eyebrow")}</p>
                    <h3 id="search-profile-source-title">{t("searchForm.profileSource.title")}</h3>
                </div>
                <span className="search-profile-source__required">{t("searchForm.required")}</span>
            </div>
            <p className="search-profile-source__copy">{t("searchForm.profileSource.copy")}</p>

            <fieldset className="profile-source-options" aria-describedby={error ? "profile-source-error" : undefined}>
                <legend className="visually-hidden">{t("searchForm.profileSource.legend")}</legend>

                <div className={`profile-source-card ${source === "career_vault" ? "is-selected" : ""}`}>
                    <label htmlFor="profile-source-career-vault" className="profile-source-card__selector">
                        <input
                            className="visually-hidden"
                            id="profile-source-career-vault"
                            type="radio"
                            name="profile_source"
                            value="career_vault"
                            checked={source === "career_vault"}
                            onChange={onSourceChange}
                            aria-invalid={Boolean(error) || undefined}
                        />
                        <span className="profile-source-card__icon" aria-hidden="true">
                            <i className="bi bi-shield-check" />
                        </span>
                        <span className="profile-source-card__body">
                            <strong>{t("searchForm.profileSource.vault")}</strong>
                            <small>{t("searchForm.profileSource.vaultCopy")}</small>
                        </span>
                        <span className="profile-source-card__check" aria-hidden="true">
                            <i className="bi bi-check-lg" />
                        </span>
                    </label>

                    <div className="profile-source-card__status" aria-live="polite">
                        {vault.status === "loading" && (
                            <span className="profile-source-status is-loading">
                                <span className="spinner-border spinner-border-sm" aria-hidden="true" />
                                {t("searchForm.profileSource.checking")}
                            </span>
                        )}
                        {vaultReady && (
                            <span className="profile-source-status is-ready">
                                <i className="bi bi-check-circle-fill" aria-hidden="true" />
                                {t("searchForm.profileSource.ready")}
                            </span>
                        )}
                        {vaultReady && (
                            <span className="profile-source-card__meta">
                                <span>{t("searchForm.profileSource.revision", { revision: vault.revision })}</span>
                                <span aria-hidden="true">·</span>
                                <span>{t("searchForm.profileSource.confirmedFacts", { count: vault.confirmedFacts })}</span>
                            </span>
                        )}
                        {vault.status === "missing" && (
                            <>
                                <span className="profile-source-status is-warning">
                                    <i className="bi bi-exclamation-circle-fill" aria-hidden="true" />
                                    {t("searchForm.profileSource.notReady")}
                                </span>
                                <Link className="button button--secondary button--small" to="/profile">
                                    {t("searchForm.profileSource.openVault")}
                                    <i className="bi bi-arrow-right" aria-hidden="true" />
                                </Link>
                            </>
                        )}
                        {vault.status === "error" && (
                            <>
                                <span className="profile-source-status is-warning">
                                    <i className="bi bi-exclamation-circle-fill" aria-hidden="true" />
                                    {t("searchForm.profileSource.loadError")}
                                </span>
                                <button className="button button--secondary button--small" type="button" onClick={onRetryVault}>
                                    {t("searchForm.profileSource.retry")}
                                </button>
                            </>
                        )}
                    </div>
                </div>

                <div className={`profile-source-card ${source === "uploaded_cv" ? "is-selected" : ""}`}>
                    <label htmlFor="profile-source-uploaded-cv" className="profile-source-card__selector">
                        <input
                            className="visually-hidden"
                            id="profile-source-uploaded-cv"
                            type="radio"
                            name="profile_source"
                            value="uploaded_cv"
                            checked={source === "uploaded_cv"}
                            onChange={onSourceChange}
                            aria-invalid={Boolean(error) || undefined}
                        />
                        <span className="profile-source-card__icon" aria-hidden="true">
                            <i className="bi bi-file-earmark-person" />
                        </span>
                        <span className="profile-source-card__body">
                            <strong>{t("searchForm.profileSource.upload")}</strong>
                            <small>{t("searchForm.profileSource.uploadCopy")}</small>
                        </span>
                        <span className="profile-source-card__check" aria-hidden="true">
                            <i className="bi bi-check-lg" />
                        </span>
                    </label>

                    {source === "uploaded_cv" && (
                        <div className="profile-source-card__status">
                            <span className={`profile-source-status ${cvReady ? "is-ready" : ""}`}>
                                <i className={`bi ${cvReady ? "bi-check-circle-fill" : "bi-file-earmark-arrow-up"}`} aria-hidden="true" />
                                {cvReady
                                    ? t("searchForm.profileSource.uploadReady")
                                    : t("searchForm.profileSource.uploadNeeded")}
                            </span>
                            <label className="button button--secondary button--small" htmlFor="search-cv-upload">
                                {isUploading
                                    ? t("searchForm.profileSource.uploading")
                                    : cvReady
                                        ? t("searchForm.change")
                                        : t("searchForm.select")}
                            </label>
                            <input
                                className="visually-hidden"
                                id="search-cv-upload"
                                type="file"
                                accept=".pdf,.txt,.md"
                                onChange={onUpload}
                                disabled={isUploading}
                                aria-invalid={source === "uploaded_cv" && Boolean(error) || undefined}
                            />
                        </div>
                    )}
                </div>
            </fieldset>

            {error && <p id="profile-source-error" className="field-error" role="alert">{error}</p>}
        </section>
    );
}
