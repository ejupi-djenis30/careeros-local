import { useState } from "react";
import { CareerService } from "../../services/career";

function candidateLabel(candidate) {
    return candidate.payload?.name || candidate.payload?.title || candidate.fact_type;
}

export function SourceImporter({ onAcceptCandidates = () => 0 }) {
    const [file, setFile] = useState(null);
    const [result, setResult] = useState(null);
    const [selected, setSelected] = useState(new Set());
    const [acceptedCount, setAcceptedCount] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const upload = async () => {
        if (!file) return;
        setLoading(true);
        setError("");
        try {
            const imported = await CareerService.uploadSource(file);
            setResult(imported);
            setSelected(new Set());
            setAcceptedCount(0);
            setFile(null);
        } catch (uploadError) {
            setError(uploadError.message);
        } finally {
            setLoading(false);
        }
    };

    const toggle = (candidateId) => {
        setSelected((current) => {
            const next = new Set(current);
            if (next.has(candidateId)) next.delete(candidateId);
            else next.add(candidateId);
            return next;
        });
    };

    const accept = () => {
        const candidates = (result?.candidates || []).filter((item) => selected.has(item.candidate_id));
        const count = onAcceptCandidates(result, candidates);
        setAcceptedCount(Number.isFinite(count) ? count : candidates.length);
        setSelected(new Set());
    };

    return (
        <section className="surface-section" aria-labelledby="sources-title">
            <div className="section-heading"><div><span className="section-kicker">Provenienza locale</span><h2 id="sources-title">Documenti sorgente</h2></div><span className="section-number">04</span></div>
            <p className="section-intro">Importa TXT, Markdown, PDF o DOCX. Il file, il testo estratto e l’hash restano nell’archivio locale; nessun upload esterno.</p>
            <div className="upload-row">
                <label className="file-picker"><i className="bi bi-file-earmark-arrow-up" aria-hidden="true" /><span>{file ? file.name : "Scegli un documento"}</span><input aria-label="Documento sorgente" type="file" accept=".txt,.md,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => { setFile(event.target.files?.[0] || null); setResult(null); setAcceptedCount(0); }} /></label>
                <button type="button" className="button button--secondary" disabled={!file || loading} onClick={upload}>{loading ? "Importazione…" : "Importa localmente"}</button>
            </div>
            {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
            {result && (
                <div className="source-review">
                    <div className="source-result"><i className="bi bi-check2-circle" aria-hidden="true" /><div><strong>{result.original_name}</strong><span>{result.extracted_characters.toLocaleString()} caratteri · SHA-256 {result.sha256.slice(0, 12)}…</span></div></div>
                    <details className="source-preview"><summary>Anteprima del testo estratto</summary><pre>{result.text_preview || "Nessun testo estraibile."}</pre></details>
                    <div className="source-candidates" aria-labelledby="source-candidates-title">
                        <div><strong id="source-candidates-title">Candidati da revisionare</strong><span>Seleziona solo fatti corretti. Saranno salvati come importati, non confermati.</span></div>
                        {(result.candidates || []).length === 0 ? <p>Nessun candidato affidabile rilevato automaticamente.</p> : result.candidates.map((candidate) => (
                            <label className="source-candidate" key={candidate.candidate_id}>
                                <input type="checkbox" checked={selected.has(candidate.candidate_id)} onChange={() => toggle(candidate.candidate_id)} />
                                <span><strong>{candidateLabel(candidate)}</strong><small>{candidate.fact_type} · confidenza {Math.round(candidate.confidence * 100)}% · {candidate.source_locator}</small><em>{candidate.excerpt}</em></span>
                            </label>
                        ))}
                        {(result.candidates || []).length > 0 && <button type="button" className="button button--primary" disabled={selected.size === 0} onClick={accept}>Accetta {selected.size} candidati selezionati</button>}
                        {acceptedCount > 0 && <p className="source-accepted" role="status">{acceptedCount} {acceptedCount === 1 ? "fatto aggiunto" : "fatti aggiunti"} al profilo. Salva il Career Vault per conservarli.</p>}
                    </div>
                </div>
            )}
        </section>
    );
}
