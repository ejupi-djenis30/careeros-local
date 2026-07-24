import { useI18n } from "../../i18n/useI18n";

function formatBytes(value, language) {
    if (value < 1024) return `${value} B`;
    const units = ["KB", "MB", "GB"];
    let amount = value;
    let unit = -1;
    do {
        amount /= 1024;
        unit += 1;
    } while (amount >= 1024 && unit < units.length - 1);
    return `${new Intl.NumberFormat(language, { maximumFractionDigits: 1 }).format(amount)} ${units[unit]}`;
}

export function BackupInspectionSummary({ inspection }) {
    const { language, t } = useI18n();
    const createdAt = new Intl.DateTimeFormat(language, {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(new Date(inspection.created_at));

    return (
        <section className="backup-inspection" aria-labelledby="backup-inspection-title">
            <div className="backup-inspection__heading">
                <div>
                    <span className="section-kicker">{t("data.inspection.kicker")}</span>
                    <h3 id="backup-inspection-title">{t("data.inspection.valid")}</h3>
                </div>
                <span className="backup-inspection__status">
                    <i className="bi bi-patch-check-fill" aria-hidden="true" />
                    {t("data.inspection.compatible")}
                </span>
            </div>
            <dl className="backup-inspection__facts">
                <div><dt>{t("data.inspection.format")}</dt><dd>v{inspection.format_version}</dd></div>
                <div><dt>{t("data.inspection.created")}</dt><dd>{createdAt}</dd></div>
                <div><dt>{t("data.inspection.archiveSize")}</dt><dd>{formatBytes(inspection.archive_bytes, language)}</dd></div>
                <div><dt>{t("data.inspection.records")}</dt><dd>{inspection.total_records}</dd></div>
                <div><dt>{t("data.inspection.files")}</dt><dd>{t("data.inspection.fileCount", { count: inspection.file_count, size: formatBytes(inspection.file_bytes, language) })}</dd></div>
                <div><dt>{t("data.inspection.digest")}</dt><dd><code>{inspection.archive_sha256}</code></dd></div>
            </dl>
            <div className="backup-inspection__details">
                <div>
                    <h4>{t("data.inspection.checks")}</h4>
                    <ul>
                        {inspection.verification_codes.map((code) => (
                            <li key={code}><i className="bi bi-check2" aria-hidden="true" />{t(`data.inspection.check.${code}`)}</li>
                        ))}
                    </ul>
                </div>
                <div>
                    <h4>{t("data.inspection.notes")}</h4>
                    <ul>
                        {inspection.warning_codes.map((code) => (
                            <li key={code}><i className="bi bi-info-circle" aria-hidden="true" />{t(`data.inspection.warning.${code}`)}</li>
                        ))}
                    </ul>
                </div>
            </div>
            <p className={`backup-inspection__restore ${inspection.restorable ? "is-ready" : ""}`}>
                <i className={`bi ${inspection.restorable ? "bi-unlock" : "bi-lock"}`} aria-hidden="true" />
                {inspection.restorable ? t("data.inspection.restoreReady") : t("data.inspection.restoreBlocked")}
            </p>
        </section>
    );
}
