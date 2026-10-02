from infrastructure.database.repositories.postRepository import PostRepository
from infrastructure.database.repositories.postCommentRepository import PostCommentRepository
from infrastructure.database.repositories.userRepository import UserRepository
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from infrastructure.database.cursorUtils import decodeCursor, encodeCursor
from infrastructure.external import fcmService
from domain.entities.post import Post, PostComment, VISIBILITIES
from domain.services.consentService import ConsentService, REQUIRED_DOCUMENTS
from domain.services.noticeService import NoticeService, POST_REMOVED, COMMENT_REMOVED
from schemas.friendshipSchemas import FriendUserInfo
from schemas.postSchemas import (
    CommentPageResponse,
    CommentResponse,
    LikeResponse,
    ModeratedContentResponse,
    PostPageResponse,
    PostResponse,
)
from security.rateLimiter import ContentQuotaLimiter
from security.sanitizer import Sanitizer
from exceptions.baseExceptions import NoHarmException
from websocket import emitter
from core.config import config
from core.database import Database

from datetime import datetime, timedelta, timezone
from typing import Optional
from core.auditTypes import AuditType


# 17 is a moderator taking a post or comment down, 18 is putting one back. Two
# types for the reason consent has two: the question asked of the log is nearly
# always one direction.
_AUDIT_CONTENT_REMOVED = AuditType.CONTENT_REMOVED
_AUDIT_CONTENT_RESTORED = AuditType.CONTENT_RESTORED

# Module-level like `reportService._reportLimiter`: no per-request state, and
# the tests patch these names.
_postQuota = ContentQuotaLimiter("post", config.POST_MAX_PER_DAY)
_commentQuota = ContentQuotaLimiter("comment", config.COMMENT_MAX_PER_DAY)


