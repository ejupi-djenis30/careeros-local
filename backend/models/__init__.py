"""Stable legacy exports for the core job-search persistence models.

The complete SQLAlchemy metadata registry lives in ``backend.model_registry`` so
feature models can import this package without circular initialization.
"""

from backend.models.base_model import BaseModel as BaseModel
from backend.models.job import Job as Job
from backend.models.job import ScrapedJob as ScrapedJob
from backend.models.search_profile import SearchProfile as SearchProfile
from backend.models.user import User as User
