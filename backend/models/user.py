from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from backend.models.base_model import BaseModel, TimestampMixin


class User(BaseModel, TimestampMixin):
    __tablename__ = "users"

    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # Relationships
    jobs = relationship("Job", back_populates="user")
    profiles = relationship("SearchProfile", back_populates="user")
