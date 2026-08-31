"""Importing any model imports them all.

Two models carry a `relationship()` written as a string — `UserModel.user_badges`
names "UserBadgesModel", `ChatModel.messages` names "MessageModel". SQLAlchemy
resolves those names against its registry the first time a mapper is
configured, and a class only reaches the registry when its module has been
imported. Import `userModel` on its own and the mapper fails with

    expression 'UserBadgesModel.user_id' failed to locate a name

which is not a missing import at the call site: the module that *would* have
registered the class simply was not loaded by anyone.

`core/database.py` imports all ten by hand for this reason, so the running
application never saw it. Anything that imports a model without going through
that — the unit tests, a script, a future worker — did. Listing them here makes
the package itself the guarantee, and `core/database.py` keeps its own list as
documentation of what `create_all` covers.

Only the modules are imported, not names re-exported: existing imports of the
form `from infrastructure.database.models.userModel import UserModel` keep
working unchanged.
"""

from infrastructure.database.models import (  # noqa: F401
    auditLogsModel,
    badgeModel,
    chatModel,
    friendshipModel,
    messageModel,
    notificationModel,
    refreshTokenModel,
    streakModel,
    userBadgesModel,
    userModel,
)
