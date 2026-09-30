import logging

from infrastructure.external.firebaseApp import getFirebaseApp

logger = logging.getLogger(__name__)


# The push categories a user can switch off, each the name of a column on
# `NotificationModel` (migration 20260928_01). A push sent without a category
# goes to every enabled device — badges today, which only the master switch
# (unregistering the token) silences.
CATEGORIES = ("messages", "friends", "community")


def sendPushToUser(user_id: str, title: str, body: str, category: str | None = None) -> None:
    from core.database import database
    from infrastructure.database.models.notificationModel import NotificationModel
    from core.config import config as appConfig

    if category is not None and category not in CATEGORIES:
        # A typo here would silently push to everyone, or to no one.
        raise ValueError(f"unknown push category: {category}")

    db = database.session
    try:
        query = db.query(NotificationModel).filter(
            NotificationModel.user_id == user_id,
            NotificationModel.status == appConfig.STATUS_CODES["enabled"],
        )
        if category is not None:
            query = query.filter(getattr(NotificationModel, category).is_(True))
        devices = query.all()
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
