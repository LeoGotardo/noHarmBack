from domain.entities.post import Post, VISIBILITY_COMMUNITY
from core.errorUtils import excLocation
from infrastructure.database.cursorUtils import Cursor
from infrastructure.database.models.baseModel import _utcnow
from infrastructure.database.models.friendshipModel import FriendshipModel
from infrastructure.database.models.postModel import PostModel
from infrastructure.database.models.postLikeModel import PostLikeModel
from infrastructure.database.models.userModel import UserModel
from exceptions.baseExceptions import NoHarmException

from core.database import Database
from core.config import config

from sqlalchemy import and_, exists, func, not_, or_, tuple_
from sqlalchemy.dialects.postgresql import insert as pgInsert

from datetime import datetime, timedelta, timezone
from typing import Optional


# ── visibility, as SQL ────────────────────────────────────────────────────────
#
# Every read path — the two feeds, a profile's posts, a single post, the check
# in front of a like or a comment, the report that names a post — goes through
# these, so "who can see this" is written once. Section 1 of
# docs/POSTS_PLAN.md is the rule; this is it as a WHERE clause.
#
# They run fine under the viewer's RLS context: tb_16 and tb_0 are readable by
# anyone, and the only tb_2 rows these ask about are ones the viewer is part of.

def pairHasStatus(otherColumn, viewerId: str, status: int):
    """EXISTS a friendship row in `status` between `otherColumn` and the viewer."""
    return exists().where(
        or_(
            and_(FriendshipModel.sender == otherColumn, FriendshipModel.reciver == viewerId),
            and_(FriendshipModel.sender == viewerId, FriendshipModel.reciver == otherColumn),
        ),
        FriendshipModel.status == status,
    )


def authorVisibleTo(authorColumn, viewerId: str):
    """Rules 2 and 3: the author's account is enabled and nobody blocked anybody.

    Applies to comment authors as well as post authors — a comment from someone
    you blocked does not appear under anybody's post for you.
    """
    return and_(
        exists().where(
            UserModel.id == authorColumn,
            UserModel.status == config.STATUS_CODES["enabled"],
        ),
        not_(pairHasStatus(authorColumn, viewerId, config.STATUS_CODES["blocked"])),
    )


def postVisibleTo(viewerId: str):
    """All four rules for a post: up, author in good standing, no block, audience."""
    return and_(
        PostModel.status == config.STATUS_CODES["enabled"],
        authorVisibleTo(PostModel.author_id, viewerId),
        or_(
            PostModel.visibility == VISIBILITY_COMMUNITY,
            PostModel.author_id == viewerId,
            pairHasStatus(PostModel.author_id, viewerId, config.STATUS_CODES["accepted"]),
        ),
    )


def _enabledUser(column):
    return exists().where(
        UserModel.id == column,
        UserModel.status == config.STATUS_CODES["enabled"],
    )


