from model.badgeModel import BadgeModel, Badge



class BadgeController(Badge):
    def giveBadge(badgeId: str, userId: str):
        ...
        
    def removeBadge(badgeId: str, userId: str) -> tuple[bool, str]:
        ...
        
    def createBadge(Badge: Badge) -> tuple[bool, Badge]:
        ...
        
    def deleteBadge(badgeId: str) -> tuple[bool, str]:
        ...
        
    def desableBadge(badgeId: str) -> tuple[bool, str]:
        ...