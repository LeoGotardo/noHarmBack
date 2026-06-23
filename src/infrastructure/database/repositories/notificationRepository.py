from core.database import Database
from domain.entities.notification import Notification
from infrastructure.database.models.notificationModel import NotificationModel
from exceptions.baseExceptions import NoHarmException
from core.errorUtils import excLocation
from core.config import config
from security.encryption import Encryption


class NotificationRepository:
    def __init__(self, db: Database):
        self.database = db
        self.session = db.session

    def _toEntity(self, model: NotificationModel) -> Notification:
        return Notification(
            id=model.id,
            user_id=model.user_id,
            status=model.status,
            device_fcm=model.device_fcm,
            created_at=model.created_at,
            updated_at=model.updated_at
        )

    def _findByFcm(self, user_id: str, fcm_token: str) -> NotificationModel:
        fcm_hash = Encryption.hash(fcm_token)
        device = (
            self.session.query(NotificationModel)
            .filter(
                NotificationModel.user_id == user_id,
                NotificationModel.device_fcm_hash == fcm_hash
            )
            .first()
        )
        if not device:
            raise NoHarmException(statusCode=404, message="Device not found")
        return device

    def add(self, user_id: str, device_fcm: str) -> Notification:
        try:
            notification = NotificationModel(
                user_id=user_id,
                device_fcm=device_fcm,
                status=config.STATUS_CODES["enabled"],
            )
            self.session.add(notification)
            self.session.commit()
            return self._toEntity(notification)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def update(self, user_id: str, old_fcm: str, new_fcm: str) -> Notification:
        try:
            device = self._findByFcm(user_id, old_fcm)
            device.device_fcm = new_fcm
            self.session.commit()
            return self._toEntity(device)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def findActiveByUserId(self, user_id: str) -> list[str]:
        devices = (
            self.session.query(NotificationModel)
            .filter(
                NotificationModel.user_id == user_id,
                NotificationModel.status == config.STATUS_CODES["enabled"],
            )
            .all()
        )
        return [d.device_fcm for d in devices]

    def softDelete(self, user_id: str, fcm_token: str) -> bool:
        try:
            device = self._findByFcm(user_id, fcm_token)
            device.status = config.STATUS_CODES["deleted"]
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
