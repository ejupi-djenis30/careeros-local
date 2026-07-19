import { useI18n } from "../../i18n/useI18n";

function Field({ label, children, hint }) {
    return (
        <label className="field-stack">
            <span>{label}</span>
            {children}
            {hint && <small>{hint}</small>}
        </label>
    );
}

export function IdentityEditor({ profile, onChange }) {
    const { t } = useI18n();
    const update = (field, value) => onChange({ ...profile, [field]: value });
    const locationName = profile.location?.name || profile.location?.city || "";

    return (
        <section className="surface-section" aria-labelledby="identity-title">
            <div className="section-heading">
                <div><span className="section-kicker">{t("profile.identityKicker")}</span><h2 id="identity-title">{t("profile.identityTitle")}</h2></div>
                <span className="section-number">01</span>
            </div>
            <div className="form-grid form-grid--2">
                <Field label={t("profile.displayName")}><input className="form-control" value={profile.display_name} onChange={(e) => update("display_name", e.target.value)} required maxLength={160} /></Field>
                <Field label={t("profile.professionalTitle")}><input className="form-control" value={profile.headline} onChange={(e) => update("headline", e.target.value)} placeholder={t("profile.professionalTitlePlaceholder")} maxLength={240} /></Field>
                <Field label={t("profile.email")}><input className="form-control" type="email" value={profile.email} onChange={(e) => update("email", e.target.value)} autoComplete="email" /></Field>
                <Field label={t("profile.phone")}><input className="form-control" value={profile.phone} onChange={(e) => update("phone", e.target.value)} autoComplete="tel" /></Field>
                <Field label={t("profile.location")} hint={t("profile.locationHint")}><input className="form-control" value={locationName} onChange={(e) => update("location", { ...profile.location, name: e.target.value })} placeholder={t("profile.locationPlaceholder")} /></Field>
                <Field label={t("profile.nationality")}><input className="form-control" value={profile.nationality} onChange={(e) => update("nationality", e.target.value)} /></Field>
                <Field label={t("profile.birthDate")}><input className="form-control" type="date" value={profile.birth_date} onChange={(e) => update("birth_date", e.target.value)} /></Field>
                <Field label={t("profile.workAuthorization")} hint={t("profile.commaSeparated")}><input className="form-control" value={(profile.work_authorization || []).join(", ")} onChange={(e) => update("work_authorization", e.target.value.split(",").map((item) => item.trim()).filter(Boolean))} placeholder="CH, EU" /></Field>
            </div>
            <Field label={t("profile.summary")}><textarea className="form-control" rows="6" value={profile.summary} onChange={(e) => update("summary", e.target.value)} placeholder={t("profile.summaryPlaceholder")} maxLength={20000} /></Field>
            <div className="form-grid form-grid--3">
                <Field label={t("profile.website")}><input className="form-control" type="url" value={profile.website} onChange={(e) => update("website", e.target.value)} placeholder="https://" /></Field>
                <Field label="LinkedIn"><input className="form-control" type="url" value={profile.linkedin} onChange={(e) => update("linkedin", e.target.value)} placeholder="https://" /></Field>
                <Field label="GitHub"><input className="form-control" type="url" value={profile.github} onChange={(e) => update("github", e.target.value)} placeholder="https://" /></Field>
            </div>
        </section>
    );
}
