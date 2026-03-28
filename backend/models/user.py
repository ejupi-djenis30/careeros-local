from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from backend.models.base_model import BaseModel, TimestampMixin


class User(BaseModel, TimestampMixin):
    __tablename__ = "users"

    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    email = Column(String, nullable=True, unique=True, index=True)
    supabase_id = Column(String, nullable=True, unique=True, index=True)

    # Relationships
    jobs = relationship("Job", back_populates="user")
    profiles = relationship("SearchProfile", back_populates="user")
