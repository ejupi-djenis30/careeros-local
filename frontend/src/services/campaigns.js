import { ApiClient } from "../lib/client";

export const CampaignService = {
    preview(file, options = {}) {
        const form = new FormData();
        form.append("archive", file);
        return ApiClient.postMultipart("/campaigns/preview", form, {
            timeoutMs: 120_000,
            ...options,
        });
    },

    importArchive(file, { expectedFingerprint, name, profileDisplayName } = {}, options = {}) {
        const form = new FormData();
        form.append("archive", file);
        if (expectedFingerprint !== undefined && expectedFingerprint !== null) {
            form.append("expected_fingerprint", expectedFingerprint);
        }
        if (name !== undefined && name !== null) {
            form.append("name", name);
        }
        if (profileDisplayName !== undefined && profileDisplayName !== null) {
            form.append("profile_display_name", profileDisplayName);
        }
        return ApiClient.postMultipart("/campaigns/import", form, {
            timeoutMs: 300_000,
            ...options,
        });
    },

    list(options = {}) {
        return ApiClient.get("/campaigns", options.signal, options);
    },

    get(campaignId, { query, stage, priority, limit, offset, signal } = {}) {
        const searchParams = new URLSearchParams();
        if (query) searchParams.set("query", query);
        if (stage) searchParams.set("stage", stage);
        if (priority) searchParams.set("priority", priority);
        if (limit !== undefined && limit !== null) searchParams.set("limit", String(limit));
        if (offset !== undefined && offset !== null) searchParams.set("offset", String(offset));
        const queryStr = searchParams.toString();
        const path = `/campaigns/${encodeURIComponent(campaignId)}${queryStr ? `?${queryStr}` : ""}`;
        return ApiClient.get(path, signal, { signal });
    },

    applicationContext(applicationId, options = {}) {
        const path = `/applications/${encodeURIComponent(applicationId)}/campaign-context`;
        return ApiClient.get(path, options.signal, options);
    },

    downloadArtifact(campaignId, artifactId) {
        const path = `/campaigns/${encodeURIComponent(campaignId)}/artifacts/${encodeURIComponent(artifactId)}/download`;
        return ApiClient.download(path);
    },
};
