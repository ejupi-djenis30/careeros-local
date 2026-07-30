import { useEffect, useMemo, useRef, useState } from "react";

import { AutomationService } from "../../services/automation";
import { errorMessage, grantState } from "./agentAccessModel";

export function useAgentAccessController(t) {
    const tokenRef = useRef(null);
    const issuedRef = useRef(null);
    const mountedRef = useRef(true);
    const pendingIssuanceRef = useRef(null);
    const [grants, setGrants] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [refreshRevision, setRefreshRevision] = useState(0);
    const [label, setLabel] = useState("");
    const [scopes, setScopes] = useState(["system:read"]);
    const [lifetimeDays, setLifetimeDays] = useState("30");
    const [password, setPassword] = useState("");
    const [creating, setCreating] = useState(false);
    const [issued, setIssued] = useState(null);
    const [issuedRemovalReason, setIssuedRemovalReason] = useState("");
    const [createMessage, setCreateMessage] = useState("");
    const [revokingId, setRevokingId] = useState("");
    const [revokePassword, setRevokePassword] = useState("");
    const [revokeBusy, setRevokeBusy] = useState(false);
    const [revokeMessage, setRevokeMessage] = useState("");
    const [revokeAnnouncement, setRevokeAnnouncement] = useState("");
    const [copyMessage, setCopyMessage] = useState("");
    const [now, setNow] = useState(() => Date.now());

    useEffect(() => {
        let active = true;
        const controller = new AbortController();
        AutomationService.listGrants({ signal: controller.signal })
            .then((items) => {
                if (active) setGrants(Array.isArray(items) ? items : []);
            })
            .catch((error) => {
                if (active) setLoadError(errorMessage(error, t, "agentAccess.error.load"));
            })
            .finally(() => {
                if (active) setLoading(false);
            });
        return () => {
            active = false;
            controller.abort();
        };
    }, [refreshRevision, t]);

    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
            tokenRef.current = null;
            issuedRef.current = null;
            if (pendingIssuanceRef.current) {
                pendingIssuanceRef.current.abandoned = true;
            }
        };
    }, []);

    useEffect(() => {
        const timer = window.setInterval(() => setNow(Date.now()), 60_000);
        return () => window.clearInterval(timer);
    }, []);

    const activeCount = useMemo(
        () => (loading || loadError
            ? null
            : grants.filter((grant) => grantState(grant, now) === "active").length),
        [grants, loadError, loading, now],
    );

    const toggleScope = (scope) => {
        setScopes((current) => current.includes(scope)
            ? current.filter((value) => value !== scope)
            : [...current, scope]);
    };

    const issueGrant = async (event) => {
        event.preventDefault();
        if (
            pendingIssuanceRef.current
            || creating
            || issued
            || loading
            || loadError
            || scopes.length === 0
        ) return;
        const submittedPassword = password;
        let resolveSettlement;
        const issuance = {
            abandoned: false,
            settled: new Promise((resolve) => {
                resolveSettlement = resolve;
            }),
        };
        pendingIssuanceRef.current = issuance;
        setCreating(true);
        setCreateMessage("");
        setIssuedRemovalReason("");
        try {
            const result = await AutomationService.issueGrant({
                label: label.trim(),
                scopes,
                lifetime_days: Number(lifetimeDays),
                password: submittedPassword,
            });
            if (!mountedRef.current || issuance.abandoned) {
                tokenRef.current = null;
                try {
                    await AutomationService.revokeGrant(
                        result.grant.id,
                        submittedPassword,
                    );
                } catch {
                    // The authenticated session is the last safe place to retry;
                    // the grant remains visible in the register if cleanup fails.
                }
                return;
            }
            tokenRef.current = result.token;
            issuedRef.current = result;
            setIssued(result);
            setGrants((current) => [
                result.grant,
                ...current.filter((grant) => grant.id !== result.grant.id),
            ]);
            setLabel("");
            setScopes(["system:read"]);
            setLifetimeDays("30");
        } catch (error) {
            if (mountedRef.current) {
                setCreateMessage(errorMessage(error, t, "agentAccess.error.issue"));
            }
        } finally {
            if (pendingIssuanceRef.current === issuance) {
                pendingIssuanceRef.current = null;
            }
            if (mountedRef.current) {
                setPassword("");
                setCreating(false);
            }
            resolveSettlement();
        }
    };

    const dismissToken = () => {
        tokenRef.current = null;
        issuedRef.current = null;
        setIssuedRemovalReason("dismissed");
        setIssued(null);
        setCopyMessage("");
    };

    const beginRevoke = (grantId) => {
        if (revokeBusy) return;
        setRevokingId(grantId);
        setRevokePassword("");
        setRevokeMessage("");
        setRevokeAnnouncement("");
    };

    const cancelRevoke = () => {
        setRevokingId("");
        setRevokePassword("");
        setRevokeMessage("");
    };

    const revokeGrant = async (event, grantId) => {
        event.preventDefault();
        setRevokeBusy(true);
        setRevokeMessage("");
        try {
            const result = await AutomationService.revokeGrant(grantId, revokePassword);
            setGrants((current) => current.map((grant) => (
                grant.id === result.id ? result : grant
            )));
            const discardedIssuedToken = issuedRef.current?.grant.id === result.id;
            if (discardedIssuedToken) {
                tokenRef.current = null;
                issuedRef.current = null;
                setIssuedRemovalReason("revoked");
                setIssued(null);
                setCopyMessage("");
            }
            cancelRevoke();
            setRevokeAnnouncement(t(
                discardedIssuedToken
                    ? "agentAccess.revokedIssuedAnnouncement"
                    : "agentAccess.revokedAnnouncement",
                {
                label: result.label,
                },
            ));
        } catch (error) {
            setRevokeMessage(errorMessage(error, t, "agentAccess.error.revoke"));
        } finally {
            setRevokePassword("");
            setRevokeBusy(false);
        }
    };

    const reportCopy = (success) => {
        setCopyMessage(t(success ? "agentAccess.copySuccess" : "agentAccess.copyFailed"));
    };

    const retryLoad = () => {
        setLoading(true);
        setLoadError("");
        setRefreshRevision((value) => value + 1);
    };

    const reportPendingNavigation = () => {
        setCreateMessage(t("agentAccess.pendingNavigation"));
    };

    const abandonPendingIssuance = () => {
        const pending = pendingIssuanceRef.current;
        if (!pending) return Promise.resolve();
        pending.abandoned = true;
        return pending.settled;
    };

    return {
        state: {
            activeCount,
            copyMessage,
            createMessage,
            creating,
            grants,
            issued,
            issuedRemovalReason,
            label,
            lifetimeDays,
            loadError,
            loading,
            now,
            password,
            revokeBusy,
            revokeAnnouncement,
            revokeMessage,
            revokePassword,
            revokingId,
            scopes,
        },
        actions: {
            abandonPendingIssuance,
            beginRevoke,
            cancelRevoke,
            dismissToken,
            issueGrant,
            reportCopy,
            reportPendingNavigation,
            retryLoad,
            revokeGrant,
            setLabel,
            setLifetimeDays,
            setPassword,
            setRevokePassword,
            toggleScope,
        },
    };
}
