import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useI18n } from "../../i18n/useI18n";
import { ResumeService } from "../../services/resumes";
import { selectTemplatePreset } from "./resumeModel";
import { tTemplate } from "./templateMessages";
import "./TemplateGallery.css";

export function TemplateGallery({ studio, onClose }) {
    const { language } = useI18n();
    const tr = (key, vars) => tTemplate(key, language, vars);
    const [templates, setTemplates] = useState([]);
    const [filters, setFilters] = useState({ family: "all", locale: "all", layout: "all" });
    const [state, setState] = useState("loading");
    const [attempt, setAttempt] = useState(0);
    const [notice, setNotice] = useState("");
    const rootRef = useRef(null);
    const closeRef = useRef(onClose);
    useEffect(() => { closeRef.current = onClose; }, [onClose]);
    useEffect(() => {
        const controller = new AbortController();
        ResumeService.listTemplates({ signal: controller.signal, suppressGlobalError: true })
            .then((list) => {
                if (controller.signal.aborted) return;
                if (!Array.isArray(list) || !list.length) { setState("error"); return; }
                setTemplates(list); setState("ready");
            })
            .catch(() => { if (!controller.signal.aborted) setState("error"); });
        return () => controller.abort();
    }, [attempt]);
    useEffect(() => {
        const root = rootRef.current;
        const focused = document.activeElement;
        const overflow = document.body.style.overflow;
        const siblings = [...document.body.children].filter((element) => element !== root)
            .map((element) => ({ element, inert: element.inert }));
        siblings.forEach(({ element }) => { element.inert = true; });
        document.body.style.overflow = "hidden";
        root.querySelector("button")?.focus();
        const keydown = (event) => {
            if (event.key === "Escape") { event.preventDefault(); closeRef.current?.(); return; }
            if (event.key !== "Tab") return;
            const items = [...root.querySelectorAll("button:not([disabled]),select:not([disabled])")];
            const first = items[0], last = items.at(-1);
            if (!first) { event.preventDefault(); root.focus(); }
            else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
            else if (!root.contains(document.activeElement)) { event.preventDefault(); first.focus(); }
        };
        document.addEventListener("keydown", keydown);
        return () => {
            document.removeEventListener("keydown", keydown);
            siblings.forEach(({ element, inert }) => { element.inert = inert; });
            document.body.style.overflow = overflow;
            if (focused?.isConnected) focused.focus();
        };
    }, []);
    const visible = useMemo(() => templates.filter((preset) => Object.entries(filters)
        .every(([field, value]) => value === "all" || preset[field] === value)), [templates, filters]);
    const choose = (preset) => {
        const previous = templates.find((item) => item.id === studio.draft.template_id);
        studio.changeDraft(selectTemplatePreset(studio.draft, preset, previous));
        setNotice(tr("template.switchSuccess", { name: preset.name }));
    };
    return createPortal(
        <div className="cv-gallery-backdrop" ref={rootRef} role="dialog" aria-modal="true" aria-labelledby="template-gallery-title" tabIndex={-1}>
            <section className="cv-gallery-panel">
                <header className="cv-gallery-header"><div><h2 id="template-gallery-title">{tr("template.catalog")}</h2><p>{tr("template.catalogSubtitle")}</p></div>
                    <button type="button" className="button button--secondary" onClick={onClose} aria-label={tr("template.close")}><i className="bi bi-x-lg" aria-hidden="true" /></button>
                </header>
                <p>{tr("template.preservingNotice")}</p>
                {state === "loading" && <p role="status">{tr("template.loading")}</p>}
                {state === "error" && <div role="alert"><p>{tr("template.loadError")}</p><button type="button" className="button button--secondary" onClick={() => { setState("loading"); setAttempt((value) => value + 1); }}>{tr("template.retry")}</button></div>}
                {notice && <p role="status">{notice}</p>}
                {state === "ready" && <>
                    <div className="cv-gallery-filters">{[["family", "template.filterFamily"], ["locale", "template.filterLanguage"], ["layout", "template.filterLayout"]].map(([field, label]) =>
                        <label key={field}>{tr(label)}<select value={filters[field]} onChange={(event) => setFilters({ ...filters, [field]: event.target.value })}><option value="all">{tr("template.all")}</option>{[...new Set(templates.map((preset) => preset[field]))].map((value) => <option key={value} value={value}>{field === "locale" ? value.toUpperCase() : tr(`template.${field}.${value}`)}</option>)}</select></label>
                    )}</div>
                    {!visible.length && <p role="status">{tr("template.empty")}</p>}
                    <ul className="cv-gallery-grid">{visible.map((preset) => {
                        const active = studio.draft.template_id === preset.id;
                        return <li key={preset.id} className={active ? "is-active" : ""}>
                            <h3>{preset.name}</h3><p>{preset.locale.toUpperCase()} · {tr("template.budgetPages", { pages: preset.page_budget })}</p>
                            <div className={`cv-template-preview cv-template-preview--${preset.layout}`} aria-hidden="true" style={{ "--template-accent": preset.preview_style?.accent_color || "#243B53" }}><span /><div><b /><span /><span /><b /><span /><span /></div></div>
                            <p>{preset.description}</p><p>{tr(preset.photo_policy === "forbidden" ? "template.photoWarningATS" : "template.photoOptional")}</p>
                            <button type="button" className="button button--primary" disabled={active || Boolean(studio.busy)} aria-pressed={active} onClick={() => choose(preset)}>{tr(active ? "template.selected" : "template.select")}<span className="cv-sr-only">: {preset.name}</span></button>
                        </li>;
                    })}</ul>
                </>}
            </section>
        </div>, document.body,
    );
}
