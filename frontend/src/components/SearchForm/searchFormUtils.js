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

    return {
        ...rest,
        role_description: mergeRoleDescription(rest.role_description, legacyStrategy),
    };
}
