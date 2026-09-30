"""Unit tests for PostService.

The visibility rules themselves are SQL and live in the integration suite
(tests/integration/test_posts.py), where a real Postgres evaluates them. What is
tested here is everything around them: the order of the gates on writing, that
quota is spent only once a row exists, who is notified of what, and who may
delete or restore.
"""

import pytest
from unittest.mock import MagicMock, patch

from datetime import datetime
from uuid import uuid4

from core.config import config
from exceptions.baseExceptions import NoHarmException


AUTHOR = "uid-author"
READER = "uid-reader"
ADMIN = "uid-admin"


def _user(uid=AUTHOR, status=None, username="ana"):
    u = MagicMock()
    u.id = uid
    u.username = username
    u.profile_picture = None
    u.status = config.STATUS_CODES["enabled"] if status is None else status
    return u


def _post(author=AUTHOR, status=None, content="one day at a time"):
    from domain.entities.post import Post
    return Post(
        id=uuid4(),
        author_id=author,
        content=content,
        visibility="community",
        status=config.STATUS_CODES["enabled"] if status is None else status,
        created_at=datetime(2026, 10, 1, 12, 0, 0),
    )


def _comment(postId, author=READER, status=None, content="you've got this"):
    from domain.entities.post import PostComment
    return PostComment(
        id=uuid4(),
        post_id=postId,
        author_id=author,
        content=content,
        status=config.STATUS_CODES["enabled"] if status is None else status,
        created_at=datetime(2026, 10, 1, 12, 5, 0),
    )


@pytest.fixture
def quotas():
    with patch("domain.services.postService._postQuota") as posts, \
         patch("domain.services.postService._commentQuota") as comments:
        posts.check.return_value = (True, 0)
        comments.check.return_value = (True, 0)
        yield posts, comments


@pytest.fixture
def consent():
    with patch("domain.services.postService.ConsentService") as MockConsent:
        MockConsent.return_value.pending.return_value = []
        yield MockConsent.return_value


@pytest.fixture
def outbound():
    with patch("domain.services.postService.emitter") as emitter, \
         patch("domain.services.postService.fcmService") as fcm, \
         patch("domain.services.postService.NoticeService") as notices:
        yield emitter, fcm, notices.return_value


@pytest.fixture
def service(mock_db, quotas, consent, outbound):
    from domain.services.postService import PostService

    s = PostService(mock_db)
    s.postRepository = MagicMock()
    s.commentRepository = MagicMock()
    s.userRepository = MagicMock()
    s.auditRepository = MagicMock()

    s.userRepository.findById.side_effect = lambda uid: _user(uid, username=f"name-{uid}")
    s.userRepository.findManyByIds.side_effect = lambda ids: [_user(uid, username=f"name-{uid}") for uid in ids]
    s.postRepository.likeCounts.return_value = {}
    s.postRepository.likedBy.return_value = set()
    s.commentRepository.countsByPosts.return_value = {}
    s.postRepository.create.side_effect = lambda post: _post(post.author_id, content=post.content)
    s.commentRepository.create.side_effect = lambda c: _comment(c.post_id, c.author_id, content=c.content)
    return s


# ── writing: the gates ────────────────────────────────────────────────────────

class TestGates:
    def test_a_post_is_created_and_the_quota_spent_after(self, service, quotas):
        posts, _ = quotas

        result = service.create(AUTHOR, "  hello  ", "friends")

        assert result.content == "hello"
        assert result.is_mine is True
        posts.spend.assert_called_once_with(AUTHOR)

    def test_the_quota_is_checked_before_the_database(self, service, quotas):
        posts, _ = quotas
        posts.check.return_value = (False, 3600)

        with pytest.raises(NoHarmException) as exc:
            service.create(AUTHOR, "hello", "community")

        assert exc.value.statusCode == 429
        assert exc.value.errorCode == "POST_QUOTA_EXCEEDED"
        assert exc.value.details["retryAt"].endswith("Z")
        service.userRepository.findById.assert_not_called()
        posts.spend.assert_not_called()

    def test_an_account_that_is_not_enabled_cannot_post(self, service, quotas):
        service.userRepository.findById.side_effect = lambda uid: _user(uid, status=config.STATUS_CODES["disabled"])

        with pytest.raises(NoHarmException) as exc:
            service.create(AUTHOR, "hello", "community")

        assert exc.value.errorCode == "POSTER_NOT_ELIGIBLE"
        service.postRepository.create.assert_not_called()
        quotas[0].spend.assert_not_called()

    def test_pending_terms_block_posting(self, service, consent):
        consent.pending.return_value = ["privacy"]

        with pytest.raises(NoHarmException) as exc:
            service.create(AUTHOR, "hello", "community")

        assert exc.value.statusCode == 403
        assert exc.value.errorCode == "CONSENT_REQUIRED"
        assert exc.value.details == {"pending": ["privacy"]}

    def test_stale_health_consent_does_not_block_posting(self, service, consent):
        """A post is not the tracker."""
        consent.pending.return_value = ["health_data"]

        service.create(AUTHOR, "hello", "community")

        service.postRepository.create.assert_called_once()

    def test_content_empty_after_sanitising_is_refused(self, service):
        with pytest.raises(NoHarmException) as exc:
            service.create(AUTHOR, "<b></b>", "community")

        assert exc.value.statusCode == 422

    def test_an_unknown_audience_is_refused(self, service):
        with pytest.raises(NoHarmException) as exc:
            service.create(AUTHOR, "hello", "everyone")

        assert exc.value.errorCode == "INVALID_VISIBILITY"


# ── comments and who hears about them ─────────────────────────────────────────

