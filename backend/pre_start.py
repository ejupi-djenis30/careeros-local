import logging
import sys

from sqlalchemy import text
from tenacity import after_log, before_log, retry, stop_after_attempt, wait_fixed

from backend.db.base import Base, engine
from backend import models  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

max_tries = 60 * 5  # 5 minutes
wait_seconds = 1


@retry(
    stop=stop_after_attempt(max_tries),
    wait=wait_fixed(wait_seconds),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.WARN),
)
def init() -> None:
    try:
        # Try to create session to check if DB is awake
        with engine.connect() as db:
            db.execute(text("SELECT 1"))
        logger.info("Database is ready.")
        
        # Create tables (Handled by Alembic)
        # logger.info("Creating database tables...")
        # Base.metadata.create_all(bind=engine)
        # logger.info("Database tables created successfully.")
        
    except Exception as e:
        logger.error(e)
        raise e


def main() -> None:
    logger.info("Initializing service")
    init()
    logger.info("Service finished initializing")


if __name__ == "__main__":
    main()
