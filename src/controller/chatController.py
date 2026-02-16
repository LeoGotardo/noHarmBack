from model.chatModel import ChatModel, Chat
from model.userModel import UserModel, User

class ChatController(Chat):
    def startCHat(by: User, to: User) -> tuple[int, Chat] | tuple[int, str]:
        ...