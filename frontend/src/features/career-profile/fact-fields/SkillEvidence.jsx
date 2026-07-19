import { useI18n } from "../../../i18n/useI18n";

export function SkillEvidence({ selectedIds = [], options = [], onChange }) {
    const { t } = useI18n();
    const selected = new Set(selectedIds);
    const toggle = (id, enabled) => onChange(
        enabled ? [...selectedIds, id] : selectedIds.filter((item) => item !== id),
    );
    return (
        <fieldset className="fact-evidence">
            <legend>{t("factEvidence.title")}</legend>
            {options.length === 0 ? <p>{t("factEvidence.empty")}</p> : options.map((option) => (
                <label className="check-line" key={option.id}>
                    <input type="checkbox" checked={selected.has(option.id)} onChange={(event) => toggle(option.id, event.target.checked)} aria-label={t("factEvidence.option", { label: option.label })} />
                    <span>{option.label}</span>
                    <small>{option.type}</small>
                </label>
            ))}
        </fieldset>
    );
}
