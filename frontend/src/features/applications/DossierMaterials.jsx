import { useEffect, useState } from "react";
import { useI18n } from "../../i18n/useI18n";
import { ResumeService } from "../../services/resumes";
import { factTitle } from "../career-profile/profileModel";

function LetterOptions({ value, onChange, defaultTemplate }) {
    const { t } = useI18n();
    const [catalog, setCatalog] = useState([]);
    const [loadError, setLoadError] = useState(false);
    const [attempt, setAttempt] = useState(0);
    const enabled = Boolean(value);
    useEffect(() => {
        if (!enabled) return undefined;
        const controller = new AbortController();
        ResumeService.listTemplates({ signal: controller.signal, suppressGlobalError: true })
            .then((items) => {
                if (controller.signal.aborted) return;
                if (!Array.isArray(items) || !items.length) throw new Error("Invalid catalog");
                setCatalog(items); setLoadError(false);
            }).catch(() => { if (!controller.signal.aborted) setLoadError(true); });
        return () => controller.abort();
    }, [enabled, attempt]);
    const set = (field, next) => onChange({ ...value, [field]: next });
    return <fieldset className="dossier-row"><legend>{t("dossier.letterFiles")}</legend>
        <label className="check-line"><input type="checkbox" checked={enabled} onChange={(event) => onChange(event.target.checked ? {
            preset_id: defaultTemplate?.template_id || "software-en",
            template_version: defaultTemplate?.template_version || 1,
            locale: defaultTemplate?.locale || "en", formats: ["pdf", "docx"],
        } : null)} />{t("dossier.includeLetterFiles")}</label>
        {value && <>
            {loadError && <div role="alert"><p>{t("dossier.templateLoadError")}</p><button type="button" className="button button--ghost" onClick={() => setAttempt((n) => n + 1)}>{t("dossier.retryTemplates")}</button></div>}
            <label className="field-stack"><span>{t("dossier.letterTemplate")}</span><select className="form-select" value={`${value.preset_id}:${value.template_version}`} disabled={!catalog.length}
                onChange={(event) => { const preset = catalog.find((item) => `${item.id}:${item.version}` === event.target.value);
                    if (preset) onChange({ ...value, preset_id: preset.id, template_version: preset.version, locale: preset.locale }); }}>
                {!catalog.some((item) => item.id === value.preset_id && item.version === value.template_version)
                    && <option value={`${value.preset_id}:${value.template_version}`}>{value.preset_id} · {value.locale.toUpperCase()}</option>}
                {catalog.map((preset) => <option key={`${preset.id}:${preset.version}`} value={`${preset.id}:${preset.version}`}>{preset.name} · {preset.locale.toUpperCase()}</option>)}
            </select></label>
            <p className="dossier-disclaimer">{t("dossier.letterLanguage")}</p>
            <div className="form-grid form-grid--2">
                <label className="field-stack"><span>{t("dossier.letterRecipient")}</span><input className="form-control" value={value.recipient || ""} maxLength={500} onChange={(event) => set("recipient", event.target.value || null)} /></label>
                <label className="field-stack"><span>{t("dossier.letterDate")}</span><input className="form-control" type="date" value={value.date || ""} onChange={(event) => set("date", event.target.value || null)} /></label>
            </div>
            <label className="field-stack"><span>{t("dossier.letterSubject")}</span><input className="form-control" value={value.subject || ""} maxLength={500} onChange={(event) => set("subject", event.target.value || null)} /></label>
            <fieldset className="dossier-inline-options"><legend>{t("dossier.letterFormats")}</legend>{["pdf", "docx"].map((format) => <label key={format} className="check-line"><input type="checkbox" checked={value.formats.includes(format)}
                disabled={value.formats.length === 1 && value.formats.includes(format)} onChange={(event) => set("formats", event.target.checked ? [...value.formats, format] : value.formats.filter((item) => item !== format))} />{format.toUpperCase()}</label>)}</fieldset>
        </>}
    </fieldset>;
}

