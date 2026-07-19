import { useLocalModelStatus } from "./useLocalModelStatus";
import { useI18n } from "../../i18n/useI18n";

export function LocalModelStatus({ compact = false }) {
    const { t } = useI18n();
    const { status, refresh } = useLocalModelStatus();
    const state = status.loading ? "checking" : status.ready ? "ready" : status.available ? "missing" : "offline";
    const runtimeName = status.runtime === "llama.cpp" ? "llama.cpp" : t("model.runtime");
    const label = {
        checking: t("model.checking"),
        ready: `${runtimeName} · ${status.configured_model}`,
        missing: t("model.configuration"),
        offline: t("model.optional"),
    }[state];

    return (
        <div className={`model-status model-status--${state} ${compact ? "model-status--compact" : ""}`}>
            <span className="model-status__dot" aria-hidden="true" />
            <div className="model-status__copy">
                <strong>{label}</strong>
                {!compact && (
                    <span>
                        {status.ready
                            ? t("model.readyCopy")
                            : t("model.offlineCopy")}
                    </span>
                )}
            </div>
            {!compact && !status.loading && (
                <button type="button" className="icon-button" onClick={refresh} aria-label={t("model.recheck")}>
                    <i className="bi bi-arrow-clockwise" aria-hidden="true" />
                </button>
            )}
        </div>
    );
}
