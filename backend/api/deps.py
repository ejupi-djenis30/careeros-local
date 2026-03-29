import logging
import os

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import PyJWTError
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.repositories.user_repository import UserRepository
from backend.services.auth import decode_access_token

is_testing = os.environ.get("TESTING") == "1"
limiter = Limiter(key_func=get_remote_address, enabled=not is_testing)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
logger = logging.getLogger(__name__)


def get_current_user_id(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> int:
    try:
        payload = decode_access_token(token)
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        logger.error("Unexpected error during token decode", exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    username = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = UserRepository(db).get_by_username(username)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user.id


def job_service_dep(db: Session = Depends(get_db)):
    from backend.services.job_service import get_job_service

    return get_job_service(db)


def profile_service_dep(db: Session = Depends(get_db)):
    from backend.services.profile_service import get_profile_service

    return get_profile_service(db)
