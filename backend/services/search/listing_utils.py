"""Compatibility import for provider-neutral listing normalization."""

import sys

from backend.search.normalization import listings as _listings

sys.modules[__name__] = _listings
