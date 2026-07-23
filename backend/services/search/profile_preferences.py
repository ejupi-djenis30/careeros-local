def get_profile_preference(profile, key: str, default=None):
    """Return a profile preference from direct attributes or advanced preferences.

    Only primitive values (str, int, float, bool, list, dict) are accepted from
    direct attribute lookup. Non-primitive objects are treated as unset so that
    callers receive a clean default rather than an unexpected object instance.
    """
    direct = getattr(profile, key, None)
    # Only accept plain Python primitives/containers. Any other type (e.g. an
    # uninitialised ORM column expression or an unspec'd mock) is treated as unset.
    if direct is not None and not isinstance(direct, (str, int, float, bool, list, dict)):
        direct = None
    if direct is not None:
        return direct

    advanced = getattr(profile, "advanced_preferences", None)
    if isinstance(advanced, dict) and key in advanced:
        return advanced.get(key)

    return default
