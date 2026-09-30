from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from api.dependencies.auth import getAdminUser, getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.consentService import ConsentService
from domain.services.exportService import ExportService
from domain.services.friendshipService import FriendshipService
from domain.services.noticeService import NoticeService
from domain.services.postService import PostService
from domain.services.userService import UserService
from schemas.consentSchemas import (
    ConsentAcceptRequest,
    ConsentRecord,
    ConsentStatusResponse,
    ConsentWithdrawResponse,
)
from schemas.friendshipSchemas import FriendshipResponse
from schemas.noticeSchemas import NoticeResponse, WarnRequest
from schemas.postSchemas import PostPageResponse
from schemas.userSchemas import (
    MeResponse,
    UserResponse,
    UserListResponse,
    ProfileUpdateRequest,
    SanctionRequest,
    SanctionResponse,
    UserStatsResponse,
    SuspendRequest,
    SuspensionResponse,
)
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from domain.entities.user import User
from security.limiter import limiter
from typing import Optional, Union



router = APIRouter(prefix="/users", tags=["Users"])


# ── /me ──────────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get my profile",
    description=(
        "Returns the full private profile of the authenticated user, including "
        "any moderation sanction on the account (`must_change_username`, "
        "`picture_blocked`). Those two are on this route and never on "
        "`GET /users/{id}`: a sanction is between the account and moderation, "
        "and a flag readable from a public profile is a label other users can "
        "see."
    )
)
@limiter.limit("60/minute")
def getMyProfile(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        user = service.getProfile(currentUserId)

        me = MeResponse.model_validate(user)

        # Composed here rather than on the entity: `User` is a domain object
        # shared with the public profile, and what an account still owes a
        # signature on is private to it. One query — `summary`, not `status`,
        # which would also fetch the whole history for a route that is called
        # on every app open.
        consents = ConsentService(db).summary(currentUserId)
        me.pending_consents = consents["pending"]
        me.health_data_consent = consents["healthDataConsent"]

        return me
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/me",
    response_model=MeResponse,
    summary="Update my profile",
    description=(
        "Updates allowed fields for the authenticated user. "
        "Only `username` and `profilePicture` can be changed here. "
        "Email changes require a separate verification flow. "
        "Status can never be changed via this endpoint.\n\n"
        "Two moderation sanctions meet this route. Setting a `username` clears "
        "`must_change_username` — choosing a name is what lifts it, and nothing "
        "else does. Setting a `profilePicture` on an account whose picture is "
        "blocked is refused with a 403 whose detail says so, or the sanction would "
        "last exactly as long as it takes to open the edit screen."
    )
)
@limiter.limit("10/minute")
def updateMyProfile(
    request: Request,
    body: ProfileUpdateRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        user = service.updateProfile(currentUserId, body.username, body.profile_picture)
        return MeResponse.model_validate(user)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── consent ───────────────────────────────────────────────────────────────────
#
# Declared above `/{userId}` so the literal paths are matched first. FastAPI
# resolves in declaration order and `/me/consents` has two segments against that
# route's one, so there is no collision today — but `/{userId}/consents` is
# exactly the kind of route somebody adds later, and the order is what keeps
# that from silently shadowing these.

@router.get(
    "/me/consents",
    response_model=ConsentStatusResponse,
    summary="What I have agreed to",
    description=(
        "Every consent this account ever gave — terms of use, privacy policy, "
        "and the separate consent to hold recovery data — with the version that "
        "was live at the time and, where it applies, when it was withdrawn. "
        "Withdrawn records are kept and returned: they are the evidence the "
        "withdrawal was honoured.\n\n"
        "`versions` is what an account is asked to accept today, and `pending` "
        "is the difference between the two. A non-empty `pending` means the app "
        "shows the consent screen and nothing else."
    )
)
@limiter.limit("30/minute")
def getMyConsents(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        status = ConsentService(db).status(currentUserId)
        return ConsentStatusResponse(
            versions=status["versions"],
            consents=[ConsentRecord.model_validate(c) for c in status["consents"]],
            pending=status["pending"],
            health_data_consent=status["healthDataConsent"]
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/me/consents",
    response_model=ConsentStatusResponse,
    status_code=201,
    summary="Record my agreement to one or more documents",
    description=(
        "Writes one record per document, stamped with the version that is live "
        "now. The body names documents and **never** a version: a client able "
        "to say which revision it was agreeing to could record agreement to a "
        "text it never displayed.\n\n"
        "Append-only. Accepting a new version does not overwrite the record of "
        "the old one, and accepting the same version twice — two taps on a slow "
        "connection — writes a second row rather than failing."
    )
)
@limiter.limit("20/minute")
def acceptConsents(
    request: Request,
    body: ConsentAcceptRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ConsentService(db)
        service.accept(currentUserId, list(body.documents))

        status = service.status(currentUserId)
        return ConsentStatusResponse(
            versions=status["versions"],
            consents=[ConsentRecord.model_validate(c) for c in status["consents"]],
            pending=status["pending"],
            health_data_consent=status["healthDataConsent"]
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.delete(
    "/me/consents/health",
    response_model=ConsentWithdrawResponse,
    summary="Withdraw consent to hold my recovery data",
    description=(
        "Turns the streak tracker off and **deletes every streak** — the active "
        "one, the closed history and the personal record. There is no grace "
        "window and no undo: a 30-day shadow copy of data someone asked to be "
        "rid of is the thing they asked to be rid of, and that is the difference "
        "between this and deleting an account.\n\n"
        "The account itself is untouched and keeps working — friends, chats and "
        "badges are unaffected, which is the whole reason this consent is "
        "separate from the terms. Giving it again is `POST /users/me/consents` "
        "with `health_data`, and starts from zero.\n\n"
        "The consent record survives, stamped with the moment it ended. "
        "Idempotent: nothing in force answers `withdrawn: false`."
    )
)
@limiter.limit("5/minute")
def withdrawHealthDataConsent(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        result = ConsentService(db).withdrawHealthData(currentUserId)
        return ConsentWithdrawResponse(
            withdrawn=result["withdrawn"],
            streaks_deleted=result["streaksDeleted"]
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── data export ───────────────────────────────────────────────────────────────

@router.get(
    "/me/export",
    summary="Download everything you hold about me",
    description=(
        "The whole account as one JSON document: profile, consent history, "
        "streaks, friendships, badges, device registrations, moderation notices, "
        "the reports this account filed, its activity log, and its conversations "
        "**including the messages the other person sent** — a thread with one "
        "side removed is not a record of a conversation.\n\n"
        "Three things are left out on purpose, and the file says so in `notes`: "
        "reports filed *about* this account and the material behind them (the "
        "promise that a reported user is never told who complained is what makes "
        "reporting usable, and a file that gets forwarded is a bad place to break "
        "it), the identity of accounts this user reported, and push tokens, which "
        "are credentials for a device.\n\n"
        "Synchronous, because one account's data is small and there is no email "
        "service to deliver a link from a job. A section that fails to build "
        "comes back `null` and is named in `incomplete`, so a partial export "
        "says which part is missing instead of looking empty."
    )
)
@limiter.limit("6/hour")
def exportMyData(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        return ExportService(db).exportFor(currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── public profile ────────────────────────────────────────────────────────────

@router.get(
    "/{userId}",
    response_model=UserResponse,
    summary="Get a user's public profile",
    description=(
        "Returns a user's public profile. "
        "Blocked users cannot view the profile of their blocker (§3.3)."
    )
)
@limiter.limit("60/minute")
def getPublicProfile(
    userId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        user = service.getPublicProfile(currentUserId, userId)
        return UserResponse.model_validate(user)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/{userId}/stats",
    response_model=UserStatsResponse,
    summary="Get a user's public activity numbers",
    description=(
        "Active-streak days and badges held, for friends only. A non-friend "
        "gets `visible=false` with no numbers — the same answer a stranger's "
        "profile shows in the app. Blocked and deleted accounts 403/404 exactly "
        "as `GET /users/{userId}` does."
    )
)
@limiter.limit("60/minute")
def getPublicStats(
    userId: str,
    request: Request,
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getCurrentUser)
):
    # getDb, not getDbWithRLS: the streak and user-badge policies are owner-only,
    # so an RLS session scoped to the caller would read nothing for anyone else
    # and every friend would look like they had no activity. The friendship check
    # inside getPublicStats is what authorises the read.
    try:
        service = UserService(db)
        return UserStatsResponse(**service.getPublicStats(currentUserId, userId))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/{userId}/posts",
    response_model=PostPageResponse,
    summary="Read one user's posts",
    description=(
        "The posts on a profile, newest first, as the caller may see them: "
        "`friends` posts only for an accepted friend, nothing at all across a "
        "block or from an account that is not enabled — an empty page, not an "
        "error. Keyset-paginated like `GET /posts`."
    )
)
@limiter.limit("60/minute")
def getUserPosts(
    userId: str,
    request: Request,
    cursor: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    # NoHarmException reaches main.py unconverted, as in postRoutes: an
    # INVALID_CURSOR is worth keeping as a code.
    return PostService(db).byAuthor(currentUserId, userId, cursor, limit)


# ── blocking anyone ───────────────────────────────────────────────────────────

@router.post(
    "/{userId}/block",
    response_model=FriendshipResponse,
    summary="Block a user",
    description=(
        "Blocks an account whether or not you are friends — what the Community "
        "tab needs, since a stranger can comment on you. Moves an existing "
        "friendship to blocked, or creates the row. Idempotent.\n\n"
        "Each side then disappears for the other: posts, comments, profile, "
        "friend requests and chats. The blocked account is not notified. Only "
        "whoever blocked can unblock (`blocked_by` on the response)."
    )
)
@limiter.limit("10/minute")
def blockUser(
    userId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = FriendshipService(db)
        return service.enrich(service.blockUser(currentUserId, userId))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.delete(
    "/{userId}/block",
    response_model=FriendshipResponse,
    summary="Unblock a user",
    description=(
        "Lifts a block you placed. 403 when the other account placed it — the "
        "blocked side cannot unblock itself. 404 when there is no block."
    )
)
@limiter.limit("10/minute")
def unblockUser(
    userId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = FriendshipService(db)
        return service.enrich(service.unblockUser(currentUserId, userId))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── admin / internal ──────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=Union[PaginatedResponse[User], UserListResponse],
    summary="Get all users",
    description=(
        "Returns the user directory. Pass `search` with a full username or email "
        "to look one person up — matches are exact, since both columns are "
        "encrypted and only their hashes are queryable (§5). "
        "Deleted, banned and blocked accounts are never listed."
    )
)
@limiter.limit("30/minute")
def getAllUsers(
    request: Request,
    search: Optional[str] = None,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)

        if paginated:
            if search:
                return service.search(search, paginatedParams)
            return service.findAll(paginatedParams)

        users = service.search(search) if search else service.findAll()
        return UserListResponse(users=[UserResponse.model_validate(u) for u in users], total=len(users))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/{userId}/warn",
    response_model=NoticeResponse,
    status_code=201,
    summary="Warn an account (admin)",
    description=(
        "Sends a warning. **Nothing about the account changes** — no ban, no "
        "limit — and that is the point: the rung between doing nothing and "
        "banning someone was missing, so every offence short of a ban got "
        "silence.\n\n"
        "The user sees it the next time they open the app and acknowledges it. "
        "It names the conduct, never the reporter: the promise that a reported "
        "user is never told who complained is what makes reports fileable.\n\n"
        "`self_harm` is refused here (400 `NOT_A_WARNING`). A report about "
        "someone's safety is usually a frightened friend, and answering it with "
        "a telling-off is the worst available move. Restricted to "
        "ADMIN_USER_IDS; any other caller gets a 404."
    )
)
@limiter.limit("20/minute")
def warnUser(
    userId: str,
    request: Request,
    body: WarnRequest,
    # `getDb`: tb_12's insert policy only passes for a session with no RLS
    # context, which is what keeps notices something only moderation writes.
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = NoticeService(db)
        return service.warn(userId, body.reason, currentUserId, body.message)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{userId}/suspend",
    response_model=SuspensionResponse,
    status_code=200,
    summary="Suspend an account for a fixed time (admin)",
    description=(
        "Bans an account until a date — `days: null` bans it permanently. A "
        "suspension is the same `banned` status as a permanent ban plus an end "
        "date, and it lifts itself at the first sign-in afterwards; nothing has "
        "to run on a schedule.\n\n"
        "Separate from resolving a report on purpose: closing a complaint and "
        "punishing an account are two decisions, and a queue where one implies "
        "the other is a queue moderators stop reading. Restricted to "
        "ADMIN_USER_IDS; any other caller gets a 404.\n\n"
        "To end a suspension early, set the account back to enabled with "
        "`PUT /users/{id}/status/1` — that clears the date with it."
    )
)
@limiter.limit("10/minute")
def suspendUser(
    userId: str,
    request: Request,
    body: SuspendRequest,
    # `getDb` for the same reason as the status route below: the tb_0 UPDATE
    # policy is owner-only, so an admin acting on someone else under an RLS
    # context would match no row.
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = UserService(db)
        suspended = service.suspend(userId, body.days, currentUserId)

        # Written beside the ban so the person is not guessing what happened
        # when they come back. Best effort: a suspension whose notice failed to
        # save is still a suspension, and failing here would leave the
        # moderator unsure which half landed.
        NoticeService(db).noticeOfSuspension(
            userId, body.reason or "other", currentUserId, body.message
        )

        return suspended
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{userId}/username/reset",
    response_model=SanctionResponse,
    status_code=200,
    summary="Reset an abusive username (admin)",
    description=(
        "Takes the username away and makes the account choose another. The "
        "answer to an impersonating or abusive handle, where a ban is far too "
        "much and a warning far too little — a warning leaves the name exactly "
        "where it is.\n\n"
        "The account is renamed **immediately** to a neutral generated handle "
        "(`user_xxxxxxxx`) rather than being asked to fix it: the harm is the "
        "name being readable, and a flag alone would leave it on every friend "
        "list and chat header until the user next signed in. The old name "
        "survives in the report's evidence and in the audit log, which is where "
        "a moderator should have to look for it.\n\n"
        "`must_change_username` then makes the app ask for a real name before "
        "anything else; setting one through `PUT /users/me` is what lifts it. "
        "Nothing else changes — the account is not banned or limited and keeps "
        "its streak, friends and history. Restricted to ADMIN_USER_IDS; any "
        "other caller gets a 404."
    )
)
@limiter.limit("10/minute")
def resetUsername(
    userId: str,
    request: Request,
    body: SanctionRequest,
    # `getDb` for the same reason as the routes below: the tb_0 UPDATE policy
    # is owner-only, so an admin acting on someone else under an RLS context
    # would match no row.
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = UserService(db)
        sanctioned = service.forceUsernameChange(userId, currentUserId)

        # Best effort, like a suspension's notice: the rename screen already
        # tells the user what to do, and failing here would leave the moderator
        # unsure whether the rename landed.
        NoticeService(db).noticeOfForcedRename(
            userId, body.reason or "impersonation", currentUserId, body.message
        )

        return SanctionResponse.model_validate(sanctioned)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{userId}/picture/{blocked}",
    response_model=SanctionResponse,
    status_code=200,
    summary="Block or unblock a profile picture (admin)",
    description=(
        "`blocked` is `block` or `unblock`. Blocking removes the picture and "
        "refuses a new one until an admin lifts it.\n\n"
        "The flag is the half that matters. `AuthService._syncProfilePicture` "
        "refreshes the photo from the Google claim at every login, so clearing "
        "the column alone would undo itself the next time the user signed in — "
        "and `PUT /users/me` would undo it sooner than that.\n\n"
        "Unblocking restores nothing: the old picture is gone, and the next "
        "sign-in pulls whatever the Google account holds now, which was always "
        "the only copy. Restricted to ADMIN_USER_IDS; any other caller gets a "
        "404."
    )
)
@limiter.limit("10/minute")
def setPictureBlocked(
    userId: str,
    blocked: str,
    request: Request,
    body: SanctionRequest,
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    if blocked not in ("block", "unblock"):
        raise HTTPException(status_code=400, detail="Use 'block' or 'unblock'.")

    try:
        service = UserService(db)
        blocking = blocked == "block"
        sanctioned = service.setPictureBlocked(userId, blocking, currentUserId)

        # Only a block is worth telling someone about. Lifting one restores
        # nothing they can see, and a notice saying so reads as a second
        # sanction rather than the end of one.
        if blocking:
            NoticeService(db).noticeOfPictureBlock(
                userId, body.reason or "inappropriate", currentUserId, body.message
            )

        return SanctionResponse.model_validate(sanctioned)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{userId}/status/{status}",
    response_model=UserResponse,
    status_code=200,
    summary="Update a user status (admin)",
    description=(
        "Updates the status of an existing user. Admin action — creates audit log type=5. "
        "Restricted to the UIDs in ADMIN_USER_IDS; any other caller gets a 404. This is the "
        "route that bans, unbans and undeletes, so leaving it open to any signed-in user "
        "would let anyone lift their own ban."
    )
)
@limiter.limit("10/minute")
def updateUserStatus(
    status: int,
    userId: str,
    request: Request,
    # `getDb`, not `getDbWithRLS`: the RLS policy on tb_0 allows UPDATE only on
    # your own row, so an admin acting on someone else under an RLS context
    # would match no row and change nothing. Authorisation for this route is
    # `getAdminUser` — the allowlist — not the database policy.
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = UserService(db)
        updatedUser = service.updateStatus(userId, status, requestingUserId=currentUserId)
        return updatedUser
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.delete(
    "/me",
    status_code=200,
    summary="Delete my account",
    description="Soft-deletes the authenticated user's own account (sets status = deleted). Only a user can delete their own account (§1.4)."
)
@limiter.limit("5/minute")
def deleteUser(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        return service.delete(currentUserId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
