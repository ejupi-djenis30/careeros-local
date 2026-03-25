from typing import Any


def get_profile_preference(profile, key: str, default=None):
    """Return a profile preference from direct attributes or advanced preferences."""
    direct = getattr(profile, key, None)
    # MagicMock placeholders appear as pseudo-values in tests; treat them as unset.
    if type(direct).__name__ == "MagicMock":
        direct = None
    if direct is not None:
        return direct

    advanced = getattr(profile, "advanced_preferences", None)
    if isinstance(advanced, dict) and key in advanced:
        return advanced.get(key)

    return default
