import { useEffect, useRef, useState } from "react";

export function CopyButton({ value, label, copiedLabel, onResult }) {
    const [copied, setCopied] = useState(false);
    const resetTimer = useRef(null);

    useEffect(() => () => {
        if (resetTimer.current) window.clearTimeout(resetTimer.current);
    }, []);

    const copy = async () => {
        if (!navigator.clipboard?.writeText) {
            onResult(false);
            return;
        }
        try {
            await navigator.clipboard.writeText(value);
            setCopied(true);
            onResult(true);
            if (resetTimer.current) window.clearTimeout(resetTimer.current);
            resetTimer.current = window.setTimeout(() => {
                resetTimer.current = null;
                setCopied(false);
            }, 1800);
        } catch {
            onResult(false);
        }
    };

    return (
        <button type="button" className="button button--secondary button--small" onClick={copy}>
            <i className={`bi ${copied ? "bi-check-lg" : "bi-copy"}`} aria-hidden="true" />
            {copied ? copiedLabel : label}
        </button>
    );
}

export function ConfigurationCard({ title, copy, snippet, t, onCopyResult }) {
    return (
        <article className="agent-config-card">
            <div>
                <h3>{title}</h3>
                <p>{copy}</p>
            </div>
            <pre tabIndex="0"><code>{snippet}</code></pre>
            <CopyButton
                value={snippet}
                label={t("agentAccess.copyConfig")}
                copiedLabel={t("agentAccess.copied")}
                onResult={onCopyResult}
            />
        </article>
    );
}
