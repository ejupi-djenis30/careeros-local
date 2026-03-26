"""Tests for backend/services/search/profile_preferences.py.

This module had zero test coverage.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.services.search.profile_preferences import get_profile_preference


class TestGetProfilePreference:
    def test_returns_direct_int_attribute(self):
        profile = SimpleNamespace(salary_min_chf=80000)
        assert get_profile_preference(profile, "salary_min_chf") == 80000

    def test_returns_direct_bool_attribute(self):
        profile = SimpleNamespace(remote_only=True)
        assert get_profile_preference(profile, "remote_only") is True

    def test_returns_direct_string_attribute(self):
        profile = SimpleNamespace(name="Test")
        assert get_profile_preference(profile, "name") == "Test"

    def test_returns_direct_list_attribute(self):
        profile = SimpleNamespace(preferred_languages=["en", "de"])
        assert get_profile_preference(profile, "preferred_languages") == ["en", "de"]

    def test_advanced_preferences_fallback(self):
        profile = SimpleNamespace(advanced_preferences={"salary_min_chf": 95000})
        # No direct attribute set — falls through to advanced_preferences
        result = get_profile_preference(profile, "salary_min_chf")
        assert result == 95000

    def test_direct_attribute_takes_priority_over_advanced(self):
        profile = SimpleNamespace(
            salary_min_chf=50000,
            advanced_preferences={"salary_min_chf": 99999},
        )
        assert get_profile_preference(profile, "salary_min_chf") == 50000

    def test_default_returned_when_not_found(self):
        profile = SimpleNamespace()
        assert get_profile_preference(profile, "nonexistent_key") is None
        assert get_profile_preference(profile, "nonexistent_key", 42) == 42

    def test_none_direct_attribute_falls_through_to_advanced(self):
        profile = SimpleNamespace(
            salary_min_chf=None,
            advanced_preferences={"salary_min_chf": 70000},
        )
        # None direct → falls through to advanced_preferences
        assert get_profile_preference(profile, "salary_min_chf") == 70000

    def test_non_primitive_direct_value_falls_through(self):
        """A non-primitive (e.g. ORM expression or unspec'd mock) is treated as unset."""
        profile = SimpleNamespace(salary_min_chf=MagicMock())
        profile.advanced_preferences = {"salary_min_chf": 60000}
        assert get_profile_preference(profile, "salary_min_chf") == 60000

    def test_non_primitive_no_advanced_returns_default(self):
        profile = SimpleNamespace(salary_min_chf=MagicMock())
        profile.advanced_preferences = {}
        assert get_profile_preference(profile, "salary_min_chf") is None

    def test_no_advanced_preferences_attribute(self):
        profile = SimpleNamespace()
        assert get_profile_preference(profile, "salary_min_chf", 0) == 0

    def test_advanced_preferences_not_a_dict(self):
        profile = SimpleNamespace(advanced_preferences="invalid")
        assert get_profile_preference(profile, "salary_min_chf") is None

    def test_zero_int_is_returned(self):
        """Zero is a valid value and must not be confused with falsy None."""
        profile = SimpleNamespace(workload_min=0)
        assert get_profile_preference(profile, "workload_min") == 0

    def test_false_bool_is_returned(self):
        """False is a valid value and must not be confused with falsy None."""
        profile = SimpleNamespace(remote_only=False)
        assert get_profile_preference(profile, "remote_only") is False
