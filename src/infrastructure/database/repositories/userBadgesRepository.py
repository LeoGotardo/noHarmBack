from infrastructure.database.models.userBedgesModel import UserBadgesModel
from domain.entities.userBadge import UserBadge

from core.database import Database

from datetime import datetime

class UserBadgesRepository(UserBadge):
    def __init__(self, database: Database):
        self.session = database.session
        
    
    def addUserBadge(self, user_id: str, badge_id: str, given_at: datetime) -> bool:
        """Adiciona um badge a um usuário
        
        Args:
            user_id (str): ID do usuário
            
            
            badge_id (str): ID do badge
            given_at (datetime): Data de criação do badge
            
        Returns:
            bool: True se o badge foi adicionado com sucesso, False caso contrário
        """
        try:
            userBadge = UserBadge(
                user_id=user_id,
                badge_id=badge_id,
                given_at=given_at
            )
            
            try:
                self.session.add(userBadge)
                self.session.commit()
            except Exception as e:
                self.session.rollback()
                raise e
            
            return True
        except Exception as e:
            return False