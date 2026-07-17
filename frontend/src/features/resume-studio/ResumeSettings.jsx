export function ResumeSettings({ studio }) {
    const { profile, draft, busy, dirty, generationGoalId, autosaveState } = studio;
    const setTemplate = (template_kind) => {
        const canvas_document = draft.canvas_document && template_kind === "ats"
            ? { ...draft.canvas_document, style: { ...draft.canvas_document.style, columns: 1 } }
            : draft.canvas_document;
        studio.changeDraft({ template_kind, canvas_document, photo_asset_id: template_kind === "ats" ? null : draft.photo_asset_id });
    };
    const setInclusion = (key, enabled) => {
        const section_config = { ...draft.section_config, [key]: enabled };
        let canvas_document = draft.canvas_document;
        if (canvas_document) {
            const contact = [];
            if (section_config.include_email && profile.email) contact.push(profile.email);
            if (section_config.include_phone && profile.phone) contact.push(profile.phone);
            const location = profile.location?.name || profile.location?.city || Object.values(profile.location || {}).filter(Boolean).join(", ");
            if (section_config.include_location && location) contact.push(location);
            if (section_config.include_links) contact.push(...[profile.website, profile.linkedin, profile.github].filter(Boolean));
            canvas_document = {
                ...canvas_document,
                sections: canvas_document.sections.map((section) => {
                    if (section.kind === "summary") return { ...section, visible: section_config.include_summary };
                    if (section.kind !== "identity") return section;
                    return { ...section, blocks: section.blocks.map((block) => ({ ...block, content: { ...block.content, description: contact.join(" | ") }, manual_fields: (block.manual_fields || []).filter((field) => field !== "description") })) };
                }),
            };
        }
        studio.changeDraft({ section_config, canvas_document });
    };
    return (
        <section className="resume-settings surface-section">
            <div className="section-heading"><div><span className="section-kicker">Bozza {draft.id ? `· r${draft.revision}` : "nuova"}</span><h2>Contenuto e formato</h2><small aria-live="polite">{{ pending: "Autosave in attesa…", saving: "Salvataggio automatico…", saved: "Salvato automaticamente", error: "Autosave da riprovare", idle: "" }[autosaveState]}</small></div><div className="button-cluster">{draft.id && <button type="button" className="icon-button" onClick={studio.duplicate} disabled={Boolean(busy)} aria-label="Duplica CV"><i className="bi bi-copy" /></button>}{draft.id && <button type="button" className="icon-button icon-button--danger" onClick={studio.remove} disabled={Boolean(busy)} aria-label="Elimina CV"><i className="bi bi-trash3" /></button>}<button type="button" className="button button--secondary" onClick={studio.save} disabled={Boolean(busy) || (!dirty && Boolean(draft.id))}>{busy === "save" ? "Salvo…" : "Salva bozza"}</button><button type="button" className="button button--primary" onClick={studio.publish} disabled={Boolean(busy) || !studio.versionName.trim()}>{busy === "publish" ? "Verifica…" : "Pubblica PDF + DOCX"}</button></div></div>
            {draft.id && <button type="button" className={`profile-sync-banner ${profile.revision > draft.profile_revision ? "is-stale" : ""}`} onClick={studio.reviewSync} disabled={Boolean(busy)}><i className="bi bi-arrow-repeat" /><span><strong>{profile.revision > draft.profile_revision ? "Il Career Vault contiene dati più recenti" : "Controlla aggiornamenti dal profilo"}</strong><small>Rivedi e applica solo le sezioni desiderate.</small></span><span>Rivedi</span></button>}
            <div className="form-grid form-grid--2"><label className="field-stack"><span>Titolo interno</span><input className="form-control" value={draft.title} onChange={(event) => studio.changeDraft({ title: event.target.value })} maxLength={200} /></label><label className="field-stack"><span>Nome prossima versione</span><input className="form-control" value={studio.versionName} onChange={(event) => studio.setVersionName(event.target.value)} maxLength={200} /></label></div>
            <div className="resume-autofill"><div><i className="bi bi-magic" /><span><strong>Crea dal profilo</strong><small>Generazione deterministica sul dispositivo, utilizzabile anche senza modello.</small></span></div><label className="field-stack"><span>Obiettivo di carriera</span><select className="form-select" value={generationGoalId} onChange={(event) => studio.setGenerationGoalId(event.target.value)}><option value="">Profilo generale</option>{(profile.goals || []).map((goal) => <option key={goal.id} value={goal.id}>{goal.name}{goal.is_primary ? " · primario" : ""}</option>)}</select></label><button type="button" className="button button--primary" onClick={studio.generateFromProfile} disabled={Boolean(busy)}>{busy === "generate" ? "Creo…" : "Crea automaticamente"}</button></div>
            <fieldset className="template-picker"><legend>Template</legend><label className={draft.template_kind === "ats" ? "is-selected" : ""}><input type="radio" name="template" value="ats" checked={draft.template_kind === "ats"} onChange={() => setTemplate("ats")} /><i className="bi bi-file-text" /><span><strong>ATS</strong><small>Una colonna, testo estraibile, nessuna immagine</small></span></label><label className={draft.template_kind === "photo" ? "is-selected" : ""}><input type="radio" name="template" value="photo" checked={draft.template_kind === "photo"} onChange={() => setTemplate("photo")} /><i className="bi bi-person-bounding-box" /><span><strong>Con foto</strong><small>Layout sobrio, foto normalizzata e privata dei metadati</small></span></label></fieldset>
            {draft.template_kind === "photo" && <label className={`photo-upload ${draft.photo_asset_id ? "is-ready" : ""}`}><i className={`bi ${draft.photo_asset_id ? "bi-check-circle-fill" : "bi-camera"}`} /><span>{draft.photo_asset_id ? "Foto pronta · scegli per sostituire" : "Carica JPEG, PNG o WebP"}</span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => studio.uploadPhoto(event.target.files?.[0])} disabled={busy === "photo"} /></label>}
            <fieldset className="inclusion-options"><legend>Contatti inclusi</legend>{[["include_summary", "Sintesi"], ["include_email", "Email"], ["include_phone", "Telefono"], ["include_location", "Località"], ["include_links", "Link"]].map(([key, label]) => <label key={key} className="check-line"><input type="checkbox" checked={draft.section_config[key]} onChange={(event) => setInclusion(key, event.target.checked)} /> {label}</label>)}</fieldset>
        </section>
    );
}
