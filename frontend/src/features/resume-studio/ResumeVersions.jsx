import { useState } from "react";
import { saveBlob } from "../../lib/download";
import { ResumeService } from "../../services/resumes";

export function ResumeVersions({ versions, comparison, busy, onCompare, onRestore, onError }) {
    const [selected, setSelected] = useState([]);
    const download = async (artifact) => {
        try {
            saveBlob(await ResumeService.downloadArtifact(artifact.id));
        } catch (error) {
            onError(error.message);
        }
    };
    const toggle = (versionId, enabled) => setSelected((current) => {
        if (!enabled) return current.filter((item) => item !== versionId);
        return current.includes(versionId) ? current : [...current.slice(-1), versionId];
    });

    if (!versions?.length) return <div className="empty-inline"><p>Nessuna versione pubblicata. La pubblicazione genera e verifica PDF e DOCX.</p></div>;
    return (
        <div className="version-list">
            {versions.length > 1 && <button type="button" className="button button--secondary" disabled={selected.length !== 2 || Boolean(busy)} onClick={() => onCompare(selected)}>Confronta 2 versioni</button>}
            {comparison && <section className="version-comparison" aria-label="Confronto versioni"><strong>{comparison.left_name} → {comparison.right_name}</strong><span>Profilo: {comparison.profile_changes.join(", ") || "invariato"}</span><span>CV: {comparison.resume_changes.join(", ") || "invariato"}</span><span>Fatti +{comparison.added_fact_ids.length} / −{comparison.removed_fact_ids.length} / modificati {comparison.changed_fact_ids.length}</span></section>}
            {[...versions].reverse().map((version) => (
                <article key={version.id} className="version-card">
                    <label className="check-line"><input type="checkbox" checked={selected.includes(version.id)} onChange={(event) => toggle(version.id, event.target.checked)} aria-label={`Seleziona versione ${version.name}`} /><span>Confronta</span></label>
                    <div className="version-card__meta"><span>v{version.semantic_version}</span><strong>{version.name}</strong><small>{new Date(version.published_at).toLocaleString("it-IT")} · Profilo r{version.profile_revision} · {version.quality_report.page_count} pag.</small></div>
                    <div className="quality-pass"><i className="bi bi-patch-check-fill" /><span>Quality gate superato</span></div>
                    <div className="button-cluster">{version.artifacts.map((artifact) => <button key={artifact.id} type="button" className="button button--secondary" onClick={() => download(artifact)}><i className={`bi ${artifact.format === "pdf" ? "bi-filetype-pdf" : "bi-filetype-docx"}`} /> {artifact.format.toUpperCase()} <small>{Math.ceil(artifact.byte_size / 1024)} KB</small></button>)}<button type="button" className="button button--ghost" disabled={Boolean(busy)} onClick={() => onRestore(version)}>Ripristina nella bozza</button></div>
                </article>
            ))}
        </div>
    );
}
