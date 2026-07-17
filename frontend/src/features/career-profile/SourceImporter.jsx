import { useState } from "react";
import { CareerService } from "../../services/career";

export function SourceImporter() {
    const [file, setFile] = useState(null);
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const upload = async () => {
        if (!file) return;
        setLoading(true);
        setError("");
        try {
            setResult(await CareerService.uploadSource(file));
            setFile(null);
        } catch (uploadError) {
            setError(uploadError.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <section className="surface-section" aria-labelledby="sources-title">
            <div className="section-heading"><div><span className="section-kicker">Provenienza locale</span><h2 id="sources-title">Documenti sorgente</h2></div><span className="section-number">04</span></div>
            <p className="section-intro">Importa TXT, Markdown, PDF o DOCX. Il file, il testo estratto e l’hash restano nell’archivio locale; nessun upload esterno.</p>
            <div className="upload-row">
                <label className="file-picker"><i className="bi bi-file-earmark-arrow-up" /><span>{file ? file.name : "Scegli un documento"}</span><input type="file" accept=".txt,.md,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); }} /></label>
                <button type="button" className="button button--secondary" disabled={!file || loading} onClick={upload}>{loading ? "Importazione…" : "Importa localmente"}</button>
            </div>
            {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
            {result && <div className="source-result"><i className="bi bi-check2-circle" /><div><strong>{result.original_name}</strong><span>{result.extracted_characters.toLocaleString()} caratteri · SHA-256 {result.sha256.slice(0, 12)}…</span></div></div>}
        </section>
    );
}

