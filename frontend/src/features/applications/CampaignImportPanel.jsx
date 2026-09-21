import { useRef, useState } from "react";
import { useI18n } from "../../i18n/useI18n";
import { isDesktopShell, openCampaignWithNativeDialog } from "../../platform/desktop";
import { CampaignService } from "../../services/campaigns";
import { CampaignPreview } from "./CampaignPreview";

export function CampaignImportPanel({ onImported }) {
    const { t } = useI18n();
    const fileInputRef = useRef(null);
    const [file, setFile] = useState(null);
    const [preview, setPreview] = useState(null);
    const [campaignName, setCampaignName] = useState("");
    const [profileName, setProfileName] = useState({ value: "", isDirty: false });
    const [choosing, setChoosing] = useState(false);
    const [busy, setBusy] = useState(false);
    const [importing, setImporting] = useState(false);
    const [error, setError] = useState("");
    const [status, setStatus] = useState("");

    const processFile = (selectedFile) => {
        if (!selectedFile) return;
        setError("");
        setStatus("");
        setBusy(true);
        setFile(selectedFile);
        CampaignService.preview(selectedFile)
            .then((res) => {
                setPreview(res);
                setCampaignName(res.suggested_name || "");
                setProfileName({
                    value: res.suggested_profile_name || "",
                    isDirty: false,
                });
            })
            .catch(() => {
                setFile(null);
                setPreview(null);
                setError(t("campaign.errorPreview"));
            })
            .finally(() => {
                setBusy(false);
                if (fileInputRef.current) fileInputRef.current.value = "";
            });
    };

    const handleFileInputChange = (event) => {
        const selected = event.target.files?.[0];
        if (selected) {
            processFile(selected);
        }
    };

    const handleChooseClick = () => {
        if (choosing || busy) return;
        if (isDesktopShell()) {
            setChoosing(true);
            setError("");
            openCampaignWithNativeDialog({ title: t("campaign.openDialogTitle") })
                .then((selectedFile) => {
                    if (selectedFile) processFile(selectedFile);
                })
                .catch(() => {
                    setError(t("campaign.errorOpen"));
                })
                .finally(() => {
                    setChoosing(false);
                });
        } else {
            fileInputRef.current?.click();
        }
    };

    const handleImportConfirm = () => {
        if (!file || !preview || importing) return;
        setImporting(true);
        setError("");
        CampaignService.importArchive(file, {
            expectedFingerprint: preview.fingerprint,
            name: campaignName.trim() || undefined,
            profileDisplayName: preview.requires_profile_name ? profileName.value.trim() : undefined,
        })
            .then((result) => {
                setStatus(t("applications.campaignImported", { count: result.application_count }));
                setPreview(null);
                setFile(null);
                onImported?.(result);
            })
            .catch(() => {
                setError(t("campaign.errorImport"));
            })
            .finally(() => {
                setImporting(false);
            });
    };

    return (
        <div className="campaign-import-panel">
            <label htmlFor="campaign-archive-input" className="visually-hidden">
                {t("campaign.archiveInput")}
            </label>
            <input
                id="campaign-archive-input"
                ref={fileInputRef}
                type="file"
                accept=".zip,application/zip"
                tabIndex="-1"
                className="visually-hidden"
                onChange={handleFileInputChange}
            />

            <button
                type="button"
                className="button button--secondary"
                disabled={busy || choosing}
                onClick={handleChooseClick}
            >
                {t("campaign.chooseArchive")}
            </button>

            {error && (
                <div className="inline-alert inline-alert--danger" role="alert">
                    {error}
                </div>
            )}

            {status && (
                <div className="inline-alert inline-alert--success" role="status">
                    {status}
                </div>
            )}

            {preview && (
                <CampaignPreview
                    preview={preview}
                    name={campaignName}
                    onNameChange={setCampaignName}
                    profileName={profileName}
                    onProfileNameChange={(val) => setProfileName({ value: val, isDirty: true })}
                    onConfirm={handleImportConfirm}
                    importing={importing}
                />
            )}
        </div>
    );
}
