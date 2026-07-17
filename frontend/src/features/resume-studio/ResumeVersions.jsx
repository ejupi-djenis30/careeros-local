import { saveBlob } from "../../lib/download";
import { ResumeService } from "../../services/resumes";

export function ResumeVersions({ versions, onError }) {
    const download = async (artifact) => {
        try {
            saveBlob(await ResumeService.downloadArtifact(artifact.id));
        } catch (error) {
            onError(error.message);
        }
    };

    if (!versions?.length) return <div className="empty-inline"><p>Nessuna versione pubblicata. La pubblicazione genera e verifica PDF e DOCX.</p></div>;
    return (
        <div className="version-list">
            {[...versions].reverse().map((version) => (
                <article key={version.id} className="version-card">
                    <div className="version-card__meta"><span>v{version.semantic_version}</span><strong>{new Date(version.published_at).toLocaleString("it-IT")}</strong><small>Profilo r{version.profile_revision} · {version.quality_report.page_count} pag.</small></div>
                    <div className="quality-pass"><i className="bi bi-patch-check-fill" /><span>Quality gate superato</span></div>
                    <div className="button-cluster">{version.artifacts.map((artifact) => <button key={artifact.id} type="button" className="button button--secondary" onClick={() => download(artifact)}><i className={`bi ${artifact.format === "pdf" ? "bi-filetype-pdf" : "bi-filetype-docx"}`} /> {artifact.format.toUpperCase()} <small>{Math.ceil(artifact.byte_size / 1024)} KB</small></button>)}</div>
                </article>
            ))}
        </div>
    );
}

