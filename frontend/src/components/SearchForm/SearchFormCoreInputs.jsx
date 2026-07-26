import React from "react";
import { LocationInput } from "../LocationInput";
import { useI18n } from "../../i18n/useI18n";

export function SearchFormCoreInputs({
    profile,
    handleChange,
    handleLocationChange,
    handleRemoteChange,
    errors = {},
}) {
    const { t } = useI18n();
    const roleDescribedBy = ["search-role-help", errors.role_description && "search-role-error"].filter(Boolean).join(" ");
    const locationDescribedBy = ["search-location-help", errors.location_filter && "search-location-error"].filter(Boolean).join(" ");

    return (
        <section className="search-core" aria-labelledby="search-core-title">
            <div className="search-core__heading">
                <p className="search-section-label">{t("searchForm.core.eyebrow")}</p>
                <h3 id="search-core-title">{t("searchForm.core.title")}</h3>
            </div>

            <div className="search-field">
                <label htmlFor="search-role-description" className="search-field__label">
                    {t("searchForm.roleDescription")} <span aria-hidden="true">*</span>
                </label>
                <textarea
                    id="search-role-description"
                    name="role_description"
                    value={profile.role_description}
                    onChange={handleChange}
                    placeholder={t("searchForm.rolePlaceholder")}
                    className={`form-control bg-black-20 border-white-10 text-white ${errors.role_description ? "is-invalid" : ""}`}
                    rows="7"
                    required
                    aria-invalid={Boolean(errors.role_description) || undefined}
                    aria-describedby={roleDescribedBy}
                />
                <p id="search-role-help" className="search-field__help">{t("searchForm.roleHelp")}</p>
                {errors.role_description && (
                    <p id="search-role-error" className="field-error" role="alert">{errors.role_description}</p>
                )}
            </div>

            <div className="search-field">
                <label htmlFor="search-location" className="search-field__label">
                    {t("searchForm.targetLocation")} <span aria-hidden="true">*</span>
                </label>
                <LocationInput
                    id="search-location"
                    location={profile.location_filter}
                    latitude={profile.latitude}
                    longitude={profile.longitude}
                    onLocationChange={handleLocationChange}
                    invalid={Boolean(errors.location_filter)}
                    ariaDescribedBy={locationDescribedBy}
                />
                <p id="search-location-help" className="search-field__help">
                    {profile.remote_only ? t("searchForm.locationRemoteHelp") : t("searchForm.locationHelp")}
                </p>
                {errors.location_filter && (
                    <p id="search-location-error" className="field-error" role="alert">{errors.location_filter}</p>
                )}
            </div>

            <div className={`search-remote-control ${profile.remote_only ? "is-active" : ""}`}>
                <div>
                    <label htmlFor="search-remote-only">{t("searchForm.remoteOnly")}</label>
                    <p id="search-remote-help">{t("searchForm.remoteCopy")}</p>
                </div>
                <input
                    className="form-check-input"
                    type="checkbox"
                    role="switch"
                    id="search-remote-only"
                    checked={Boolean(profile.remote_only)}
                    onChange={handleRemoteChange}
                    aria-describedby="search-remote-help"
                />
            </div>
        </section>
    );
}
