/**
 * Pure utility functions for the SearchForm component.
 */

export function mergeRoleDescription(roleDescription, legacyStrategy) {
    const baseDescription = String(roleDescription || "").trim();
    const extraRequirements = String(legacyStrategy || "").trim();

    if (!extraRequirements) return baseDescription;
    if (!baseDescription) return extraRequirements;
    if (baseDescription.toLowerCase().includes(extraRequirements.toLowerCase())) return baseDescription;

    return `${baseDescription}\n\nAdditional search requirements:\n${extraRequirements}`;
}

export function normalizePrefillProfile(prefill) {
    if (!prefill) return null;

    const {
        search_strategy: legacyStrategy,
        preferred_domains: _preferredDomains,
        workload_min: _legacyWorkloadMin,
        workload_max: _legacyWorkloadMax,
        hard_max_distance_km: _legacyHardMaxDistance,
        ...rest
    } = prefill;

    const cvContent = String(rest.cv_content ?? "");
    const profileSource = rest.profile_source === "uploaded_cv"
        || (rest.profile_source == null && cvContent.trim())
        ? "uploaded_cv"
        : "career_vault";
    const remoteOnly = Boolean(rest.remote_only);

    return {
        ...rest,
        name: String(rest.name ?? ""),
        profile_source: profileSource,
        role_description: mergeRoleDescription(rest.role_description, legacyStrategy),
        location_filter: String(rest.location_filter ?? ""),
        cv_content: cvContent,
        workload_filter: String(rest.workload_filter ?? "80-100"),
        contract_type: String(rest.contract_type ?? "any"),
        max_distance: remoteOnly ? 0 : rest.max_distance,
    };
}
