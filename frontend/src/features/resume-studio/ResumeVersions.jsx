import { useState } from "react";
import { saveBlob } from "../../lib/download";
import { ResumeService } from "../../services/resumes";
import { useI18n } from "../../i18n/useI18n";

export function ResumeVersions({ versions, comparison, busy, onCompare, onRestore, onError }) {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    const [selected, setSelected] = useState([]);
    const download = async (artifact) => {
        try {
            saveBlob(await ResumeService.downloadArtifact(artifact.id));
        } catch (error) {
            onError({ message: error.message });
        }
    };
    const toggle = (versionId, enabled) => setSelected((current) => {
        if (!enabled) return current.filter((item) => item !== versionId);
        return current.includes(versionId) ? current : [...current.slice(-1), versionId];
    });

    if (!versions?.length) return <div className="empty-inline"><p>{t("resumeVersions.empty")}</p></div>;
    return (
        <div className="version-list">
            {versions.length > 1 && <button type="button" className="button button--secondary" disabled={selected.length !== 2 || Boolean(busy)} onClick={() => onCompare(selected)}>{t("resumeVersions.compareTwo")}</button>}
            {comparison && <section className="version-comparison" aria-label={t("resumeVersions.comparison")}><strong>{comparison.left_name} → {comparison.right_name}</strong><span>{t("resumeVersions.profile")}: {comparison.profile_changes.join(", ") || t("resumeVersions.unchanged")}</span><span>{t("resumeVersions.resume")}: {comparison.resume_changes.join(", ") || t("resumeVersions.unchanged")}</span><span>{t("resumeVersions.factsChanged", { added: comparison.added_fact_ids.length, removed: comparison.removed_fact_ids.length, changed: comparison.changed_fact_ids.length })}</span></section>}
            {[...versions].reverse().map((version) => (
                <article key={version.id} className="version-card">
                    <label className="check-line"><input type="checkbox" checked={selected.includes(version.id)} onChange={(event) => toggle(version.id, event.target.checked)} aria-label={t("resumeVersions.select", { name: version.name })} /><span>{t("resumeVersions.compare")}</span></label>
                    <div className="version-card__meta"><span>v{version.semantic_version}</span><strong>{version.name}</strong><small>{new Date(version.published_at).toLocaleString(locale)} · {t("resumeVersions.meta", { revision: version.profile_revision, pages: version.quality_report.page_count })}</small></div>
                    <div className="quality-pass"><i className="bi bi-patch-check-fill" /><span>{t("resumeVersions.qualityPassed")}</span></div>
                    <div className="button-cluster">{version.artifacts.map((artifact) => <button key={artifact.id} type="button" className="button button--secondary" onClick={() => download(artifact)}><i className={`bi ${artifact.format === "pdf" ? "bi-filetype-pdf" : "bi-filetype-docx"}`} /> {artifact.format.toUpperCase()} <small>{Math.ceil(artifact.byte_size / 1024)} KB</small></button>)}<button type="button" className="button button--ghost" disabled={Boolean(busy)} onClick={() => onRestore(version)}>{t("resumeVersions.restore")}</button></div>
                </article>
            ))}
        </div>
    );
}
