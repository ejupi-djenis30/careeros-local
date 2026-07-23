import { useI18n } from "../../../i18n/useI18n";
import { Dates, Input, Lines, Select, Textarea } from "./FieldControls";
import { SkillEvidence } from "./SkillEvidence";

const EMPLOYMENT_TYPES = ["permanent", "temporary", "contract", "freelance", "internship", "apprenticeship"];
const WORK_MODES = ["onsite", "hybrid", "remote"];
const SKILL_LEVELS = ["learning", "working", "advanced", "expert"];

function Experience({ payload, update, t }) {
    return <>
        <div className="form-grid form-grid--2">
            <Input label={t("factField.role")} value={payload.role || ""} onChange={(event) => update("role", event.target.value)} required />
            <Input label={t("factField.organization")} value={payload.organization || ""} onChange={(event) => update("organization", event.target.value)} required />
        </div>
        <div className="form-grid form-grid--3">
            <Select label={t("factField.employmentType")} value={payload.employment_type || "permanent"} onChange={(event) => update("employment_type", event.target.value)}>
                {EMPLOYMENT_TYPES.map((value) => <option key={value} value={value}>{t(`factField.employment.${value}`)}</option>)}
            </Select>
            <Input label={t("factField.industry")} value={payload.industry || ""} onChange={(event) => update("industry", event.target.value)} />
            <Select label={t("factField.workMode")} value={payload.work_mode || "hybrid"} onChange={(event) => update("work_mode", event.target.value)}>
                {WORK_MODES.map((value) => <option key={value} value={value}>{t(`factField.${value}`)}</option>)}
            </Select>
        </div>
        <div className="form-grid form-grid--2">
            <Input label={t("factField.location")} value={payload.location || ""} onChange={(event) => update("location", event.target.value)} />
            <Input label={t("factField.teamSize")} type="number" min="1" value={payload.team_size ?? ""} onChange={(event) => update("team_size", event.target.value ? Number(event.target.value) : null)} />
        </div>
        <Dates payload={payload} update={update} allowCurrent />
        <Textarea label={t("factField.description")} value={payload.description || ""} onChange={(event) => update("description", event.target.value)} />
        <div className="form-grid form-grid--2">
            <Lines label={t("factField.responsibilities")} value={payload.responsibilities} onChange={(value) => update("responsibilities", value)} />
            <Lines label={t("factField.achievements")} value={payload.achievements} onChange={(value) => update("achievements", value)} />
            <Lines label={t("factField.metrics")} value={payload.metrics} onChange={(value) => update("metrics", value)} />
            <Lines label={t("factField.technologies")} value={payload.technologies} onChange={(value) => update("technologies", value)} />
            <Lines label={t("factField.skills")} value={payload.skills} onChange={(value) => update("skills", value)} />
        </div>
    </>;
}

function Education({ payload, update, t }) {
    return <>
        <div className="form-grid form-grid--2">
            <Input label={t("factField.institution")} value={payload.institution || ""} onChange={(event) => update("institution", event.target.value)} required />
            <Input label={t("factField.qualification")} value={payload.qualification || ""} onChange={(event) => update("qualification", event.target.value)} required />
        </div>
        <div className="form-grid form-grid--2">
            <Input label={t("factField.field")} value={payload.field || ""} onChange={(event) => update("field", event.target.value)} />
            <Input label={t("factField.grade")} value={payload.grade || ""} onChange={(event) => update("grade", event.target.value)} />
        </div>
        <Dates payload={payload} update={update} />
        <Textarea label={t("factField.details")} value={payload.description || ""} onChange={(event) => update("description", event.target.value)} />
        <Input label={t("factField.thesis")} value={payload.thesis || ""} onChange={(event) => update("thesis", event.target.value)} />
        <div className="form-grid form-grid--2">
            <Lines label={t("factField.activities")} value={payload.activities} onChange={(value) => update("activities", value)} />
            <Lines label={t("factField.coursework")} value={payload.coursework} onChange={(value) => update("coursework", value)} />
        </div>
    </>;
}

function Project({ payload, update, t }) {
    return <>
        <div className="form-grid form-grid--2">
            <Input label={t("factField.name")} value={payload.name || ""} onChange={(event) => update("name", event.target.value)} required />
            <Input label={t("factField.role")} value={payload.role || ""} onChange={(event) => update("role", event.target.value)} />
        </div>
        <div className="form-grid form-grid--2">
            <Input label={t("factField.projectOrganization")} value={payload.organization || ""} onChange={(event) => update("organization", event.target.value)} />
            <Input label={t("factField.client")} value={payload.client || ""} onChange={(event) => update("client", event.target.value)} />
        </div>
        <Input label={t("factField.url")} type="url" value={payload.url || ""} onChange={(event) => update("url", event.target.value)} placeholder="https://" />
        <Dates payload={payload} update={update} />
        <Textarea label={t("factField.description")} value={payload.description || ""} onChange={(event) => update("description", event.target.value)} />
        <div className="form-grid form-grid--3">
            <Lines label={t("factField.achievements")} value={payload.achievements} onChange={(value) => update("achievements", value)} />
            <Lines label={t("factField.technologies")} value={payload.technologies} onChange={(value) => update("technologies", value)} />
            <Lines label={t("factField.skills")} value={payload.skills} onChange={(value) => update("skills", value)} />
        </div>
    </>;
}

