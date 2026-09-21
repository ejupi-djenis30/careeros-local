import { useI18n } from "../../i18n/useI18n";

export function CampaignPreview({
    preview,
    name,
    onNameChange,
    profileName,
    onProfileNameChange,
    onConfirm,
    importing,
}) {
    const { t } = useI18n();

    const isImportDisabled =
        importing ||
        !name.trim() ||
        (preview.requires_profile_name && (!profileName.value.trim() || !profileName.isDirty));

    return (
        <section className="campaign-preview" aria-labelledby="campaign-preview-heading">
            <h3 id="campaign-preview-heading">{t("campaign.previewHeading")}</h3>
            <p className="campaign-preview__disclosure">{t("campaign.unencryptedDisclosure")}</p>

            <div className="campaign-preview__stats">
                <span className="badge">
                    {t("campaign.applicationCount", { count: preview.logical_application_count })}
                </span>
                <span className="badge">
                    {t("campaign.artifactCount", { count: preview.artifact_count })}
                </span>
                {preview.credential_rows_omitted > 0 && (
                    <span className="badge badge--warning">
                        {t("campaign.credentialRowsOmitted", { count: preview.credential_rows_omitted })}
                    </span>
                )}
            </div>

            <div className="campaign-preview__aggregates">
                <span>{t("campaign.trackerRows", { count: preview.tracker_rows ?? 0 })}</span>
                <span>{t("campaign.dossierCount", { count: preview.dossier_count ?? 0 })}</span>
                <span>{t("campaign.matchedCount", { count: preview.matched_count ?? 0 })}</span>
                <span>{t("campaign.trackerOnlyCount", { count: preview.tracker_only_count ?? 0 })}</span>
                <span>{t("campaign.dossierOnlyCount", { count: preview.dossier_only_count ?? 0 })}</span>
            </div>

            {preview.status_counts && Object.keys(preview.status_counts).length > 0 && (
                <div className="campaign-preview__status-counts">
                    <h4>{t("campaign.sourceStatuses")}</h4>
                    <div className="campaign-preview__status-list">
                        {Object.entries(preview.status_counts).map(([status, count]) => (
                            <span key={status} className="badge">
                                {status}: {count}
                            </span>
                        ))}
                    </div>
                </div>
            )}

            <div className="form-grid form-grid--2">
                <label className="field-stack">
                    <span>{t("campaign.name")}</span>
                    <input
                        className="form-control"
                        type="text"
                        value={name}
                        maxLength="160"
                        onChange={(e) => onNameChange(e.target.value)}
                    />
                </label>
                {preview.requires_profile_name && (
                    <label className="field-stack">
                        <span>{t("campaign.profileName")}</span>
                        <input
                            className="form-control"
                            type="text"
                            value={profileName.value}
                            maxLength="160"
                            required
                            onChange={(e) => onProfileNameChange(e.target.value)}
                        />
                    </label>
                )}
            </div>

            <div className="campaign-preview__actions">
                <button
                    type="button"
                    className="button button--primary"
                    disabled={isImportDisabled}
                    aria-label={t("campaign.importAction", { count: preview.logical_application_count })}
                    onClick={onConfirm}
                >
                    {importing
                        ? t("campaign.importing")
                        : t("campaign.importButton")}
                </button>
            </div>
        </section>
    );
}