def _utcNow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PostService:
    """The Community tab: posts, their comments and likes, and their moderation.

    ## Visibility is decided here, not by RLS

    A post is visible to a viewer when it is up, its author's account is
    enabled, neither has blocked the other, and it was written for the
    community — or the viewer is the author or an accepted friend. Comments add
    the same author and block rules for whoever wrote each one. The rules live
    as SQL in `postRepository` (`postVisibleTo`) so every path — feed, single
    post, like, comment, report — asks the same question.

    **Invisible is 404, never 403.** A 403 would confirm the post exists, and
    "this person blocked you" is exactly what that would leak.

    ## Writing is gated twice

    An account must be `enabled` (the unverified-provider hole, same as
    `REPORTER_NOT_ELIGIBLE`) and must have accepted the current terms and
    privacy policy. The second is normally the app's ConsentGate, but the new
    terms are what license showing a post to other people, so the API does not
    take a post from an account that has not agreed to them. Health-data
    consent is not required: a post is not the tracker.
    """

    def __init__(self, db):
        self.database: Database = db
        self.postRepository = PostRepository(self.database)
        self.commentRepository = PostCommentRepository(self.database)
        self.userRepository = UserRepository(self.database)
        self.auditRepository = AuditLogsRepository(self.database)

    def _logAudit(self, actionType: int, catalystId: str, description: str) -> None:
        try:
            entry = AuditLogsModel(
                type=actionType,
                catalyst_id=catalystId,
                catalyst=None,
                description=description
            )
            self.auditRepository.create(entry)
        except Exception:
            pass

    # ── response assembly ─────────────────────────────────────────────────────

    def _authors(self, userIds) -> dict[str, FriendUserInfo]:
        ids = list({str(uid) for uid in userIds if uid})
        if not ids:
            return {}
        return {
            u.id: FriendUserInfo(id=u.id, username=u.username, profile_picture=u.profile_picture)
            for u in self.userRepository.findManyByIds(ids)
        }

    def _postResponses(self, posts: list[Post], viewerId: str) -> list[PostResponse]:
        """Posts plus their counts, in four grouped queries for the whole page."""
        if not posts:
            return []

        ids = [post.id for post in posts]
        likes = self.postRepository.likeCounts(ids)
        comments = self.commentRepository.countsByPosts(ids)
        liked = self.postRepository.likedBy(viewerId, ids)
        authors = self._authors(post.author_id for post in posts)

        responses = []
        for post in posts:
            author = authors.get(str(post.author_id))
            if author is None:
                # Purged between the two reads. Its post went with it.
                continue
            responses.append(PostResponse(
                id=post.id,
                author=author,
                content=post.content,
                visibility=post.visibility,
                like_count=likes.get(post.id, 0),
                comment_count=comments.get(post.id, 0),
                liked_by_me=post.id in liked,
                is_mine=str(post.author_id) == str(viewerId),
                created_at=post.created_at,
            ))
        return responses

    def _commentResponses(self, comments: list[PostComment], post: Post, viewerId: str) -> list[CommentResponse]:
        authors = self._authors(comment.author_id for comment in comments)
        ownsPost = str(post.author_id) == str(viewerId)

        responses = []
        for comment in comments:
            author = authors.get(str(comment.author_id))
            if author is None:
                continue
            mine = str(comment.author_id) == str(viewerId)
            responses.append(CommentResponse(
                id=comment.id,
                post_id=comment.post_id,
                author=author,
                content=comment.content,
                is_mine=mine,
                can_delete=mine or ownsPost,
                created_at=comment.created_at,
            ))
        return responses

    @staticmethod
    def _nextCursor(rows: list, limit: int) -> tuple[list, Optional[str]]:
        """Split the `limit + 1` rows a repository returns into a page and a cursor."""
        if len(rows) <= limit:
            return rows, None
        page = rows[:limit]
        last = page[-1]
        return page, encodeCursor(last.created_at, last.id)

    # ── reads ─────────────────────────────────────────────────────────────────

    def feed(self, viewerId: str, scope: str, cursor: Optional[str], limit: int) -> PostPageResponse:
        """One page of the `friends` or `community` feed, newest first."""
        if scope not in VISIBILITIES:
            raise NoHarmException(statusCode=400, errorCode="INVALID_SCOPE", message="Unknown feed.")

        rows = self.postRepository.feed(viewerId, scope, decodeCursor(cursor), limit)
        page, nextCursor = self._nextCursor(rows, limit)
        return PostPageResponse(posts=self._postResponses(page, viewerId), next_cursor=nextCursor)

    def byAuthor(self, viewerId: str, authorId: str, cursor: Optional[str], limit: int) -> PostPageResponse:
        """One account's posts as this viewer may see them.

        An author the viewer cannot see — blocked either way, banned, deleted —
        is an empty list, not an error: the profile route is where "this
        person is not available" gets said.
        """
        rows = self.postRepository.byAuthor(viewerId, authorId, decodeCursor(cursor), limit)
        page, nextCursor = self._nextCursor(rows, limit)
        return PostPageResponse(posts=self._postResponses(page, viewerId), next_cursor=nextCursor)

    def get(self, postId, viewerId: str) -> PostResponse:
        post = self.postRepository.findVisible(postId, viewerId)
        return self._postResponses([post], viewerId)[0]

    def comments(self, postId, viewerId: str, cursor: Optional[str], limit: int) -> CommentPageResponse:
        """A post's comments, oldest first. 404 when the post is not visible."""
        post = self.postRepository.findVisible(postId, viewerId)
        rows = self.commentRepository.thread(post.id, viewerId, decodeCursor(cursor), limit)
        page, nextCursor = self._nextCursor(rows, limit)
        return CommentPageResponse(comments=self._commentResponses(page, post, viewerId), next_cursor=nextCursor)

    def visiblePost(self, postId, viewerId: str) -> Post:
        return self.postRepository.findVisible(postId, viewerId)

    def visibleComment(self, commentId, viewerId: str) -> PostComment:
        return self.commentRepository.findVisible(commentId, viewerId)

    # ── the gates on writing ──────────────────────────────────────────────────

    def _assertCanWrite(self, userId: str, quota: ContentQuotaLimiter, quotaError: str):
        """Quota, account standing, consent — cheapest refusal first.

        Returns the writer's account, which the caller needs for its name.
        """
        allowed, retryAfter = quota.check(userId)
        if not allowed:
            retryAt = _utcNow() + timedelta(seconds=retryAfter)
            raise NoHarmException(
                statusCode=429,
                errorCode=quotaError,
                message="You have reached today's limit. Try again later.",
                details={"retryAt": retryAt.isoformat() + "Z"}
            )

        try:
            user = self.userRepository.findById(userId)
        except NoHarmException:
            user = None

        if user is None or user.status != config.STATUS_CODES["enabled"]:
            raise NoHarmException(
                statusCode=403,
                errorCode="POSTER_NOT_ELIGIBLE",
                message="Verify your account before posting."
            )

        pending = [doc for doc in ConsentService(self.database).pending(userId) if doc in REQUIRED_DOCUMENTS]
        if pending:
            raise NoHarmException(
                statusCode=403,
                errorCode="CONSENT_REQUIRED",
                message="Accept the current terms and privacy policy first.",
                details={"pending": pending}
            )

        return user

    @staticmethod
    def _clean(content: str, what: str) -> str:
        """Sanitised and trimmed. Empty after sanitising is refused like empty."""
        cleaned = (Sanitizer.cleanHtml(content) or "").strip()
        if not cleaned:
            raise NoHarmException(
                statusCode=422,
                errorCode="VALIDATION_ERROR",
                message=f"The {what} is empty."
            )
        return cleaned

    # ── posts ─────────────────────────────────────────────────────────────────

    def create(self, authorId: str, content: str, visibility: str) -> PostResponse:
        if visibility not in VISIBILITIES:
            raise NoHarmException(statusCode=400, errorCode="INVALID_VISIBILITY", message="Unknown audience.")

        self._assertCanWrite(authorId, _postQuota, "POST_QUOTA_EXCEEDED")

        created = self.postRepository.create(Post(
            author_id=authorId,
            content=self._clean(content, "post"),
            visibility=visibility,
            status=config.STATUS_CODES["enabled"],
        ))

        # Charged once the row exists, never for a refusal.
        _postQuota.spend(authorId)

        return self._postResponses([created], authorId)[0]

    def delete(self, postId, userId: str) -> None:
        """The author's delete — real, with its comments and likes.

        Someone else's post is a 404 whether or not they can see it: saying
        "not yours" would confirm it exists.
        """
        post = self.postRepository.findById(postId)
        if str(post.author_id) != str(userId):
            raise NoHarmException(statusCode=404, errorCode="POST_NOT_FOUND", message="Post not found.")

        self.postRepository.delete(post.id)

    # ── likes ─────────────────────────────────────────────────────────────────

    def like(self, postId, userId: str) -> LikeResponse:
        """Idempotent: two likes are one. No notification, ever (D6)."""
        post = self.postRepository.findVisible(postId, userId)
        self.postRepository.like(post.id, userId)
        return LikeResponse(liked=True, like_count=self.postRepository.likeCounts([post.id]).get(post.id, 0))

    def unlike(self, postId, userId: str) -> LikeResponse:
        post = self.postRepository.findVisible(postId, userId)
        self.postRepository.unlike(post.id, userId)
        return LikeResponse(liked=False, like_count=self.postRepository.likeCounts([post.id]).get(post.id, 0))

    # ── comments ──────────────────────────────────────────────────────────────

    def comment(self, postId, authorId: str, content: str) -> CommentResponse:
        post = self.postRepository.findVisible(postId, authorId)
        author = self._assertCanWrite(authorId, _commentQuota, "COMMENT_QUOTA_EXCEEDED")

        created = self.commentRepository.create(PostComment(
            post_id=post.id,
            author_id=authorId,
            content=self._clean(content, "comment"),
            status=config.STATUS_CODES["enabled"],
        ))

        _commentQuota.spend(authorId)

        if str(post.author_id) != str(authorId):
            emitter.notifyPostComment(post.author_id, post.id, created.id, authorId, author.username)
            # Who, never what: the text would travel through FCM and APNs, and
            # the privacy policy declares that for messages only.
            fcmService.sendPushToUser(
                str(post.author_id),
                "New comment",
                f"{author.username} commented on your post",
                category="community"
            )

        return self._commentResponses([created], post, authorId)[0]

    def deleteComment(self, postId, commentId, userId: str) -> None:
        """Delete a comment — its author, or the author of the post (D7).

        The author of a comment may delete it even from a post they can no
        longer see: deleting what you wrote does not depend on the other
        person still letting you read their post.
        """
        comment = self.commentRepository.findById(commentId)
        if str(comment.post_id) != str(postId):
            raise NoHarmException(statusCode=404, errorCode="COMMENT_NOT_FOUND", message="Comment not found.")

        if str(comment.author_id) != str(userId):
            post = self.postRepository.findById(postId)
            if str(post.author_id) != str(userId):
                raise NoHarmException(statusCode=404, errorCode="COMMENT_NOT_FOUND", message="Comment not found.")

        self.commentRepository.delete(comment.id)

    # ── moderation ────────────────────────────────────────────────────────────

    def _moderated(self, row, kind: str) -> ModeratedContentResponse:
        return ModeratedContentResponse(
            id=row.id,
            kind=kind,
            author_id=row.author_id,
            status=row.status,
            removed_at=row.removed_at,
        )

    def _commentOf(self, postId, commentId) -> PostComment:
        comment = self.commentRepository.findById(commentId)
        if str(comment.post_id) != str(postId):
            raise NoHarmException(statusCode=404, errorCode="COMMENT_NOT_FOUND", message="Comment not found.")
        return comment

    def removePost(
        self,
        postId,
        adminUserId: str,
        reason: str,
        message: Optional[str] = None,
        reportId=None
    ) -> ModeratedContentResponse:
        """Take a post down for everyone, its author included.

        A status, not a delete, so an appeal can restore it; the purge job
        deletes it after REMOVED_CONTENT_RETENTION_DAYS. The author gets a
        notice naming the conduct and quoting the start of the post.

        Removing is neither resolving the report nor sanctioning the account —
        three decisions, kept apart for the same reason as "Resolving never
        changes an account". A post the author already deleted is a 404, and
        the evidence is still in the report.

        Removing something already removed changes nothing and sends no second
        notice.
        """
        post = self.postRepository.findById(postId)
        if post.status == config.STATUS_CODES["blocked"]:
            return self._moderated(post, "post")

        removed = self.postRepository.setRemoved(post.id, True)

        NoticeService(self.database).noticeOfContentRemoval(
            str(post.author_id), POST_REMOVED, reason, adminUserId, post.content, message
        )
        self._logAudit(
            _AUDIT_CONTENT_REMOVED,
            adminUserId,
            f"Post {post.id} by {post.author_id} removed for {reason}"
            + (f" (report {reportId})" if reportId else "")
        )

        return self._moderated(removed, "post")

    def removeComment(
        self,
        postId,
        commentId,
        adminUserId: str,
        reason: str,
        message: Optional[str] = None,
        reportId=None
    ) -> ModeratedContentResponse:
        comment = self._commentOf(postId, commentId)
        if comment.status == config.STATUS_CODES["blocked"]:
            return self._moderated(comment, "comment")

        removed = self.commentRepository.setRemoved(comment.id, True)

        NoticeService(self.database).noticeOfContentRemoval(
            str(comment.author_id), COMMENT_REMOVED, reason, adminUserId, comment.content, message
        )
        self._logAudit(
            _AUDIT_CONTENT_REMOVED,
            adminUserId,
            f"Comment {comment.id} by {comment.author_id} removed for {reason}"
            + (f" (report {reportId})" if reportId else "")
        )

        return self._moderated(removed, "comment")

    def restorePost(self, postId, adminUserId: str) -> ModeratedContentResponse:
        """Put a removed post back — what an upheld appeal does."""
        post = self.postRepository.findById(postId)
        if post.status != config.STATUS_CODES["blocked"]:
            return self._moderated(post, "post")

        restored = self.postRepository.setRemoved(post.id, False)
        self._logAudit(_AUDIT_CONTENT_RESTORED, adminUserId, f"Post {post.id} by {post.author_id} restored")

        return self._moderated(restored, "post")

    def restoreComment(self, postId, commentId, adminUserId: str) -> ModeratedContentResponse:
        comment = self._commentOf(postId, commentId)
        if comment.status != config.STATUS_CODES["blocked"]:
            return self._moderated(comment, "comment")

        restored = self.commentRepository.setRemoved(comment.id, False)
        self._logAudit(_AUDIT_CONTENT_RESTORED, adminUserId, f"Comment {comment.id} by {comment.author_id} restored")

        return self._moderated(restored, "comment")
