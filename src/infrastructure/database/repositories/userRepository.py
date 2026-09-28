from core.errorUtils import excLocation
from infrastructure.database.models.userModel import UserModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.user import User
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse
from core.database import Database
from core.config import config
from security.encryption import Encryption

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta, timezone
from typing import Optional

# How many generated handles to try before giving up. The space is 2^32, so a
# second attempt is already a curiosity and a third never happens; the loop
# exists because a unique index is a guarantee and "unlikely" is not.
_RENAME_ATTEMPTS = 5

class UserRepository:
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
        
    def _toEntity(self, model: UserModel) -> User:
        return User(
            id=model.id,
            username=model.username,
            email=model.email,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
            profile_picture=model.profile_picture,
            deleted_at=model.deleted_at,
            banned_until=model.banned_until,
            must_change_username=bool(model.must_change_username),
            picture_blocked=bool(model.picture_blocked),
            birth_date=model.birth_date
        )
        
    
    def findById(self, id: str, returnModel: bool = False) -> User | UserModel:
        """Find a user by ID
        
        Args:
            id (str): User ID
            
        Returns:
            User: User with his full data
        """
        try:
            user = self.session.query(UserModel).filter(UserModel.id == id).first()
            if user:
                return user if returnModel else self._toEntity(user)
            else:
                raise NoHarmException(statusCode=404, message="User not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
    
    
    def findByEmail(self, email: str) -> User:
        try:
            emailHash = Encryption.hash(email)
            
            userModel = self.session.query(UserModel).filter(UserModel.email_hash == emailHash).first()
            
            if userModel:
                return self._toEntity(userModel)
            else:
                raise NoHarmException(statusCode=404, message="User not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findByUsername(self, username: str) -> User:
        try:
            usernameHash = Encryption.hash(username)
            userModel = self.session.query(UserModel).filter(UserModel.username_hash == usernameHash).first()
            
            if userModel:
                return self._toEntity(userModel)
            else:
                raise NoHarmException(statusCode=404, message="User not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
    
    
    def findManyByIds(self, ids: list[str]) -> list[User]:
        """Fetch multiple users by ID (public profile read).

        Returns only users that exist; missing IDs are silently skipped.
        """
        if not ids:
            return []
        try:
            userModels = self.session.query(UserModel).filter(UserModel.id.in_(ids)).all()
            return [self._toEntity(u) for u in userModels]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    # Accounts in these states are excluded from the directory: a deleted or
    # banned user must not remain findable in friend search.
    _HIDDEN_STATUSES = (
        config.STATUS_CODES["deleted"],
        config.STATUS_CODES["banned"],
        config.STATUS_CODES["blocked"],
    )


    def search(self, term: str, params: Optional[PaginationParams] = None) -> list[User] | PaginatedResponse[User]:
        """Find users by an exact username or email match.

        Both columns are encrypted, so only their SHA-256 hashes are queryable —
        exact matches only, which is also what the privacy rule requires (§5).
        Without this, clients had to page the whole directory to find one person.
        """
        try:
            term = (term or "").strip()
            if not term:
                return [] if not params else createPaginatedResponse([], 0, params.page, params.pageSize)

            termHash = Encryption.hash(term)
            query = (
                self.session.query(UserModel)
                .filter(UserModel.status.notin_(self._HIDDEN_STATUSES))
                .filter((UserModel.username_hash == termHash) | (UserModel.email_hash == termHash))
            )

            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                items = [self._toEntity(item) for item in query.offset(offset).limit(params.pageSize).all()]
                return createPaginatedResponse(items, total, params.page, params.pageSize)

            return [self._toEntity(item) for item in query.all()]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findAll(
        self,
        params: Optional[PaginationParams] = None,
        includeInactive: bool = False,
        status: Optional[int] = None,
    ) -> list[User] | PaginatedResponse[User]:
        """Find all users, optionally paginated

        `status` narrows to one status **in the query**, before the page is
        taken. Filtering the page afterwards instead — which the admin route
        did until this argument existed — silently answers "the banned accounts
        that happen to be on page one", and reports a total for the unfiltered
        set beside it.

        Args:
            params: Optional pagination parameters (page, pageSize)
            includeInactive: Include deleted / banned / blocked accounts
            status: Only accounts at this status

        Returns:
            list[User] | PaginatedResponse[User]: List of Users or paginated response
        """
        try:
            query = self.session.query(UserModel)
            if not includeInactive:
                query = query.filter(UserModel.status.notin_(self._HIDDEN_STATUSES))
            if status is not None:
                query = query.filter(UserModel.status == status)
            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                
                items = query.offset(offset).limit(params.pageSize).all()
                items = [self._toEntity(item) for item in items]
                
                return createPaginatedResponse(items, total, params.page, params.pageSize)  
            
            return [self._toEntity(item) for item in query.all()]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
    
    
    def create(self, User: User) -> User:
        """Create a user
        
        Args:
            User (User): User to create
            
        Returns:
            User: User with his full data
        """
        try:
            userModel = UserModel(
                id=User.id,
                username=User.username,
                email=User.email,
                status=User.status,
                created_at=User.created_at,
                updated_at=User.updated_at,
                profile_picture=User.profile_picture,
                # Declared at registration and never editable afterwards: there
                # is no route that writes it again, so `update` does not carry
                # it either. Changing a birth date is how an account that was
                # refused for being under age becomes one that was not.
                birth_date=getattr(User, "birth_date", None)
            )
            
            self.session.add(userModel)
            self.session.commit()
            
            return self._toEntity(userModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def update(self, user_id: str, updatedUser: User) -> User: 
        """Update a user
        
        Args:
            user_id (str): User ID
            updatedUser (User): User with updated data
            
        Returns:
            User: User with his full data
        """
        try:
            userModel = self.findById(user_id, returnModel=True)
            
            userModel.username = updatedUser.username if updatedUser.username else userModel.username
            userModel.email = updatedUser.email if updatedUser.email else userModel.email
            userModel.status = updatedUser.status if updatedUser.status else userModel.status
            userModel.profile_picture = updatedUser.profile_picture if updatedUser.profile_picture else userModel.profile_picture
            
            self.session.commit()
            
            return self._toEntity(userModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def updateStatus(self, id: str, status: int) -> User:
        """Update a user status

        Moving an account off `banned` clears `banned_until` with it. A stale
        date left behind would make a later permanent ban look like a
        suspension that expired weeks ago, and lift itself at the next login.

        Args:
            id (str): User ID
            status (int): New status
            
        Returns:
            User: User with his full data
        """
        try:
            userModel = self.findById(id, returnModel=True)
            
            userModel.status = status
            if status != config.STATUS_CODES["banned"]:
                userModel.banned_until = None
            
            self.session.commit()
            
            return self._toEntity(userModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        

    def usernamesByIds(self, ids: list[str]) -> dict[str, str]:
        """Resolve a page of user ids to usernames in one query.

        The moderation queue names the reporter on every row. Usernames are
        encrypted, so this cannot be a join in the reports query and it cannot
        be filtered in SQL either — but it is still one round trip for the page
        rather than one per row, which is what the N+1 would cost.

        Ids with no row are simply absent: a purged reporter has no name, and
        inventing one would be worse than the gap.

        Args:
            ids (list[str]): user ids

        Returns:
            dict[str, str]: {userId: username}
        """
        if not ids:
            return {}
        try:
            rows = self.session.query(UserModel).filter(UserModel.id.in_(list(set(ids)))).all()
            return {row.id: row.username for row in rows}
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def forceUsernameChange(self, id: str, generate) -> User:
        """Rename the account to a generated handle and demand a real one.

        `generate` is a callable rather than a value so a collision can be
        retried without the service knowing this ever happens. The unique index
        is on `cl_0b_h`, the blind index of the name, so a clash surfaces as an
        IntegrityError on commit and not as a row this method can look up first.

        Args:
            id (str): User ID
            generate (Callable[[], str]): produces a candidate handle

        Returns:
            User: the account under its new name
        """
        for attempt in range(_RENAME_ATTEMPTS):
            try:
                userModel = self.findById(id, returnModel=True)

                # @validates('username') recomputes cl_0b_h, which is the
                # column the unique index is actually on.
                userModel.username = generate()
                userModel.must_change_username = True

                self.session.commit()
                return self._toEntity(userModel)
            except IntegrityError:
                self.session.rollback()
                if attempt == _RENAME_ATTEMPTS - 1:
                    raise NoHarmException(
                        statusCode=500,
                        errorCode="RENAME_FAILED",
                        message="Could not allocate a username for this account."
                    )
            except Exception as e:
                self.session.rollback()
                if isinstance(e, NoHarmException):
                    raise e
                raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def setPictureBlocked(self, id: str, blocked: bool) -> User:
        """Set or lift the picture block, clearing the picture when setting it.

        Both halves in one transaction: the column holds the photo and the flag
        stops it being written again, and an account left with one without the
        other is either still showing the picture or silently refusing an
        upload for no visible reason.

        Args:
            id (str): User ID
            blocked (bool): True to block and clear, False to lift

        Returns:
            User: User with his full data
        """
        try:
            userModel = self.findById(id, returnModel=True)

            userModel.picture_blocked = blocked
            if blocked:
                userModel.profile_picture = None

            self.session.commit()

            return self._toEntity(userModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def suspend(self, id: str, until: Optional[datetime]) -> User:
        """Ban an account, until `until` or for good when that is None.

        The two are the same status on purpose: everything that refuses a
        banned account — login, register, reactivate, refresh, and the token
        check on every request — keeps working untouched, and the date only
        decides when the ban stops applying.

        Args:
            id (str): User ID
            until (datetime | None): when the suspension ends; None is permanent

        Returns:
            User: User with his full data
        """
        try:
            userModel = self.findById(id, returnModel=True)

            userModel.status = config.STATUS_CODES["banned"]
            userModel.banned_until = until

            self.session.commit()

            return self._toEntity(userModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def liftExpiredSuspension(self, id: str) -> Optional[User]:
        """Re-enable an account whose suspension has run out.

        Returns the restored user, or None when there was nothing to lift —
        the account is not banned, or its ban has no end date, or the date has
        not arrived. Called from the authentication paths rather than a cron:
        an account nobody is trying to sign in to does not need unbanning, and
        a nightly job would be one more thing that silently stops running.
        """
        try:
            userModel = self.findById(id, returnModel=True)

            if userModel.status != config.STATUS_CODES["banned"]:
                return None
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if userModel.banned_until is None or userModel.banned_until > now:
                return None

            userModel.status = config.STATUS_CODES["enabled"]
            userModel.banned_until = None

            self.session.commit()

            return self._toEntity(userModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def delete(self, id: str) -> bool:
        """Delete a user
        
        Args:
            id (str): User ID
            
        Returns:
            bool: True if user was deleted, False if not
        """
        try:
            userModel = self.findById(id, returnModel=True)
            
            self.session.delete(userModel)
            self.session.commit()
            
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def softDelete(self, id: str) -> bool:
        """Soft delete a user

        Args:
            id (str): User ID

        Returns:
            bool: True if user was soft deleted, False if not
        """
        try:
            userModel = self.findById(id, returnModel=True)

            userModel.status = config.STATUS_CODES["deleted"]
            # Starts the grace window. `purgeExpired` reads this, and nothing
            # else does — leaving it unset would make the account undeletable
            # rather than deleted, since the purge would never select it.
            userModel.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self.session.commit()

            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def restore(self, id: str) -> User:
        """Undo a soft delete: back to enabled, clock cleared.

        Args:
            id (str): User ID

        Returns:
            User: the restored user
        """
        try:
            userModel = self.findById(id, returnModel=True)

            userModel.status = config.STATUS_CODES["enabled"]
            userModel.deleted_at = None
            self.session.commit()

            return self._toEntity(userModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    # ── aggregates for the admin board ────────────────────────────────────────
    #
    # Counting, not listing. Everything here groups in SQL and returns a number
    # per bucket, because the panel asks "how many" and pulling rows to answer
    # that would decrypt a username per account to throw it away.

    def countsByStatus(self) -> dict[int, int]:
        """`{statusCode: howMany}`, every status the table actually holds.

        One grouped query rather than one count per status: the board shows
        four of these side by side, and four scans of `tb_0` to produce four
        integers is the shape that gets slower exactly as the app succeeds.

        A status with no rows is simply absent — the caller supplies its own
        zero, which keeps this honest about what it found.
        """
        try:
            rows = (
                self.session.query(UserModel.status, func.count(UserModel.id))
                .group_by(UserModel.status)
                .all()
            )
            return {int(status): int(total) for status, total in rows}
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def countCreatedSince(self, *windows: int) -> dict[int, int]:
        """Sign-ups inside each window, in days: `countCreatedSince(1, 7, 30)`.

        One pass with a FILTER per window instead of one query per window. The
        buckets overlap on purpose — 30 days includes the last 7 — because
        "new this week" and "new this month" are both read as totals, and
        making them exclusive would put the difference in the reader's head.
        """
        if not windows:
            return {}
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            columns = [
                func.count(UserModel.id).filter(
                    UserModel.created_at >= now - timedelta(days=days)
                ).label(f"w{days}")
                for days in windows
            ]
            row = self.session.query(*columns).one()
            return {days: int(value or 0) for days, value in zip(windows, row)}
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def countCreatedPerDay(self, days: int) -> list[dict]:
        """Rows created per day for the last `days`, oldest first.

        **Every day is present, including the empty ones.** A chart fed only
        the days that had rows draws a line through the gaps and turns three
        sign-ups in a month into a steady climb. Filling here rather than in
        the client keeps one description of the window.

        Returned as `[{"date": "2026-09-18", "count": 3}, ...]` — a string date
        because this crosses JSON, where the alternative is an instant the
        reader has to re-truncate to a day.
        """
        try:
            since = (
                datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(days=days - 1)
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            rows = (
                self.session.query(
                    func.date(UserModel.created_at).label("day"),
                    func.count(UserModel.id),
                )
                .filter(UserModel.created_at >= since)
                .group_by(func.date(UserModel.created_at))
                .all()
            )
            counted = {str(day): int(total) for day, total in rows}

            return [
                {
                    "date": str((since + timedelta(days=offset)).date()),
                    "count": counted.get(str((since + timedelta(days=offset)).date()), 0),
                }
                for offset in range(days)
            ]
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def countSanctioned(self) -> dict[str, int]:
        """Accounts under each profile sanction, and under both.

        Separate numbers rather than one total: a reset username and a blocked
        picture are different decisions about different problems, and an
        account carrying both is the one worth looking at.
        """
        try:
            row = self.session.query(
                func.count(UserModel.id).filter(UserModel.must_change_username.is_(True)),
                func.count(UserModel.id).filter(UserModel.picture_blocked.is_(True)),
                func.count(UserModel.id).filter(
                    UserModel.must_change_username.is_(True),
                    UserModel.picture_blocked.is_(True),
                ),
            ).one()
            return {
                "mustChangeUsername": int(row[0] or 0),
                "pictureBlocked": int(row[1] or 0),
                "both": int(row[2] or 0),
            }
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def countBans(self) -> dict[str, int]:
        """Banned accounts, split by whether the ban ends.

        `banned_until` NULL on a banned row means permanent — the column is
        overloaded exactly as migration `20260911_02` describes — so this is
        the one place the overload has to be read carefully rather than
        counted as "has a date".
        """
        try:
            banned = config.STATUS_CODES["banned"]
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            row = self.session.query(
                func.count(UserModel.id).filter(UserModel.status == banned),
                func.count(UserModel.id).filter(
                    UserModel.status == banned, UserModel.banned_until.is_(None)
                ),
                # Already expired but still flagged: the ban lifts itself at the
                # next sign-in, so this is the backlog of accounts nobody has
                # tried to use since their suspension ran out.
                func.count(UserModel.id).filter(
                    UserModel.status == banned, UserModel.banned_until < now
                ),
            ).one()
            return {
                "total": int(row[0] or 0),
                "permanent": int(row[1] or 0),
                "expired": int(row[2] or 0),
            }
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def countExpiredDeleted(self, graceDays: int) -> int:
        """How many accounts are past their purge date and still here.

        `findExpiredDeleted` answers the same question by returning the ids;
        this one is for the board, which wants the number and nothing else.
        A non-zero value here means `purge-accounts` has stopped running —
        the failure `docs/TODO.md` calls invisible from outside, because a
        deleted account past its window answers "not found" either way.
        """
        try:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=graceDays)
            return (
                self.session.query(UserModel.id)
                .filter(
                    UserModel.status == config.STATUS_CODES["deleted"],
                    UserModel.deleted_at.isnot(None),
                    UserModel.deleted_at < cutoff,
                )
                .count()
            )
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def findExpiredDeleted(self, graceDays: int) -> list[str]:
        """IDs of soft-deleted accounts whose grace window has closed.

        A deleted row with no `deleted_at` is not returned: the timestamp is the
        only evidence of when the window opened, and destroying a row on a guess
        is not a mistake that can be walked back.

        Args:
            graceDays (int): days a deleted account is kept before purging

        Returns:
            list[str]: user IDs eligible for permanent deletion
        """
        try:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=graceDays)

            rows = (
                self.session.query(UserModel.id)
                .filter(UserModel.status == config.STATUS_CODES["deleted"])
                .filter(UserModel.deleted_at.isnot(None))
                .filter(UserModel.deleted_at <= cutoff)
                .all()
            )

            return [row[0] for row in rows]
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def purge(self, id: str) -> bool:
        """Permanently delete a user row.

        Everything owned by the account goes with it, through the ON DELETE
        actions added in migration `20260901_01` — streaks, friendships, chats
        and their messages, user_badges, refresh and device tokens. Audit log
        entries survive with a null catalyst, which is what keeps a record that
        the deletion happened.

        Args:
            id (str): User ID

        Returns:
            bool: True when the row was removed
        """
        try:
            userModel = self.findById(id, returnModel=True)

            self.session.delete(userModel)
            self.session.commit()

            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
