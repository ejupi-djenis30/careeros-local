import { useI18n } from "../../i18n/useI18n";
import { publishedFiles } from "./dossierModel";

export function DossierArtifacts({ application, busy, onDownload }) {
    const { t } = useI18n();
    if (!application.dossiers?.length) return null;
    return <div className="dossier-versions">{application.dossiers.map((dossier) => <article key={dossier.id}>
        <div><strong>{t("dossier.version", { version: dossier.version_number })}</strong>
            <span>{t("dossier.requirements", { count: dossier.requirement_count })} · {t("dossier.checklist", { complete: dossier.completed_checklist, total: dossier.checklist_total })}</span>
            <code>{dossier.manifest_sha256.slice(0, 12)}</code>
        </div>
        <div className="dossier-artifact-actions">
            <button type="button" className="button button--secondary" disabled={busy} onClick={() => onDownload(dossier)}>{t("dossier.download")}</button>
            {publishedFiles(application, dossier.id).map((filename) => <button key={filename} type="button"
                className="button button--ghost" disabled={busy}
                aria-label={`${t("dossier.downloadFile", { filename })} · ${t("dossier.version", { version: dossier.version_number })}`}
                onClick={() => onDownload(dossier, filename)}>{t("dossier.downloadFile", { filename })}</button>)}
        </div>
    </article>)}</div>;
}
