import { useLocalModelStatus } from "./useLocalModelStatus";

export function LocalModelStatus({ compact = false }) {
    const { status, refresh } = useLocalModelStatus();
    const state = status.loading ? "checking" : status.ready ? "ready" : status.available ? "missing" : "offline";
    const runtimeName = status.runtime === "llama.cpp" ? "llama.cpp" : "runtime locale";
    const label = {
        checking: "Verifica modello…",
        ready: `${runtimeName} · ${status.configured_model}`,
        missing: "Configurazione modello necessaria",
        offline: "Runtime locale non disponibile",
    }[state];

    return (
        <div className={`model-status model-status--${state} ${compact ? "model-status--compact" : ""}`}>
            <span className="model-status__dot" aria-hidden="true" />
            <div className="model-status__copy">
                <strong>{label}</strong>
                {!compact && (
                    <span>
                        {status.ready
                            ? "Inferenza disponibile solo su questo dispositivo"
                            : "Ricerca e archivio restano disponibili senza modello"}
                    </span>
                )}
            </div>
            {!compact && !status.loading && (
                <button type="button" className="icon-button" onClick={refresh} aria-label="Ricontrolla modello locale">
                    <i className="bi bi-arrow-clockwise" aria-hidden="true" />
                </button>
            )}
        </div>
    );
}
