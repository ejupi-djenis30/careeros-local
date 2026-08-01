import logging
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure

logger = logging.getLogger(__name__)

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType", bound=PydanticBaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=PydanticBaseModel)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], db: Session):
        self.model = model
        self.db = db

    def get(self, id: Any) -> Optional[ModelType]:
        return self.db.query(self.model).filter(self.model.id == id).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        return self.db.query(self.model).offset(skip).limit(limit).all()

    def create(self, obj_in: Union[CreateSchemaType, Dict[str, Any]]) -> ModelType:
        if isinstance(obj_in, dict):
            obj_in_data = obj_in
        else:
            obj_in_data = obj_in.model_dump()

        db_obj = self.model(**obj_in_data)
        self.db.add(db_obj)
        try:
            self.db.commit()
            self.db.refresh(db_obj)
        except IntegrityError as exc:
            self.db.rollback()
            diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_INTEGRITY_FAILED)
            log_failure(logger, diagnostic, level=logging.WARNING)
            raise
        except Exception as exc:
            self.db.rollback()
            diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
            log_failure(logger, diagnostic)
            raise
        return db_obj

    def update(
        self, db_obj: ModelType, obj_in: Union[UpdateSchemaType, Dict[str, Any]]
    ) -> ModelType:
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        self.db.add(db_obj)
        try:
            self.db.commit()
            self.db.refresh(db_obj)
        except IntegrityError as exc:
            self.db.rollback()
            diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_INTEGRITY_FAILED)
            log_failure(logger, diagnostic, level=logging.WARNING)
            raise
        except Exception as exc:
            self.db.rollback()
            diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
            log_failure(logger, diagnostic)
            raise
        return db_obj

    def delete(self, id: Any) -> Optional[ModelType]:
        obj = self.db.get(self.model, id)
        if obj:
            self.db.delete(obj)
            try:
                self.db.commit()
            except IntegrityError as exc:
                self.db.rollback()
                diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_INTEGRITY_FAILED)
                log_failure(logger, diagnostic, level=logging.WARNING)
                raise
            except Exception as exc:
                self.db.rollback()
                diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
                log_failure(logger, diagnostic)
                raise
        return obj
