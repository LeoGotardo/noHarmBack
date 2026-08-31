import logging

from infrastructure.external.firebaseApp import getFirebaseApp

logger = logging.getLogger(__name__)


def sendPushToUser(user_id: str, title: str, body: str) -> None:
    from core.database import database
    from infrastructure.database.models.notificationModel import NotificationModel
    from core.config import config as appConfig

    db = database.session
    try:
        devices = (
            db.query(NotificationModel)
            .filter(
                NotificationModel.user_id == user_id,
                NotificationModel.status == appConfig.STATUS_CODES["enabled"],
            )
            .all()
        )
        tokens = [d.device_fcm for d in devices]
        sendPush(tokens, title, body)
    except Exception as e:
        logger.error(f"sendPushToUser failed for {user_id}: {e}")
    finally:
        db.close()


def sendPush(tokens: list[str], title: str, body: str) -> None:
    if not tokens:
        return

    app = getFirebaseApp()
    if app is None:
        logger.debug("FCM not configured — skipping push")
        return

    try:
        from firebase_admin import messaging

        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            tokens=tokens,
        )
        response = messaging.send_each_for_multicast(message)
        if response.failure_count:
            logger.warning(f"FCM: {response.failure_count}/{len(tokens)} tokens failed")
    except Exception as e:
        logger.error(f"FCM send failed: {e}")
