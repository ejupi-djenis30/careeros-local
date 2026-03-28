"""Unit tests for backend/repositories/user_repository.py.

Covers UserRepository.get_by_username against an in-memory SQLite database.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.models.user import User
from backend.repositories.user_repository import UserRepository
from backend.services.auth import get_password_hash


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def user_repo(db_session):
    return UserRepository(db_session)


@pytest.fixture
def existing_user(db_session):
    user = User(
        username="alice",
        hashed_password=get_password_hash("SecurePass1"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


# ─── get_by_username ──────────────────────────────────────────────────────────

class TestUserRepositoryGetByUsername:
    def test_returns_user_when_found(self, user_repo, existing_user):
        result = user_repo.get_by_username("alice")
        assert result is not None
        assert result.username == "alice"
        assert result.id == existing_user.id

    def test_returns_none_when_not_found(self, user_repo, existing_user):
        result = user_repo.get_by_username("nonexistent")
        assert result is None

    def test_case_sensitive_lookup(self, user_repo, existing_user):
        # Username lookup is case-sensitive (stored as-is)
        result = user_repo.get_by_username("Alice")
        assert result is None

    def test_returns_none_on_empty_table(self, user_repo):
        result = user_repo.get_by_username("anyone")
        assert result is None


# ─── Inherited BaseRepository methods ─────────────────────────────────────────

class TestUserRepositoryBaseInheritance:
    def test_get_by_id(self, user_repo, existing_user):
        found = user_repo.get(existing_user.id)
        assert found is not None
        assert found.username == "alice"

    def test_get_nonexistent_id_returns_none(self, user_repo):
        found = user_repo.get(99999)
        assert found is None

    def test_get_all_returns_list(self, user_repo, existing_user, db_session):
        user2 = User(username="bob", hashed_password=get_password_hash("Pass2"))
        db_session.add(user2)
        db_session.commit()
        all_users = user_repo.get_all()
        assert len(all_users) == 2

    def test_delete_removes_user(self, user_repo, existing_user, db_session):
        user_repo.delete(existing_user.id)
        db_session.commit()
        assert user_repo.get(existing_user.id) is None
