import { useEffect, useRef } from "react";
import { useBlocker } from "react-router";

import { useI18n } from "../../i18n/useI18n";
import { CAREEROS_BEFORE_LOGOUT_EVENT } from "../../lib/events";
import { AgentAccessConfigurations } from "./AgentAccessConfigurations";
import { AgentAccessDisclosure } from "./AgentAccessDisclosure";
import { AgentAccessTokenPanel } from "./AgentAccessTokenPanel";
import { AgentGrantForm } from "./AgentGrantForm";
import { AgentGrantList } from "./AgentGrantList";
import { useAgentAccessController } from "./useAgentAccessController";

export function AgentAccessPage() {
    const { language, t } = useI18n();
    const { state, actions } = useAgentAccessController(t);
    const blocker = useBlocker(state.creating);
    const issueButtonRef = useRef(null);
    const previouslyIssued = useRef(false);
    const locale = language === "it" ? "it-CH" : "en-GB";

    useEffect(() => {
        if (
            previouslyIssued.current
            && !state.issued
            && state.issuedRemovalReason === "dismissed"
        ) {
            issueButtonRef.current?.focus();
        }
        previouslyIssued.current = Boolean(state.issued);
    }, [state.issued, state.issuedRemovalReason]);

    useEffect(() => {
        if (blocker.state !== "blocked") return;
        actions.reportPendingNavigation();
        blocker.reset();
    }, [actions, blocker]);

    useEffect(() => {
        if (!state.creating) return undefined;

        const preventUnload = (event) => {
            event.preventDefault();
            event.returnValue = "";
        };
        const preventLogout = (event) => {
            event.preventDefault();
            actions.reportPendingNavigation();
            if (
                event.detail?.force
                && typeof event.detail.waitUntil === "function"
            ) {
                event.detail.waitUntil(actions.abandonPendingIssuance());
            }
        };
        const preventLinkNavigation = (event) => {
            if (!(event.target instanceof Element)) return;
            const link = event.target.closest("a[href]");
            if (!link || event.defaultPrevented || link.target === "_blank" || link.hasAttribute("download")) {
                return;
            }
            const destination = new URL(link.href, window.location.href);
            if (!["http:", "https:"].includes(destination.protocol)) return;
            const sameDocumentFragment = (
                destination.origin === window.location.origin
                && destination.pathname === window.location.pathname
                && destination.search === window.location.search
                && Boolean(destination.hash)
            );
            if (sameDocumentFragment) return;
            event.preventDefault();
            actions.reportPendingNavigation();
        };

        window.addEventListener("beforeunload", preventUnload);
        window.addEventListener(CAREEROS_BEFORE_LOGOUT_EVENT, preventLogout);
        document.addEventListener("click", preventLinkNavigation);
        return () => {
            window.removeEventListener("beforeunload", preventUnload);
            window.removeEventListener(CAREEROS_BEFORE_LOGOUT_EVENT, preventLogout);
            document.removeEventListener("click", preventLinkNavigation);
        };
    }, [actions, state.creating]);

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