class PostRepository:
    """Posts (tb_16) and the likes on them (tb_18)."""

    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine


    def _toEntity(self, model: PostModel) -> Post:
        return Post(
            id=model.id,
            author_id=model.author_id,
            content=model.content,
            visibility=model.visibility,
            status=model.status,
            removed_at=model.removed_at,
            created_at=model.created_at,
            updated_at=model.updated_at
        )


    @staticmethod
    def _notFound() -> NoHarmException:
        # One answer for "does not exist" and "exists but not for you": a 403
        # would confirm the post is there.
        return NoHarmException(statusCode=404, errorCode="POST_NOT_FOUND", message="Post not found.")


    # ── writes ────────────────────────────────────────────────────────────────

    def create(self, post: Post) -> Post:
        try:
            model = PostModel(
                author_id=post.author_id,
                content=post.content,
                visibility=post.visibility,
                status=post.status
            )

            self.session.add(model)
            self.session.commit()

            return self._toEntity(model)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def delete(self, id) -> bool:
        """The author's delete: the row, its comments and its likes, for real."""
        try:
            model = self.findById(id, returnModel=True)

            self.session.delete(model)
            self.session.commit()

            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def setRemoved(self, id, removed: bool) -> Post:
        """Moderation: take a post down (status blocked) or put it back.

        Only a session with no RLS context can do this — tb_16's UPDATE policy
        — which is the admin routes' `getDb` and nothing an author holds.
        """
        try:
            model = self.findById(id, returnModel=True)

            if removed:
                model.status = config.STATUS_CODES["blocked"]
                model.removed_at = _utcnow()
            else:
                model.status = config.STATUS_CODES["enabled"]
                model.removed_at = None

            self.session.commit()

            return self._toEntity(model)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    # ── single reads ──────────────────────────────────────────────────────────

    def findById(self, id, returnModel: bool = False) -> Post | PostModel:
        """A post by id, whatever its state — for moderation and ownership checks."""
        try:
            model = self.session.query(PostModel).filter(PostModel.id == id).first()
            if model:
                return model if returnModel else self._toEntity(model)
            raise self._notFound()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findVisible(self, id, viewerId: str) -> Post:
        """A post as `viewerId` may see it, or 404 POST_NOT_FOUND."""
        try:
            model = self.session.query(PostModel).filter(
                PostModel.id == id,
                postVisibleTo(viewerId),
            ).first()
            if model:
                return self._toEntity(model)
            raise self._notFound()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    # ── lists ─────────────────────────────────────────────────────────────────

    def _page(self, query, after: Optional[Cursor], limit: int) -> list[Post]:
        """Newest first, keyset on (created_at, id). Fetches `limit + 1` so the
        caller can tell whether there is a next page without a count."""
        if after is not None:
            query = query.filter(tuple_(PostModel.created_at, PostModel.id) < tuple_(*after))

        models = query.order_by(
            PostModel.created_at.desc(),
            PostModel.id.desc()
        ).limit(limit + 1).all()

        return [self._toEntity(model) for model in models]


    def feed(self, viewerId: str, scope: str, after: Optional[Cursor], limit: int) -> list[Post]:
        """One page of a feed.

        - `friends` — my posts and my accepted friends', whatever audience
          each was written for.
        - `community` — every `community` post I may see, plus my own.
        """
        try:
            query = self.session.query(PostModel).filter(postVisibleTo(viewerId))

            if scope == VISIBILITY_COMMUNITY:
                query = query.filter(or_(
                    PostModel.visibility == VISIBILITY_COMMUNITY,
                    PostModel.author_id == viewerId,
                ))
            else:
                query = query.filter(or_(
                    PostModel.author_id == viewerId,
                    pairHasStatus(PostModel.author_id, viewerId, config.STATUS_CODES["accepted"]),
                ))

            return self._page(query, after, limit)
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def byAuthor(self, viewerId: str, authorId: str, after: Optional[Cursor], limit: int) -> list[Post]:
        """One account's posts, as `viewerId` may see them — a profile's list."""
        try:
            query = self.session.query(PostModel).filter(
                PostModel.author_id == authorId,
                postVisibleTo(viewerId),
            )
            return self._page(query, after, limit)
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findAllByAuthor(self, authorId: str) -> list[Post]:
        """Every post an account wrote, removed ones included — for the export."""
        try:
            models = self.session.query(PostModel).filter(
                PostModel.author_id == authorId
            ).order_by(PostModel.created_at.asc()).all()
            return [self._toEntity(model) for model in models]
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    # ── likes ─────────────────────────────────────────────────────────────────

    def like(self, postId, userId: str) -> None:
        """Idempotent: a second like of the same post is a no-op, not an error."""
        try:
            self.session.execute(
                pgInsert(PostLikeModel.__table__)
                .values(cl_18a=postId, cl_18b=userId, created_at=_utcnow())
                .on_conflict_do_nothing()
            )
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def unlike(self, postId, userId: str) -> None:
        """Idempotent the same way: unliking what was never liked is fine."""
        try:
            self.session.query(PostLikeModel).filter(
                PostLikeModel.post_id == postId,
                PostLikeModel.user_id == userId,
            ).delete(synchronize_session=False)
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def likeCounts(self, postIds: list) -> dict:
        """{post id: likes} for a page, in one grouped query.

        Counts likes from enabled accounts only, and the same number for every
        viewer — a like from someone you blocked still counts, it just never
        comes with a name, because no response ever names who liked anything.
        """
        if not postIds:
            return {}
        try:
            rows = self.session.query(
                PostLikeModel.post_id, func.count()
            ).filter(
                PostLikeModel.post_id.in_(postIds),
                _enabledUser(PostLikeModel.user_id),
            ).group_by(PostLikeModel.post_id).all()
            return {postId: int(total) for postId, total in rows}
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def likedBy(self, userId: str, postIds: list) -> set:
        """Which of these posts `userId` has liked."""
        if not postIds:
            return set()
        try:
            rows = self.session.query(PostLikeModel.post_id).filter(
                PostLikeModel.user_id == userId,
                PostLikeModel.post_id.in_(postIds),
            ).all()
            return {row[0] for row in rows}
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def likedPostIds(self, userId: str) -> list[tuple]:
        """(post id, when) for every like an account gave — for the export."""
        try:
            rows = self.session.query(PostLikeModel.post_id, PostLikeModel.created_at).filter(
                PostLikeModel.user_id == userId
            ).order_by(PostLikeModel.created_at.asc()).all()
            return [(row[0], row[1]) for row in rows]
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    # ── the admin board ───────────────────────────────────────────────────────

    def countCreatedPerDay(self, days: int) -> list[dict]:
        """Posts published per day for the last `days`, oldest first, every day
        present — the same shape and the same reasoning as
        `ReportRepository.countCreatedPerDay`. A count and nothing else: the
        board aggregates and never enumerates."""
        try:
            since = (
                datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(days=days - 1)
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            rows = (
                self.session.query(func.date(PostModel.created_at), func.count(PostModel.id))
                .filter(PostModel.created_at >= since)
                .group_by(func.date(PostModel.created_at))
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


    # ── retention ─────────────────────────────────────────────────────────────

    def countRemovedBefore(self, cutoff: datetime) -> int:
        try:
            return self.session.query(PostModel.id).filter(
                PostModel.status == config.STATUS_CODES["blocked"],
                PostModel.removed_at < cutoff,
            ).count()
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def deleteRemovedBefore(self, cutoff: datetime) -> int:
        """Delete posts a moderator removed before `cutoff`. Returns how many.

        Their comments and likes go with them through the foreign keys.
        """
        try:
            deleted = self.session.query(PostModel).filter(
                PostModel.status == config.STATUS_CODES["blocked"],
                PostModel.removed_at < cutoff,
            ).delete(synchronize_session=False)
            self.session.commit()
            return deleted
        except Exception as e:
            self.session.rollback()
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
