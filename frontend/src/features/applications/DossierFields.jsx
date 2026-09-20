import { useI18n } from "../../i18n/useI18n";
import { factTitle } from "../career-profile/profileModel";
import { LIMITS, requirementRow, answerRow, checklistRow } from "./dossierModel";

export function DossierFields({ requirements, setRequirements, coverLetter, setCoverLetter, answers, setAnswers, checklist, setChecklist, updateRequirement, toggleFact, updateAnswer, updateChecklist, removeRow, resumeMetadataStatus, linkedVersion, profileStatus, eligibleFacts, evidenceSelectionDisabled }) {
    const { t } = useI18n();
    return <>
                        <p id="dossier-limits" className="dossier-disclaimer">{t("dossier.limits")}</p>
                        <section className="dossier-builder" aria-labelledby="dossier-requirements-title">
                            <div className="dossier-builder__heading"><h4 id="dossier-requirements-title">{t("dossier.requirementsSection")}</h4><button type="button" className="button button--secondary" aria-describedby="dossier-limits" disabled={requirements.length >= LIMITS.requirements} onClick={() => setRequirements((current) => [...current, requirementRow()])}><i className="bi bi-plus-lg" aria-hidden="true" /> {t("dossier.addRequirement")}</button></div>
                            {requirements.map((row, index) => <fieldset className="dossier-row" key={row.id}>
                                <legend>{t("dossier.requirementNumber", { index: index + 1 })}</legend>
                                <label className="field-stack"><span>{t("dossier.requirementLabel", { index: index + 1 })}</span><textarea className="form-control" rows="2" value={row.requirement} onChange={(event) => updateRequirement(row.id, "requirement", event.target.value)} required maxLength="2000" placeholder={t("dossier.requirementPlaceholder")} /></label>
                                <fieldset className="dossier-evidence"><legend>{t("dossier.evidence")}</legend><small id={`dossier-evidence-limit-${row.id}`}>{t("dossier.evidenceLimit", { count: LIMITS.evidencePerRequirement })}</small>{resumeMetadataStatus === "loading" ? <p role="status">{t("dossier.resumeMetadataLoading")}</p> : resumeMetadataStatus === "error" ? null : !linkedVersion ? <p>{t("dossier.resumeMetadataMissing")}</p> : profileStatus === "loading" ? <p role="status">{t("dossier.loadingEvidence")}</p> : profileStatus === "ready" && eligibleFacts.length ? eligibleFacts.map((fact) => <label key={fact.id} className="check-line"><input type="checkbox" aria-label={t("dossier.evidenceFor", { fact: factTitle(fact), index: index + 1 })} aria-describedby={`dossier-evidence-limit-${row.id}`} checked={row.evidenceFactIds.includes(fact.id)} disabled={evidenceSelectionDisabled(row, fact.id)} onChange={() => toggleFact(row.id, fact.id)} /><span>{factTitle(fact)}</span><small>{t(`fact.type.${fact.fact_type}`)}</small></label>) : profileStatus === "ready" ? <p>{t("dossier.noEvidence")}</p> : null}</fieldset>
                                {requirements.length > 1 && <button type="button" className="button button--ghost dossier-row__remove" aria-label={t("dossier.removeRequirement", { index: index + 1 })} onClick={() => removeRow(setRequirements, row.id)}><i className="bi bi-trash3" aria-hidden="true" /> {t("dossier.remove")}</button>}
                            </fieldset>)}
                        </section>
                        <label className="field-stack"><span>{t("dossier.coverLetter")}</span><textarea className="form-control" rows="5" value={coverLetter} onChange={(event) => setCoverLetter(event.target.value)} maxLength={LIMITS.coverLetter} /></label>
                        <section className="dossier-builder" aria-labelledby="dossier-answers-title">
                            <div className="dossier-builder__heading"><h4 id="dossier-answers-title">{t("dossier.answersSection")}</h4><button type="button" className="button button--secondary" aria-describedby="dossier-limits" disabled={answers.length >= LIMITS.answers} onClick={() => setAnswers((current) => [...current, answerRow()])}><i className="bi bi-plus-lg" aria-hidden="true" /> {t("dossier.addAnswer")}</button></div>
                            {answers.map((row, index) => <fieldset className="dossier-row" key={row.id}>
                                <legend>{t("dossier.answerNumber", { index: index + 1 })}</legend>
                                <div className="form-grid form-grid--2"><label className="field-stack"><span>{t("dossier.questionLabel", { index: index + 1 })}</span><input className="form-control" value={row.question} onChange={(event) => updateAnswer(row.id, "question", event.target.value)} maxLength="1000" /></label><label className="field-stack"><span>{t("dossier.answerLabel", { index: index + 1 })}</span><textarea className="form-control" rows="2" value={row.answer} onChange={(event) => updateAnswer(row.id, "answer", event.target.value)} maxLength="20000" /></label></div>
                                {answers.length > 1 && <button type="button" className="button button--ghost dossier-row__remove" aria-label={t("dossier.removeAnswer", { index: index + 1 })} onClick={() => removeRow(setAnswers, row.id)}><i className="bi bi-trash3" aria-hidden="true" /> {t("dossier.remove")}</button>}
                            </fieldset>)}
                        </section>
                        <section className="dossier-builder" aria-labelledby="dossier-checklist-title">
                            <div className="dossier-builder__heading"><h4 id="dossier-checklist-title">{t("dossier.checklistSection")}</h4><button type="button" className="button button--secondary" aria-describedby="dossier-limits" disabled={checklist.length >= LIMITS.checklist} onClick={() => setChecklist((current) => [...current, checklistRow()])}><i className="bi bi-plus-lg" aria-hidden="true" /> {t("dossier.addChecklist")}</button></div>
                            {checklist.map((row, index) => <fieldset className="dossier-row dossier-checkline" key={row.id}>
                                <legend>{t("dossier.checklistNumber", { index: index + 1 })}</legend>
                                <label className="field-stack"><span>{t("dossier.checklistLabel", { index: index + 1 })}</span><input className="form-control" value={row.label} onChange={(event) => updateChecklist(row.id, "label", event.target.value)} maxLength="500" /></label><label className="check-line"><input type="checkbox" checked={row.completed} onChange={(event) => updateChecklist(row.id, "completed", event.target.checked)} /> {t("dossier.complete")}</label>
                                {checklist.length > 1 && <button type="button" className="button button--ghost dossier-row__remove" aria-label={t("dossier.removeChecklist", { index: index + 1 })} onClick={() => removeRow(setChecklist, row.id)}><i className="bi bi-trash3" aria-hidden="true" /> {t("dossier.remove")}</button>}
                            </fieldset>)}
                        </section>
    </>;
}