export function DossierMaterials({ letterOptions, setLetterOptions, emailDraft, setEmailDraft,
    evidenceClaims, setEvidenceClaims, generationProvenance, eligibleFacts, defaultTemplate }) {
    const { t } = useI18n();
    const updateEmail = (field, value) => setEmailDraft({ ...emailDraft, [field]: value });
    const attachmentOptions = ["resume.pdf", "resume.docx", ...(letterOptions?.formats || []).map((format) => `cover_letter.${format}`)];
    const available = [...new Set([...attachmentOptions, ...(emailDraft?.attachment_names || [])])];
    return <section className="dossier-materials" aria-labelledby="dossier-materials-title">
        <h4 id="dossier-materials-title">{t("dossier.materialsTitle")}</h4>
        <LetterOptions value={letterOptions} onChange={setLetterOptions} defaultTemplate={defaultTemplate} />
        <fieldset className="dossier-row"><legend>{t("dossier.emailTitle")}</legend>
            <label className="check-line"><input type="checkbox" checked={Boolean(emailDraft)} onChange={(event) => setEmailDraft(event.target.checked ? { mode: "short", recipient: null, subject: "", body: "", attachment_names: [] } : null)} />{t("dossier.includeEmail")}</label>
            {emailDraft && <>
                <div className="form-grid form-grid--2">
                    <label className="field-stack"><span>{t("dossier.emailMode")}</span><select className="form-select" value={emailDraft.mode} onChange={(event) => updateEmail("mode", event.target.value)}><option value="short">{t("dossier.emailShort")}</option><option value="motivational">{t("dossier.emailMotivational")}</option></select></label>
                    <label className="field-stack"><span>{t("dossier.emailRecipient")}</span><input className="form-control" type="email" maxLength={320} value={emailDraft.recipient || ""} onChange={(event) => updateEmail("recipient", event.target.value || null)} /></label>
                </div>
                <label className="field-stack"><span>{t("dossier.emailSubject")}</span><input className="form-control" maxLength={500} value={emailDraft.subject} onChange={(event) => updateEmail("subject", event.target.value)} /></label>
                <label className="field-stack"><span>{t("dossier.emailBody")}</span><textarea className="form-control" rows={6} maxLength={20000} value={emailDraft.body} onChange={(event) => updateEmail("body", event.target.value)} /></label>
                <fieldset className="dossier-inline-options"><legend>{t("dossier.emailAttachments")}</legend>{available.map((name) => <label className="check-line" key={name}><input type="checkbox" checked={emailDraft.attachment_names.includes(name)} onChange={(event) => updateEmail("attachment_names", event.target.checked ? [...emailDraft.attachment_names, name] : emailDraft.attachment_names.filter((item) => item !== name))} />{name}</label>)}</fieldset>
                <p className="dossier-disclaimer">{t("dossier.emailOffline")}</p>
            </>}
        </fieldset>
        {generationProvenance && <p className="dossier-disclaimer">{t("dossier.provenance", { source: generationProvenance.source })}</p>}
        {evidenceClaims.length > 0 && <fieldset className="dossier-row"><legend>{t("dossier.materialCitations")}</legend>
            <p>{t("dossier.materialCitationsCopy")}</p>
            {evidenceClaims.map((claim, index) => <div className="dossier-cited-claim" key={claim.id}>
                <label className="field-stack"><span>{t("dossier.citedText", { index: index + 1 })}</span><textarea className="form-control" value={claim.text} rows={2} maxLength={4000} onChange={(event) => setEvidenceClaims(evidenceClaims.map((item) => item.id === claim.id ? { ...item, text: event.target.value } : item))} /></label>
                <fieldset className="dossier-evidence"><legend>{t("dossier.citedFacts", { index: index + 1 })}</legend>{eligibleFacts.map((fact) => <label className="check-line" key={fact.id}><input type="checkbox" checked={claim.fact_ids.includes(fact.id)} aria-label={t("dossier.citedFactLabel", { index: index + 1, fact: factTitle(fact) })}
                    disabled={claim.fact_ids.includes(fact.id) ? claim.fact_ids.length === 1 : claim.fact_ids.length >= 20}
                    onChange={(event) => setEvidenceClaims(evidenceClaims.map((item) => item.id === claim.id ? { ...item, fact_ids: event.target.checked ? [...item.fact_ids, fact.id] : item.fact_ids.filter((id) => id !== fact.id) } : item))} />{factTitle(fact)}</label>)}</fieldset>
            </div>)}
        </fieldset>}
    </section>;
}
