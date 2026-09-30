from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session
from typing import Literal, Optional
from uuid import UUID

from api.dependencies.auth import getAdminUser, getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.postService import PostService
from schemas.postSchemas import (
    CommentCreateRequest,
    CommentPageResponse,
    CommentResponse,
    LikeResponse,
    ModeratedContentResponse,
    PostCreateRequest,
    PostPageResponse,
    PostResponse,
    RemoveContentRequest,
)
from security.limiter import limiter


# NoHarmException is never converted to HTTPException in this file. The handler
# in main.py keeps `errorCode` and `details`, and the app needs both here: a 404
# is POST_NOT_FOUND or COMMENT_NOT_FOUND, a 403 is POSTER_NOT_ELIGIBLE or
# CONSENT_REQUIRED, and a 429 carries `details.retryAt`.
router = APIRouter(prefix="/posts", tags=["Posts"])


# ── feed ──────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=PostPageResponse,
    summary="Read a feed",
    description=(
        "Newest first, keyset-paginated: pass `next_cursor` back as `cursor`. "
        "A cursor rather than page numbers because the feed changes while it is "
        "read — a new post at the top would otherwise repeat the last item of "
        "one page at the top of the next.\n\n"
        "- `friends` — my posts and my accepted friends', whatever audience each was written for\n"
        "- `community` — every `community` post I may see, plus my own\n\n"
        "Never shown: removed posts, posts by accounts that are not enabled, and "
        "posts by anyone I blocked or who blocked me."
    )
)
@limiter.limit("60/minute")
def getFeed(
    request: Request,
    scope: Literal["friends", "community"] = "friends",
    cursor: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    return PostService(db).feed(currentUserId, scope, cursor, limit)


@router.post(
    "",
    response_model=PostResponse,
    status_code=201,
    summary="Publish a post",
    description=(
        "Text only, 1–1000 characters after trimming. No edit: delete and post "
        "again.\n\n"
        "- 403 `POSTER_NOT_ELIGIBLE` — the account is not enabled\n"
        "- 403 `CONSENT_REQUIRED` — the current terms or privacy policy are not "
        "accepted; `details.pending` names which\n"
        "- 429 `POST_QUOTA_EXCEEDED` — past POST_MAX_PER_DAY; `details.retryAt` says when"
    )
)
@limiter.limit("5/minute")
def createPost(
    request: Request,
    body: PostCreateRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    return PostService(db).create(currentUserId, body.content, body.visibility)


# ── one post ──────────────────────────────────────────────────────────────────

@router.get(
    "/{postId}",
    response_model=PostResponse,
    summary="Read a post",
    description="404 `POST_NOT_FOUND` when it does not exist *or* the caller may not see it — never 403."
)
@limiter.limit("60/minute")
def getPost(
    postId: UUID,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    return PostService(db).get(postId, currentUserId)


@router.delete(
    "/{postId}",
    status_code=204,
    summary="Delete my post",
    description=(
        "A real delete, with its comments and likes. Only the author; anyone "
        "else gets 404. If it was reported, the report kept its own copy."
    )
)
@limiter.limit("20/minute")
def deletePost(
    postId: UUID,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    PostService(db).delete(postId, currentUserId)
    return Response(status_code=204)


# ── likes ─────────────────────────────────────────────────────────────────────

@router.put(
    "/{postId}/like",
    response_model=LikeResponse,
    summary="Like a post",
    description=(
        "Idempotent — liking twice is one like, so a double tap cannot count "
        "twice. `like_count` in the answer is the truth to show. Likes never "
        "notify anyone."
    )
)
@limiter.limit("60/minute")
def likePost(
    postId: UUID,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    return PostService(db).like(postId, currentUserId)


@router.delete(
    "/{postId}/like",
    response_model=LikeResponse,
    summary="Take back a like",
    description="Idempotent, like the PUT."
)
@limiter.limit("60/minute")
def unlikePost(
    postId: UUID,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    return PostService(db).unlike(postId, currentUserId)


# ── comments ──────────────────────────────────────────────────────────────────

@router.get(
    "/{postId}/comments",
    response_model=CommentPageResponse,
    summary="Read a post's comments",
    description=(
        "Oldest first — a conversation reads in the order it was said. "
        "Comments by anyone the caller blocked, or who blocked the caller, are "
        "left out."
    )
)
@limiter.limit("60/minute")
def getComments(
    postId: UUID,
    request: Request,
    cursor: Optional[str] = None,
    limit: int = Query(30, ge=1, le=50),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    return PostService(db).comments(postId, currentUserId, cursor, limit)


@router.post(
    "/{postId}/comments",
    response_model=CommentResponse,
    status_code=201,
    summary="Comment on a post",
    description=(
        "1–500 characters after trimming. Same gates as posting, with "
        "`COMMENT_QUOTA_EXCEEDED` past COMMENT_MAX_PER_DAY. The post's author "
        "gets a `post_comment` socket event and a push in the `community` "
        "category — naming who commented, never what they wrote."
    )
)
@limiter.limit("20/minute")
def createComment(
    postId: UUID,
    request: Request,
    body: CommentCreateRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    return PostService(db).comment(postId, currentUserId, body.content)


@router.delete(
    "/{postId}/comments/{commentId}",
    status_code=204,
    summary="Delete a comment",
    description="The comment's author, or the author of the post. Anyone else gets 404."
)
@limiter.limit("20/minute")
def deleteComment(
    postId: UUID,
    commentId: UUID,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    PostService(db).deleteComment(postId, commentId, currentUserId)
    return Response(status_code=204)


# ── moderation (admin) ────────────────────────────────────────────────────────
#
# `getDb`, not `getDbWithRLS`: the UPDATE policies on tb_16 and tb_17 pass only
# for a session with no context, so no author can reverse a removal. The
# allowlist in `getAdminUser` is the authorisation, and it answers 404 to
# everyone else.

@router.put(
    "/{postId}/remove",
    response_model=ModeratedContentResponse,
    summary="Remove a post (admin)",
    description=(
        "Takes the post down for everyone, its author included, and sends the "
        "author a `post_removed` notice quoting its start. Kept for "
        "REMOVED_CONTENT_RETENTION_DAYS so an appeal can restore it.\n\n"
        "Neither resolves the report nor sanctions the account — those stay "
        "separate calls. 404 when the author already deleted it."
    )
)
@limiter.limit("20/minute")
def removePost(
    postId: UUID,
    request: Request,
    body: RemoveContentRequest,
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    return PostService(db).removePost(postId, currentUserId, body.reason, body.message, body.reportId)


@router.put(
    "/{postId}/restore",
    response_model=ModeratedContentResponse,
    summary="Restore a removed post (admin)",
    description="What an upheld appeal does. No notice is sent."
)
@limiter.limit("20/minute")
def restorePost(
    postId: UUID,
    request: Request,
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    return PostService(db).restorePost(postId, currentUserId)


@router.put(
    "/{postId}/comments/{commentId}/remove",
    response_model=ModeratedContentResponse,
    summary="Remove a comment (admin)",
    description="As removing a post, with a `comment_removed` notice."
)
@limiter.limit("20/minute")
def removeComment(
    postId: UUID,
    commentId: UUID,
    request: Request,
    body: RemoveContentRequest,
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    return PostService(db).removeComment(postId, commentId, currentUserId, body.reason, body.message, body.reportId)


@router.put(
    "/{postId}/comments/{commentId}/restore",
    response_model=ModeratedContentResponse,
    summary="Restore a removed comment (admin)"
)
@limiter.limit("20/minute")
def restoreComment(
    postId: UUID,
    commentId: UUID,
    request: Request,
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    return PostService(db).restoreComment(postId, commentId, currentUserId)
