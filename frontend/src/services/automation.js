import { ApiClient } from "../lib/client";

export const AutomationService = {
    listGrants({ signal } = {}) {
        return ApiClient.get("/automation/grants", signal, { suppressGlobalError: true });
    },
    issueGrant(payload, { signal } = {}) {
        return ApiClient.post("/automation/grants", payload, {
            signal,
            suppressGlobalError: true,
        });
    },
    revokeGrant(grantId, password, { signal } = {}) {
        return ApiClient.post(
            `/automation/grants/${encodeURIComponent(grantId)}/revoke`,
            { password },
            { signal, suppressGlobalError: true },
        );
    },
};
