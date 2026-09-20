import { useEffect, useState } from "react";
import { useI18n } from "../../i18n/useI18n";
import { CampaignService } from "../../services/campaigns";

export function CampaignMaterials({ applicationId }) {
    const { t } = useI18n();
    const [context, setContext] = useState(null);
    const [error, setError] = useState(false);
    const [downloadError, setDownloadError] = useState(false);
    const [notFound, setNotFound] = useState(false);
    const [retryCount, setRetryCount] = useState(0);
    const [prevAppId, setPrevAppId] = useState(applicationId);

    if (prevAppId !== applicationId) {
        setPrevAppId(applicationId);
        setContext(null);
        setError(false);
        setDownloadError(false);
        setNotFound(false);
    }

    useEffect(() => {
        if (!applicationId) return;
        const controller = new AbortController();

        CampaignService.applicationContext(applicationId, { signal: controller.signal })
            .then((data) => {
                if (controller.signal.aborted) return;
                setContext(data);
                setError(false);
                setNotFound(false);
            })
            .catch((err) => {
                if (controller.signal.aborted || err?.name === "AbortError") return;
                if (err?.status === 404) {
                    setNotFound(true);
                    setError(false);
                } else {
                    setError(true);
                    setNotFound(false);
                }
            });

        return () => controller.abort();
    }, [applicationId, retryCount]);

    if (notFound) return null;

    if (error) {
        return (
            <div className="inline-alert inline-alert--danger" role="alert">
                <span>{t("campaign.errorMaterials")}</span>
                <button
                    type="button"
                    className="button button--secondary"
                    onClick={() => {
                        setError(false);
                        setRetryCount((c) => c + 1);
                    }}
                >
                    {t("campaign.retryMaterials")}
                </button>
            </div>
        );
    }

    if (!context) return null;

    const handleDownload = async (artifact) => {
        setDownloadError(false);
        try {
            const res = await CampaignService.downloadArtifact(context.campaign_id, artifact.id);
            const url = URL.createObjectURL(res.blob);
            const anchor = document.createElement("a");
            anchor.href = url;
            anchor.download = res.filename || artifact.display_name || "artifact";
            anchor.click();
            URL.revokeObjectURL(url);
        } catch {
            setDownloadError(true);
        }
    };

    const artifactGroups = Object.entries(context.artifact_groups || {});

    return (
        <section className="campaign-materials" aria-labelledby="campaign-materials-heading">
            <h3 id="campaign-materials-heading">{t("campaign.materialsHeading")}</h3>
            <div className="campaign-materials__meta">
                <span>{context.campaign_name}</span>
                <span>{context.source_application_id}</span>
            </div>
            {context.tracker_record && (
                <div className="campaign-materials__tracker">
                    {Object.entries(context.tracker_record).map(([key, val]) => (
                        <div key={key}>
                            <span>{key}: </span>
                            <span>{String(val ?? "")}</span>
                        </div>
                    ))}
                </div>
            )}
            {downloadError && (
                <div className="inline-alert inline-alert--danger" role="alert">
                    {t("campaign.errorDownload")}
                </div>
            )}
            {artifactGroups.map(([category, items]) => {
                if (!items || items.length === 0) return null;
                const label = t(`campaign.category.${category}`) || category;
                return (
                    <div key={category} role="group" aria-label={label} className="campaign-materials__group">
                        <h4>{label}</h4>
                        <div className="campaign-materials__items">
                            {items.map((art) => (
                                <button
                                    key={art.id}
                                    type="button"
                                    className="button button--secondary"
                                    onClick={() => handleDownload(art)}
                                >
                                    {t("campaign.downloadArtifact", { name: art.display_name })}
                                </button>
                            ))}
                        </div>
                    </div>
                );
            })}
        </section>
    );
}