function Skill({ payload, update, evidenceOptions, t }) {
    return <>
        <div className="form-grid form-grid--3">
            <Input label={t("factField.skill")} value={payload.name || ""} onChange={(event) => update("name", event.target.value)} required />
            <Input label={t("factField.skillCategory")} value={payload.category || ""} onChange={(event) => update("category", event.target.value)} />
            <Select label={t("factField.level")} value={payload.level || "working"} onChange={(event) => update("level", event.target.value)}>
                {SKILL_LEVELS.map((value) => <option key={value} value={value}>{t(`factField.level.${value}`)}</option>)}
            </Select>
            <Input label={t("factField.years")} type="number" min="0" max="80" step="0.5" value={payload.years ?? ""} onChange={(event) => update("years", event.target.value === "" ? null : Number(event.target.value))} />
            <Input label={t("factField.lastUsed")} type="date" value={payload.last_used_date || ""} onChange={(event) => update("last_used_date", event.target.value)} />
        </div>
        <SkillEvidence selectedIds={payload.evidence_fact_ids || []} options={evidenceOptions} onChange={(value) => update("evidence_fact_ids", value)} />
    </>;
}

function Simple({ type, payload, update, evidenceOptions, t }) {
    if (type === "skill") return <Skill payload={payload} update={update} evidenceOptions={evidenceOptions} t={t} />;
    if (type === "language") return <div className="form-grid form-grid--2"><Input label={t("factField.language")} value={payload.language || ""} onChange={(event) => update("language", event.target.value)} required /><Select label={t("factField.level")} value={payload.level || "B2"} onChange={(event) => update("level", event.target.value)}>{["A1", "A2", "B1", "B2", "C1", "C2", "native"].map((level) => <option key={level} value={level}>{level}</option>)}</Select></div>;
    if (type === "certification") return <><div className="form-grid form-grid--2"><Input label={t("factField.certification")} value={payload.name || ""} onChange={(event) => update("name", event.target.value)} required /><Input label={t("factField.issuer")} value={payload.issuer || ""} onChange={(event) => update("issuer", event.target.value)} /></div><div className="form-grid form-grid--2"><Input label={t("factField.issued")} type="date" value={payload.issued_on || ""} onChange={(event) => update("issued_on", event.target.value)} /><Input label={t("factField.expires")} type="date" value={payload.expires_on || ""} onChange={(event) => update("expires_on", event.target.value)} /></div><div className="form-grid form-grid--2"><Input label={t("factField.credentialId")} value={payload.credential_id || ""} onChange={(event) => update("credential_id", event.target.value)} /><Input label={t("factField.url")} type="url" value={payload.url || ""} onChange={(event) => update("url", event.target.value)} /></div></>;
    if (type === "achievement") return <><div className="form-grid form-grid--2"><Input label={t("factField.achievement")} value={payload.title || ""} onChange={(event) => update("title", event.target.value)} required /><Input label={t("factField.achievementDate")} type="date" value={payload.achieved_on || ""} onChange={(event) => update("achieved_on", event.target.value)} /></div><Textarea label={t("factField.description")} value={payload.description || ""} onChange={(event) => update("description", event.target.value)} /><Lines label={t("factField.achievementDetails")} value={payload.details} onChange={(value) => update("details", value)} /><div className="form-grid form-grid--3"><Input label={t("factField.value")} type="number" value={payload.metric_value ?? ""} onChange={(event) => update("metric_value", event.target.value === "" ? null : Number(event.target.value))} /><Input label={t("factField.unit")} value={payload.metric_unit || ""} onChange={(event) => update("metric_unit", event.target.value)} /><Input label={t("factField.context")} value={payload.context || ""} onChange={(event) => update("context", event.target.value)} /></div></>;
    if (type === "link") return <div className="form-grid form-grid--2"><Input label={t("factField.label")} value={payload.label || ""} onChange={(event) => update("label", event.target.value)} required /><Input label={t("factField.url")} type="url" value={payload.url || ""} onChange={(event) => update("url", event.target.value)} required /></div>;
    if (type === "publication") return <><Input label={t("factField.title")} value={payload.title || ""} onChange={(event) => update("title", event.target.value)} required /><div className="form-grid form-grid--2"><Input label={t("factField.publisher")} value={payload.publisher || ""} onChange={(event) => update("publisher", event.target.value)} /><Input label={t("factField.publicationDate")} type="date" value={payload.published_on || ""} onChange={(event) => update("published_on", event.target.value)} /></div><Input label={t("factField.url")} type="url" value={payload.url || ""} onChange={(event) => update("url", event.target.value)} /><Textarea label={t("factField.description")} value={payload.description || ""} onChange={(event) => update("description", event.target.value)} /></>;
    if (type === "award") return <><div className="form-grid form-grid--2"><Input label={t("factField.award")} value={payload.title || ""} onChange={(event) => update("title", event.target.value)} required /><Input label={t("factField.awardingBody")} value={payload.issuer || ""} onChange={(event) => update("issuer", event.target.value)} /></div><div className="form-grid form-grid--2"><Input label={t("factField.awardDate")} type="date" value={payload.awarded_on || ""} onChange={(event) => update("awarded_on", event.target.value)} /><Input label={t("factField.awardUrl")} type="url" value={payload.url || ""} onChange={(event) => update("url", event.target.value)} /></div><Textarea label={t("factField.awardDescription")} value={payload.description || ""} onChange={(event) => update("description", event.target.value)} /></>;
    if (type === "membership") return <><div className="form-grid form-grid--2"><Input label={t("factField.membership")} value={payload.organization || ""} onChange={(event) => update("organization", event.target.value)} required /><Input label={t("factField.membershipRole")} value={payload.role || ""} onChange={(event) => update("role", event.target.value)} required /></div><Dates payload={payload} update={update} allowCurrent /><Input label={t("factField.membershipUrl")} type="url" value={payload.url || ""} onChange={(event) => update("url", event.target.value)} /><Textarea label={t("factField.membershipDescription")} value={payload.description || ""} onChange={(event) => update("description", event.target.value)} /></>;
    if (type === "reference") return <><div className="inline-alert inline-alert--warning"><div><strong>{t("factField.sensitive")}</strong><span>{t("factField.referenceCopy")}</span></div></div><div className="form-grid form-grid--3"><Input label={t("factField.referenceName")} value={payload.name || ""} onChange={(event) => update("name", event.target.value)} required /><Input label={t("factField.relationship")} value={payload.relationship || ""} onChange={(event) => update("relationship", event.target.value)} required /><Input label={t("factField.referenceOrganization")} value={payload.organization || ""} onChange={(event) => update("organization", event.target.value)} /></div><div className="form-grid form-grid--2"><Input label={t("factField.referenceEmail")} type="email" value={payload.email || ""} onChange={(event) => update("email", event.target.value)} /><Input label={t("factField.referencePhone")} value={payload.phone || ""} onChange={(event) => update("phone", event.target.value)} /></div><label className="check-line check-line--field"><input type="checkbox" checked={Boolean(payload.permission_to_contact)} onChange={(event) => update("permission_to_contact", event.target.checked)} /> {t("factField.referencePermission")}</label><Textarea label={t("factField.referenceNotes")} value={payload.notes || ""} onChange={(event) => update("notes", event.target.value)} /></>;
    if (type === "portfolio") return <><div className="form-grid form-grid--2"><Input label={t("factField.portfolioName")} value={payload.name || ""} onChange={(event) => update("name", event.target.value)} required /><Input label={t("factField.portfolioUrl")} type="url" value={payload.url || ""} onChange={(event) => update("url", event.target.value)} required /></div><Textarea label={t("factField.portfolioDescription")} value={payload.description || ""} onChange={(event) => update("description", event.target.value)} /><Lines label={t("factField.portfolioSkills")} value={payload.skills} onChange={(value) => update("skills", value)} /></>;
    return <><Input label={t("factField.title")} value={payload.title || ""} onChange={(event) => update("title", event.target.value)} required /><Input label={t("factField.volunteeringOrganization")} value={payload.organization || ""} onChange={(event) => update("organization", event.target.value)} /><Dates payload={payload} update={update} /><Textarea label={t("factField.description")} value={payload.description || ""} onChange={(event) => update("description", event.target.value)} /><Lines label={t("factField.achievements")} value={payload.achievements} onChange={(value) => update("achievements", value)} /></>;
}

export function DetailedFactFields({ type, payload, update, evidenceOptions = [] }) {
    const { t } = useI18n();
    if (type === "experience") return <Experience payload={payload} update={update} t={t} />;
    if (type === "education") return <Education payload={payload} update={update} t={t} />;
    if (type === "project") return <Project payload={payload} update={update} t={t} />;
    return <Simple type={type} payload={payload} update={update} evidenceOptions={evidenceOptions} t={t} />;
}
