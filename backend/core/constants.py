"""Shared constants used across the backend."""

# Fields treated as user-preference settings (stored in advanced_preferences on SearchProfile).
# Centralised here to avoid duplication between api/routes/search.py and services/profile_service.py.
PREFERENCE_FIELDS: frozenset = frozenset(
    {
        "preferred_languages",
        "preferred_domains",
        "remote_only",
        "salary_min_chf",
        "workload_min",
        "workload_max",
        "hard_max_distance_km",
    }
)
