from infrastructure.database.repositories.notificationRepository import NotificationRepository
from infrastructure.external import fcmService
from domain.entities.notification import Notification
from core.database import Database


class NotificationService:
    def __init__(self, db):
        self.database: Database = db
        self.notificationRepository = NotificationRepository(self.database)
        
    
    def addDevice(self, user_id: str, device_fcm: str) -> Notification:
        """Add a device to recive notifications
        
        Args:
            user_id (str): User ID
            device_fcm (str): Device FCM
            
        Returns:
            Notification: Notification with his full data
        """
        return self.notificationRepository.add(user_id, device_fcm)
    
    
    def updateDevice(self, user_id: str, old_fcm: str, new_fcm: str) -> Notification:
        """Update a device
        
        Args:
            user_id (str): User ID
            old_fcm (str): Old FCM
            new_fcm (str): New FCM
            
        Returns:
            Notification: Notification with his full data
        """
        return self.notificationRepository.update(user_id, old_fcm, new_fcm)
    
    
    def sendBadgeNotification(self, user_id: str, badge_name: str) -> None:
        tokens = self.notificationRepository.findActiveByUserId(user_id)
        fcmService.sendPush(tokens, title="Badge unlocked!", body=f"You earned {badge_name}")

    def deleteDevice(self, user_id: str, old_fcm: str) -> bool:
        """Delete a device
        
        Args:
            user_id (str): User ID
            old_fcm (str): Old FCM
            
        Returns:
            Notification: Notification with his full data
        """
        return self.notificationRepository.softDelete(user_id, old_fcm)