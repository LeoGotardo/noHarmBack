from core.errorUtils import excLocation
from infrastructure.database.models.userBadgesModel import UserBadgesModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.userBadge import UserBadge
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse
from core.database import Database
from core.config import config
from core.statusCodes import resolveStatusCode

from datetime import datetime
from typing import Optional


class UserBadgesRepository:
    def __init__(self, database: Database):
        self.database = database
        self.session = self.database.session
        self.engine = self.database.engine


    def _toEntity(self, model: UserBadgesModel) -> UserBadge:
        return UserBadge(
            id=model.id,
            user_id=model.user_id,
            badge_id=model.badge_id,
            given_at=model.given_at,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


    def findById(self, id: str, returnModel: bool = False) -> UserBadge | UserBadgesModel:
        try:
            userBadgesModel = self.session.query(UserBadgesModel).filter(UserBadgesModel.id == id).first()

            if not userBadgesModel:
                raise NoHarmException(statusCode=404, message="UserBadge not found")

            return userBadgesModel if returnModel else self._toEntity(userBadgesModel)
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findByUserId(self, user_id: str, params: Optional[PaginationParams] = None) -> list[UserBadge] | PaginatedResponse[UserBadge]:
        try:
            query = self.session.query(UserBadgesModel).filter(UserBadgesModel.user_id == user_id)
            
            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                
                items = [self._toEntity(m) for m in query.offset(offset).limit(params.pageSize).all()]
                
                return createPaginatedResponse(items, total, params.page, params.pageSize)
            
            return [self._toEntity(m) for m in query.all()]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findByBadgeId(self, badge_id: str, params: Optional[PaginationParams] = None) -> list[UserBadge] | PaginatedResponse[UserBadge]:
        try:
            query = self.session.query(UserBadgesModel).filter(UserBadgesModel.badge_id == badge_id)
            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                items = [self._toEntity(m) for m in query.offset(offset).limit(params.pageSize).all()]
                return createPaginatedResponse(items, total, params.page, params.pageSize)
            return [self._toEntity(m) for m in query.all()]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def existsByUserAndBadge(self, user_id: str, badge_id: str) -> bool:
        try:
            return self.session.query(UserBadgesModel).filter(
                UserBadgesModel.user_id == user_id,
                UserBadgesModel.badge_id == badge_id
            ).first() is not None
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def grant(self, user_id: str, badge_id: str, given_at: datetime | None = None) -> UserBadge:
        """Grant a badge, or re-enable it if it was previously revoked.

        `status` and `given_at` are both NOT NULL, so neither may be left unset —
        passing given_at=None used to bypass the column default and fail.
        """
        try:
            grantedAt = given_at or datetime.now()

            model = self.session.query(UserBadgesModel).filter(
                UserBadgesModel.user_id == user_id,
                UserBadgesModel.badge_id == badge_id
            ).first()

            if model:
                model.given_at = grantedAt
                model.status = config.STATUS_CODES["enabled"]
            else:
                model = UserBadgesModel(
                    user_id=user_id,
                    badge_id=badge_id,
                    given_at=grantedAt,
                    status=config.STATUS_CODES["enabled"],
                )
                self.session.add(model)

            self.session.commit()
            return self._toEntity(model)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def revoke(self, user_id: str, badge_id: str) -> UserBadge:
        try:
            model = self.session.query(UserBadgesModel).filter(
                UserBadgesModel.user_id == user_id,
                UserBadgesModel.badge_id == badge_id
            ).first()
            if not model:
                raise NoHarmException(statusCode=404, message="UserBadge not found")
            model.status = config.STATUS_CODES["deleted"]
            self.session.commit()
            return self._toEntity(model)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def updateStatus(self, id: str, status: int) -> UserBadge:
        try:
            statusCode = resolveStatusCode(status)
            userBadgesModel = self.findById(id, returnModel=True)

            userBadgesModel.status = statusCode

            self.session.commit()
            
            return self._toEntity(userBadgesModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def update(self, id: str, updatedUserBadge: UserBadge) -> UserBadge:
        try:
            userBadgesModel = self.findById(id, returnModel=True)
            
            if updatedUserBadge.status:
                userBadgesModel.status = updatedUserBadge.status
            
            self.session.commit()
            
            return self._toEntity(userBadgesModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def delete(self, id: str) -> bool:
        try:
            userBadgesModel = self.findById(id, returnModel=True)
            
            self.session.delete(userBadgesModel)
            self.session.commit()
            
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def softDelete(self, id: str) -> UserBadge:
        try:
            userBadgesModel = self.findById(id, returnModel=True)

            userBadgesModel.status = config.STATUS_CODES["deleted"]

            self.session.commit()

            return self._toEntity(userBadgesModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
