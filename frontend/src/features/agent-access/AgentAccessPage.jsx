import { useEffect, useRef } from "react";

import { useI18n } from "../../i18n/useI18n";
import { AgentAccessConfigurations } from "./AgentAccessConfigurations";
import { AgentAccessDisclosure } from "./AgentAccessDisclosure";
import { AgentAccessTokenPanel } from "./AgentAccessTokenPanel";
import { AgentGrantForm } from "./AgentGrantForm";
import { AgentGrantList } from "./AgentGrantList";
import { useAgentAccessController } from "./useAgentAccessController";

export function AgentAccessPage() {
    const { language, t } = useI18n();
    const { state, actions } = useAgentAccessController(t);
    const issueButtonRef = useRef(null);
    const previouslyIssued = useRef(false);
    const locale = language === "it" ? "it-CH" : "en-GB";

    useEffect(() => {
        if (previouslyIssued.current && !state.issued) {
            issueButtonRef.current?.focus();
        }
        previouslyIssued.current = Boolean(state.issued);
    }, [state.issued]);

    return (
        <div className="agent-access-grid">
            <AgentAccessDisclosure activeCount={state.activeCount} t={t} />
            <AgentGrantForm
                state={state}
                actions={actions}
                issueButtonRef={issueButtonRef}
                t={t}
            />
            <AgentGrantList
                state={state}
                actions={actions}
                locale={locale}
                t={t}
            />
            <AgentAccessTokenPanel
                issued={state.issued}
                onCopyResult={actions.reportCopy}
                onDismiss={actions.dismissToken}
                t={t}
            />
            <AgentAccessConfigurations onCopyResult={actions.reportCopy} t={t} />
            {state.copyMessage && (
                <p className="visually-hidden" role="status">{state.copyMessage}</p>
            )}
            {state.revokeAnnouncement && (
                <p className="visually-hidden" role="status">
                    {state.revokeAnnouncement}
                </p>
            )}
        </div>
    );
}
