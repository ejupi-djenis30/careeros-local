import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { CAREEROS_MARK_URL } from "../../app/brand";
import { useI18n } from "../../i18n/useI18n";
import { LocalModelService } from "../../services/localModel";
import { ModelManager } from "./ModelManager";
import { useLocalModelStatus } from "./useLocalModelStatus";

const INITIAL_PROBE = { state: "idle", identity: "", result: null };

function modelIdentity(status) {
    return `${status.runtime || "local"}/${status.configured_model || "unknown"}`;
}

export function RequiredLocalAnalysis({ children }) {
    const { t } = useI18n();
    const { status, refresh } = useLocalModelStatus({ refreshMs: 2_000 });
    const [probe, setProbe] = useState(INITIAL_PROBE);
    const probeController = useRef(null);
    const probeInFlight = useRef(null);
    const probeSequence = useRef(0);
    const statusRef = useRef(status);
    const unlockRef = useRef(null);
    const wasUnlocked = useRef(false);
    const identity = modelIdentity(status);

    useEffect(() => {
        statusRef.current = status;
    }, [status]);

    const runProbe = useCallback(async () => {
        const currentStatus = statusRef.current;
        if (!currentStatus.ready) return;
        const identityAtStart = modelIdentity(currentStatus);
        if (probeInFlight.current?.identity === identityAtStart) return probeInFlight.current.promise;

        probeController.current?.abort();
        const controller = new AbortController();
        const sequence = probeSequence.current + 1;
        probeSequence.current = sequence;
        probeController.current = controller;
        setProbe({ state: "checking", identity: identityAtStart, result: null });

        const request = (async () => {
            try {
                const result = await LocalModelService.readiness({ signal: controller.signal });
                const latestStatus = statusRef.current;
                if (
                    controller.signal.aborted
                    || probeSequence.current !== sequence
                    || !latestStatus.ready
                    || modelIdentity(latestStatus) !== identityAtStart
                ) return;
                setProbe({ state: result.ready ? "ready" : "failed", identity: identityAtStart, result });
            } catch {
                const latestStatus = statusRef.current;
                if (
                    controller.signal.aborted
                    || probeSequence.current !== sequence
                    || !latestStatus.ready
                    || modelIdentity(latestStatus) !== identityAtStart
                ) return;
                setProbe({
                    state: "failed",
                    identity: identityAtStart,
                    result: { ready: false, error_code: "readiness_service_unreachable", checks: [] },
                });
            } finally {
                if (probeController.current === controller) probeController.current = null;
                if (probeInFlight.current?.sequence === sequence) probeInFlight.current = null;
            }
        })();
        probeInFlight.current = { identity: identityAtStart, sequence, promise: request };
        return request;
    }, []);

    useEffect(() => () => {
        probeSequence.current += 1;
        probeController.current?.abort();
    }, []);

    useEffect(() => {
        if (!status.ready) {
            probeSequence.current += 1;
            probeController.current?.abort();
            // Reset a previous pass when the runtime stops or the model is removed.
            // eslint-disable-next-line react-hooks/set-state-in-effect
            if (probe.state !== "idle") setProbe(INITIAL_PROBE);
            return;
        }
        if (probe.identity === identity && probe.state !== "idle") return;
        probeSequence.current += 1;
        probeController.current?.abort();
        // Discard a result tied to a replaced/reconfigured model before probing it.
        setProbe({ state: "idle", identity, result: null });
        void runProbe();
    }, [status.ready, identity, probe.identity, probe.state, runProbe]);

    const unlocked = status.ready && probe.state === "ready" && probe.identity === identity;
    useEffect(() => {
        if (unlocked && !wasUnlocked.current) {
            const frame = window.requestAnimationFrame(() => unlockRef.current?.focus());
            wasUnlocked.current = true;
            return () => window.cancelAnimationFrame(frame);
        }
        if (!unlocked) wasUnlocked.current = false;
        return undefined;
    }, [unlocked]);

    if (unlocked) {
        return (
            <div
                ref={unlockRef}
                className="analysis-unlocked"
                tabIndex="-1"
                aria-label={t("analysisGate.unlocked")}
            >
                {children}
            </div>
        );
    }

    const checking = status.loading || probe.state === "checking";
    const checks = probe.result?.checks || [];
    const assistiveStatus = status.loading
        ? t("analysisGate.sr.modelStatus")
        : !status.ready
            ? t("analysisGate.sr.setupRequired")
            : probe.state === "failed"
                ? t("analysisGate.sr.failed")
                : t("analysisGate.sr.readiness");
    return (
        <section className="analysis-gate" aria-labelledby="analysis-gate-title">
            <p className="visually-hidden" role="status" aria-live="polite">{assistiveStatus}</p>
            <div className="analysis-gate__intro">
                <img src={CAREEROS_MARK_URL} alt="" width="52" height="52" />
                <span className="section-kicker">{t("analysisGate.kicker")}</span>
                <h2 id="analysis-gate-title">{t("analysisGate.title")}</h2>
                <p>{t("analysisGate.copy")}</p>
                <div className="analysis-gate__boundary">
                    <i className="bi bi-shield-lock" aria-hidden="true" />
                    <span>{t("analysisGate.boundary")}</span>
                </div>
                <Link className="button button--ghost" to="/">{t("analysisGate.back")}</Link>
            </div>

            <div className="analysis-gate__setup">
                <div className="section-heading">
                    <div>
                        <span className="section-kicker">{t("analysisGate.step")}</span>
                        <h3>{checking ? t("analysisGate.checking") : t("analysisGate.setup")}</h3>
                    </div>
                    {checking && <span className="analysis-gate__spinner" role="status"><span className="visually-hidden">{t("analysisGate.checking")}</span></span>}
                </div>

                {!status.loading && !status.ready && <ModelManager status={status} onRefresh={refresh} />}

                {!status.loading && status.ready && probe.state === "failed" && (
                    <div className="analysis-diagnostics" role="alert">
                        <strong>{t("analysisGate.failed")}</strong>
                        <p>{t(`analysisGate.error.${probe.result?.error_code || "unknown"}`)}</p>
                        {checks.length > 0 && (
                            <ul>
                                {checks.map((check) => (
                                    <li key={check.code} className={check.status === "passed" ? "is-passed" : "is-failed"}>
                                        <i className={`bi ${check.status === "passed" ? "bi-check-circle" : "bi-x-circle"}`} aria-hidden="true" />
                                        <span>{t(`analysisGate.check.${check.code}`)}</span>
                                        <span className="visually-hidden">
                                            {check.status === "passed" ? t("analysisGate.checkPassed") : t("analysisGate.checkFailed")}
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        )}
                        <div className="button-cluster">
                            <button type="button" className="button button--primary" disabled={checking} onClick={runProbe}>{t("analysisGate.retry")}</button>
                            <button type="button" className="button button--ghost" disabled={checking} onClick={refresh}>{t("model.recheck")}</button>
                        </div>
                    </div>
                )}

                {!status.loading && status.ready && probe.state !== "failed" && (
                    <p className="analysis-gate__checking-copy">{t("analysisGate.checkingCopy")}</p>
                )}
            </div>
        </section>
    );
}
