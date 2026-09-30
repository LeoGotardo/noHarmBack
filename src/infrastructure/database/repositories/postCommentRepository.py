from domain.entities.post import PostComment
from core.errorUtils import excLocation
from infrastructure.database.cursorUtils import Cursor
from infrastructure.database.models.baseModel import _utcnow
from infrastructure.database.models.postCommentModel import PostCommentModel
from infrastructure.database.models.postModel import PostModel
from infrastructure.database.models.userModel import UserModel
from infrastructure.database.repositories.postRepository import authorVisibleTo, postVisibleTo
from exceptions.baseExceptions import NoHarmException

from core.database import Database
from core.config import config

from sqlalchemy import exists, func, tuple_

from datetime import datetime
from typing import Optional


class PostCommentRepository:
    """Comments (tb_17)."""

    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine


    def _toEntity(self, model: PostCommentModel) -> PostComment:
        return PostComment(
            id=model.id,
            post_id=model.post_id,
            author_id=model.author_id,
            content=model.content,
            status=model.status,
            removed_at=model.removed_at,
            created_at=model.created_at,
            updated_at=model.updated_at
        )


    @staticmethod
    def _notFound() -> NoHarmException:
        return NoHarmException(statusCode=404, errorCode="COMMENT_NOT_FOUND", message="Comment not found.")


    # ── writes ────────────────────────────────────────────────────────────────

    def create(self, comment: PostComment) -> PostComment:
        try:
            model = PostCommentModel(
                post_id=comment.post_id,
                author_id=comment.author_id,
                content=comment.content,
                status=comment.status
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


    def setRemoved(self, id, removed: bool) -> PostComment:
        """Moderation's removal and restore — see `PostRepository.setRemoved`."""
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


    # ── reads ─────────────────────────────────────────────────────────────────

    def findById(self, id, returnModel: bool = False) -> PostComment | PostCommentModel:
        try:
            model = self.session.query(PostCommentModel).filter(PostCommentModel.id == id).first()
            if model:
                return model if returnModel else self._toEntity(model)
            raise self._notFound()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findVisible(self, id, viewerId: str) -> PostComment:
        """A comment `viewerId` may see: it is up, its author is visible to them,
        and so is the post it sits under. 404 COMMENT_NOT_FOUND otherwise."""
        try:
            model = self.session.query(PostCommentModel).filter(
                PostCommentModel.id == id,
                PostCommentModel.status == config.STATUS_CODES["enabled"],
                authorVisibleTo(PostCommentModel.author_id, viewerId),
                exists().where(PostModel.id == PostCommentModel.post_id, postVisibleTo(viewerId)),
            ).first()
            if model:
                return self._toEntity(model)
            raise self._notFound()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def thread(self, postId, viewerId: str, after: Optional[Cursor], limit: int) -> list[PostComment]:
        """One page of a post's comments, oldest first — a conversation reads
        in the order it was said. Fetches `limit + 1`, like the feed.

        Whether the post itself is visible is the caller's check; this applies
        rules 2 and 3 to each comment's author.
        """
        try:
            query = self.session.query(PostCommentModel).filter(
                PostCommentModel.post_id == postId,
                PostCommentModel.status == config.STATUS_CODES["enabled"],
                authorVisibleTo(PostCommentModel.author_id, viewerId),
            )

            if after is not None:
                query = query.filter(tuple_(PostCommentModel.created_at, PostCommentModel.id) > tuple_(*after))

            models = query.order_by(
                PostCommentModel.created_at.asc(),
                PostCommentModel.id.asc()
            ).limit(limit + 1).all()

            return [self._toEntity(model) for model in models]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def countsByPosts(self, postIds: list) -> dict:
        """{post id: comments} for a page, in one grouped query.

        Live comments from enabled accounts, the same number for every viewer.
        """
        if not postIds:
            return {}
        try:
            rows = self.session.query(
                PostCommentModel.post_id, func.count(PostCommentModel.id)
            ).filter(
                PostCommentModel.post_id.in_(postIds),
                PostCommentModel.status == config.STATUS_CODES["enabled"],
                exists().where(
                    UserModel.id == PostCommentModel.author_id,
                    UserModel.status == config.STATUS_CODES["enabled"],
                ),
            ).group_by(PostCommentModel.post_id).all()
            return {postId: int(total) for postId, total in rows}
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findAllByAuthor(self, authorId: str) -> list[PostComment]:
        """Every comment an account wrote, removed ones included — for the export."""
        try:
            models = self.session.query(PostCommentModel).filter(
                PostCommentModel.author_id == authorId
            ).order_by(PostCommentModel.created_at.asc()).all()
            return [self._toEntity(model) for model in models]
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    # ── retention ─────────────────────────────────────────────────────────────

    def countRemovedBefore(self, cutoff: datetime) -> int:
        try:
            return self.session.query(PostCommentModel.id).filter(
                PostCommentModel.status == config.STATUS_CODES["blocked"],
                PostCommentModel.removed_at < cutoff,
            ).count()
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def deleteRemovedBefore(self, cutoff: datetime) -> int:
        try:
            deleted = self.session.query(PostCommentModel).filter(
                PostCommentModel.status == config.STATUS_CODES["blocked"],
                PostCommentModel.removed_at < cutoff,
            ).delete(synchronize_session=False)
            self.session.commit()
            return deleted
        except Exception as e:
            self.session.rollback()
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
