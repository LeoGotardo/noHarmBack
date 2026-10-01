from core.errorUtils import excLocation
from core.database import Database
from infrastructure.database.models.adminGrantModel import AdminGrantModel
from exceptions.baseExceptions import NoHarmException


class AdminGrantRepository:
    """tb_19 — administrators promoted from inside the app.

    Writes pass RLS only without a context, so this must be handed a `getDb`
    session, never `getDbWithRLS`.
    """

    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session


    def exists(self, userId: str) -> bool:
        try:
            return self.session.query(AdminGrantModel.user_id).filter(
                AdminGrantModel.user_id == str(userId)
            ).first() is not None
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findAll(self) -> list[AdminGrantModel]:
        try:
            return self.session.query(AdminGrantModel).order_by(AdminGrantModel.created_at).all()
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def grant(self, userId: str, grantedBy: str) -> AdminGrantModel:
        try:
            model = AdminGrantModel(user_id=str(userId), granted_by=str(grantedBy))
            self.session.add(model)
            self.session.commit()
            return model
        except Exception as e:
            self.session.rollback()
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def revoke(self, userId: str) -> bool:
        """Remove a grant. False when there was none."""
        try:
            deleted = self.session.query(AdminGrantModel).filter(
                AdminGrantModel.user_id == str(userId)
            ).delete()
            self.session.commit()
            return deleted > 0
        except Exception as e:
            self.session.rollback()
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
