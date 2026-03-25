from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from backend.db.base import get_db
from backend.services.auth import decode_access_token
from backend.models import User
import os
import logging
from slowapi import Limiter
from slowapi.util import get_remote_address

is_testing = os.environ.get("TESTING") == "1"
limiter = Limiter(key_func=get_remote_address, enabled=not is_testing)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
logger = logging.getLogger(__name__)

def get_current_user_id(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> int:
    try:
        payload = decode_access_token(token)
    except Exception:
        logger.warning("Token decode raised an unexpected exception", exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    username = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user.id

def get_job_service(db: Session = Depends(get_db)):
    from backend.services.job_service import get_job_service
    return get_job_service(db)

def get_profile_service(db: Session = Depends(get_db)):
    from backend.services.profile_service import get_profile_service
    return get_profile_service(db)
