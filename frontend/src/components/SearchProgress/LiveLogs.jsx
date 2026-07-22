import React from "react";
import { useI18n } from "../../i18n/useI18n";

function releaseLogMessage(message) {
    if (typeof message !== "string" || message.startsWith("[LLM_DEBUG]")) return null;
    return message.replace(/\bprofile_id\s*[=:]\s*\S+/gi, "").replace(/\s{2,}/g, " ").trim();
}

export function LiveLogs({ log, logEndRef }) {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    return (
        <div className="col-lg-7 d-flex flex-column h-100">
            <div className="glass-panel p-0 h-100 overflow-hidden d-flex flex-column border-0 shadow-lg">
                <div className="p-2 border-bottom border-white-10 bg-black d-flex justify-content-between align-items-center">
                    <div className="d-flex align-items-center px-2">
                        <i className="bi bi-terminal-fill text-secondary me-2"></i>
                        <span className="text-secondary x-small fw-bold font-monospace">{t("searchProgress.logOutput")}</span>
                    </div>
                </div>
                <div className="flex-grow-1 overflow-auto bg-black p-3 custom-scrollbar" style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.8rem' }}>
                    {log?.some((entry) => releaseLogMessage(entry.message)) ? (
                        log.map((entry, i) => {
                            const message = releaseLogMessage(entry.message);
                            if (!message) return null;
                            return (
                                <div key={i} className="mb-1 d-flex align-items-start">
                                    <span className="text-secondary opacity-50 me-2 select-none" style={{ minWidth: '70px' }}>
                                        [{new Date(entry.time).toLocaleTimeString(locale, { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}]
                                    </span>

                                    <span className="text-light text-break">{message}</span>
                                </div>
                            );
                        })
                    ) : (
                        <div className="h-100 d-flex align-items-center justify-content-center text-secondary opacity-25">
                            <span>{t("searchProgress.waitingStream")}</span>
                        </div>
                    )}
                    <div ref={logEndRef} />
                </div>
            </div>
        </div>
    );
}