class TestComments:
    def test_the_post_author_is_notified_by_name_and_never_by_text(self, service, outbound, quotas):
        emitter, fcm, _ = outbound
        post = _post()
        service.postRepository.findVisible.return_value = post

        service.comment(post.id, READER, "something private")

        emitter.notifyPostComment.assert_called_once()
        args = fcm.sendPushToUser.call_args
        assert args[0][0] == AUTHOR
        assert "something private" not in args[0][1] + args[0][2]
        assert f"name-{READER}" in args[0][2]
        assert args.kwargs["category"] == "community"
        quotas[1].spend.assert_called_once_with(READER)

    def test_commenting_on_your_own_post_notifies_nobody(self, service, outbound):
        emitter, fcm, _ = outbound
        post = _post()
        service.postRepository.findVisible.return_value = post

        service.comment(post.id, AUTHOR, "thanks all")

        emitter.notifyPostComment.assert_not_called()
        fcm.sendPushToUser.assert_not_called()

    def test_an_invisible_post_is_404_before_any_gate(self, service, quotas):
        service.postRepository.findVisible.side_effect = NoHarmException(
            statusCode=404, errorCode="POST_NOT_FOUND", message="Post not found."
        )

        with pytest.raises(NoHarmException) as exc:
            service.comment(uuid4(), READER, "hi")

        assert exc.value.errorCode == "POST_NOT_FOUND"
        quotas[1].check.assert_not_called()

    def test_likes_notify_nobody(self, service, outbound):
        emitter, fcm, _ = outbound
        post = _post()
        service.postRepository.findVisible.return_value = post
        service.postRepository.likeCounts.return_value = {post.id: 1}

        result = service.like(post.id, READER)

        assert result.liked is True and result.like_count == 1
        emitter.notifyPostComment.assert_not_called()
        fcm.sendPushToUser.assert_not_called()


# ── deleting ──────────────────────────────────────────────────────────────────

class TestDeleting:
    def test_someone_elses_post_is_404_not_403(self, service):
        post = _post()
        service.postRepository.findById.return_value = post

        with pytest.raises(NoHarmException) as exc:
            service.delete(post.id, READER)

        assert exc.value.statusCode == 404
        service.postRepository.delete.assert_not_called()

    def test_the_author_deletes_for_real(self, service):
        post = _post()
        service.postRepository.findById.return_value = post

        service.delete(post.id, AUTHOR)

        service.postRepository.delete.assert_called_once_with(post.id)

    @pytest.mark.parametrize("caller", [READER, AUTHOR])
    def test_a_comment_goes_by_its_author_or_the_posts(self, service, caller):
        post = _post()
        comment = _comment(post.id)
        service.commentRepository.findById.return_value = comment
        service.postRepository.findById.return_value = post

        service.deleteComment(post.id, comment.id, caller)

        service.commentRepository.delete.assert_called_once_with(comment.id)

    def test_a_third_party_cannot_delete_a_comment(self, service):
        post = _post()
        comment = _comment(post.id)
        service.commentRepository.findById.return_value = comment
        service.postRepository.findById.return_value = post

        with pytest.raises(NoHarmException) as exc:
            service.deleteComment(post.id, comment.id, "uid-stranger")

        assert exc.value.errorCode == "COMMENT_NOT_FOUND"
        service.commentRepository.delete.assert_not_called()

    def test_a_comment_named_under_the_wrong_post_is_404(self, service):
        comment = _comment(uuid4())
        service.commentRepository.findById.return_value = comment

        with pytest.raises(NoHarmException):
            service.deleteComment(uuid4(), comment.id, READER)


# ── moderation ────────────────────────────────────────────────────────────────

class TestModeration:
    def test_removal_sends_one_notice_with_an_excerpt(self, service, outbound):
        _, _, notices = outbound
        post = _post(content="x" * 50)
        service.postRepository.findById.return_value = post
        service.postRepository.setRemoved.return_value = _post(status=config.STATUS_CODES["blocked"])

        result = service.removePost(post.id, ADMIN, "self_harm", "we're here for you")

        assert result.status == config.STATUS_CODES["blocked"]
        service.postRepository.setRemoved.assert_called_once_with(post.id, True)
        notices.noticeOfContentRemoval.assert_called_once_with(
            AUTHOR, "post_removed", "self_harm", ADMIN, "x" * 50, "we're here for you"
        )

    def test_removing_what_is_already_removed_sends_nothing(self, service, outbound):
        _, _, notices = outbound
        service.postRepository.findById.return_value = _post(status=config.STATUS_CODES["blocked"])

        service.removePost(uuid4(), ADMIN, "spam")

        service.postRepository.setRemoved.assert_not_called()
        notices.noticeOfContentRemoval.assert_not_called()

    def test_restore_is_idempotent(self, service):
        service.postRepository.findById.return_value = _post()

        service.restorePost(uuid4(), ADMIN)

        service.postRepository.setRemoved.assert_not_called()


# ── pages ─────────────────────────────────────────────────────────────────────

class TestPages:
    def test_a_full_page_carries_a_cursor_and_drops_the_lookahead_row(self, service):
        rows = [_post() for _ in range(3)]
        service.postRepository.feed.return_value = rows

        page = service.feed(READER, "community", None, 2)

        assert [p.id for p in page.posts] == [rows[0].id, rows[1].id]
        assert page.next_cursor is not None

    def test_the_last_page_has_no_cursor(self, service):
        service.postRepository.feed.return_value = [_post()]

        assert service.feed(READER, "friends", None, 2).next_cursor is None

    def test_an_unknown_feed_is_refused(self, service):
        with pytest.raises(NoHarmException) as exc:
            service.feed(READER, "everything", None, 20)

        assert exc.value.errorCode == "INVALID_SCOPE"
