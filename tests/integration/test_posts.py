"""The Community tab: posts, comments, likes, and who can see which.

Visibility is the part that breaks, so most of this file is about it: the two
feeds, blocks in both directions, an author whose account stops being enabled,
a post a moderator removed. Every "cannot see" is asserted as a 404, never a
403 — a 403 would confirm the post exists.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text

from helpers import _engine, as_admin, make_friends, new_identity, register, set_status


ADMIN_UID = "uid-moderator"


@pytest.fixture
def user_c(client):
    return register(client)


@pytest.fixture
def admin(client):
    user = register(client, new_identity(uid=ADMIN_UID))
    with as_admin(ADMIN_UID):
        yield user


def _post(client, author, content="one day at a time", visibility="community"):
    resp = client.post("/posts", json={"content": content, "visibility": visibility}, headers=author["headers"])
    assert resp.status_code == 201, resp.text
    return resp.json()


def _feed(client, viewer, scope, **params):
    resp = client.get("/posts", params={"scope": scope, **params}, headers=viewer["headers"])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids(page):
    return [p["id"] for p in page["posts"]]


def _comment(client, author, postId, content="you've got this"):
    return client.post(f"/posts/{postId}/comments", json={"content": content}, headers=author["headers"])


# ── writing ───────────────────────────────────────────────────────────────────

class TestWriting:
    def test_a_post_comes_back_in_the_contract_shape(self, client, user_a):
        post = _post(client, user_a, "  day 30  ", "friends")

        assert post["content"] == "day 30", "trimmed"
        assert post["visibility"] == "friends"
        assert post["author"]["id"] == user_a["uid"]
        assert post["author"]["username"] == user_a["identity"]["username"]
        assert post["like_count"] == 0 and post["comment_count"] == 0
        assert post["is_mine"] is True and post["liked_by_me"] is False

    @pytest.mark.parametrize("body", [
        {"content": "   \n  ", "visibility": "community"},
        {"content": "x" * 1001, "visibility": "community"},
        {"content": "hi", "visibility": "everyone"},
        {"content": "hi", "visibility": "community", "anonymous": True},
    ])
    def test_invalid_bodies_are_422(self, client, user_a, body):
        assert client.post("/posts", json=body, headers=user_a["headers"]).status_code == 422

    def test_html_is_stripped(self, client, user_a):
        post = _post(client, user_a, "<script>alert(1)</script>still here")
        assert "<script>" not in post["content"]

    def test_an_account_that_owes_consent_cannot_post_but_can_like(self, client, user_a, user_b):
        post = _post(client, user_b)

        with patch("core.config.config.TERMS_VERSION", "2099-01-01"):
            resp = client.post("/posts", json={"content": "hi", "visibility": "community"}, headers=user_a["headers"])
            assert resp.status_code == 403
            assert resp.json()["errorCode"] == "CONSENT_REQUIRED"
            assert resp.json()["details"]["pending"] == ["terms"]

            resp = _comment(client, user_a, post["id"])
            assert resp.json()["errorCode"] == "CONSENT_REQUIRED"

            assert client.put(f"/posts/{post['id']}/like", headers=user_a["headers"]).status_code == 200

    def test_the_daily_quota_answers_with_when_it_lifts(self, client, user_a):
        from security.rateLimiter import ContentQuotaLimiter

        with patch("domain.services.postService._postQuota", ContentQuotaLimiter("post-test", 1)):
            _post(client, user_a)
            resp = client.post("/posts", json={"content": "again", "visibility": "community"}, headers=user_a["headers"])

        assert resp.status_code == 429
        assert resp.json()["errorCode"] == "POST_QUOTA_EXCEEDED"
        assert resp.json()["details"]["retryAt"].endswith("Z")


# ── visibility ────────────────────────────────────────────────────────────────

class TestVisibility:
    def test_friends_posts_reach_friends_only(self, client, user_a, user_b, user_c):
        make_friends(client, user_a, user_b)
        post = _post(client, user_a, visibility="friends")

        assert post["id"] in _ids(_feed(client, user_b, "friends"))
        assert post["id"] not in _ids(_feed(client, user_b, "community")), "the community tab is community posts"
        assert post["id"] not in _ids(_feed(client, user_c, "friends"))
        assert post["id"] not in _ids(_feed(client, user_c, "community"))

        resp = client.get(f"/posts/{post['id']}", headers=user_c["headers"])
        assert resp.status_code == 404
        assert resp.json()["errorCode"] == "POST_NOT_FOUND"

    def test_community_posts_reach_everyone(self, client, user_a, user_c):
        post = _post(client, user_a, visibility="community")

        assert post["id"] in _ids(_feed(client, user_c, "community"))
        assert post["id"] not in _ids(_feed(client, user_c, "friends")), "a stranger is not a friend"
        assert client.get(f"/posts/{post['id']}", headers=user_c["headers"]).status_code == 200

    def test_my_own_posts_are_in_both_feeds(self, client, user_a):
        friendsOnly = _post(client, user_a, visibility="friends")
        public = _post(client, user_a, visibility="community")

        assert set(_ids(_feed(client, user_a, "friends"))) == {friendsOnly["id"], public["id"]}
        assert set(_ids(_feed(client, user_a, "community"))) == {friendsOnly["id"], public["id"]}

    def test_an_ended_friendship_takes_friends_posts_with_it(self, client, user_a, user_b):
        fid = make_friends(client, user_a, user_b)
        post = _post(client, user_a, visibility="friends")

        client.delete(f"/friendships/{fid}", headers=user_b["headers"])

        assert client.get(f"/posts/{post['id']}", headers=user_b["headers"]).status_code == 404

    @pytest.mark.parametrize("blocker", ["author", "viewer"])
    def test_a_block_in_either_direction_hides_everything(self, client, user_a, user_c, blocker):
        post = _post(client, user_a)
        _comment(client, user_c, post["id"])

        who, whom = (user_a, user_c) if blocker == "author" else (user_c, user_a)
        assert client.post(f"/users/{whom['uid']}/block", headers=who["headers"]).status_code == 200

        assert post["id"] not in _ids(_feed(client, user_c, "community"))
        assert client.get(f"/posts/{post['id']}", headers=user_c["headers"]).status_code == 404
        assert client.put(f"/posts/{post['id']}/like", headers=user_c["headers"]).status_code == 404
        assert _comment(client, user_c, post["id"]).status_code == 404

        # And the author no longer sees the blocked account's comment on their post.
        comments = client.get(f"/posts/{post['id']}/comments", headers=user_a["headers"]).json()["comments"]
        assert comments == []

    @pytest.mark.parametrize("status", [2, 9])  # deleted, banned
    def test_an_author_who_is_not_enabled_disappears(self, client, user_a, user_c, status):
        post = _post(client, user_a)
        set_status(user_a["uid"], status)

        assert post["id"] not in _ids(_feed(client, user_c, "community"))
        assert client.get(f"/posts/{post['id']}", headers=user_c["headers"]).status_code == 404

    def test_a_profile_lists_what_the_viewer_may_see(self, client, user_a, user_b, user_c):
        make_friends(client, user_a, user_b)
        friendsOnly = _post(client, user_a, visibility="friends")
        public = _post(client, user_a, visibility="community")

        def listed(viewer):
            resp = client.get(f"/users/{user_a['uid']}/posts", headers=viewer["headers"])
            assert resp.status_code == 200
            return set(_ids(resp.json()))

        assert listed(user_b) == {friendsOnly["id"], public["id"]}
        assert listed(user_c) == {public["id"]}

        client.post(f"/users/{user_c['uid']}/block", headers=user_a["headers"])
        assert listed(user_c) == set(), "an empty page, not an error"


# ── the feed's cursor ─────────────────────────────────────────────────────────

class TestCursor:
    def test_pages_do_not_repeat_when_a_post_arrives_in_between(self, client, user_a, user_c):
        first, second, third = (_post(client, user_a, f"post {n}") for n in range(3))

        page1 = _feed(client, user_c, "community", limit=2)
        assert _ids(page1) == [third["id"], second["id"]], "newest first"
        assert page1["next_cursor"]

        _post(client, user_a, "arrived meanwhile")

        page2 = _feed(client, user_c, "community", limit=2, cursor=page1["next_cursor"])
        assert _ids(page2) == [first["id"]]
        assert page2["next_cursor"] is None

    def test_a_mangled_cursor_is_a_400(self, client, user_a):
        resp = client.get("/posts", params={"cursor": "not-a-cursor!"}, headers=user_a["headers"])
        assert resp.status_code == 400
        assert resp.json()["errorCode"] == "INVALID_CURSOR"


# ── likes ─────────────────────────────────────────────────────────────────────

class TestLikes:
    def test_liking_is_idempotent(self, client, user_a, user_c):
        post = _post(client, user_a)

        for _ in range(2):
            resp = client.put(f"/posts/{post['id']}/like", headers=user_c["headers"])
            assert resp.json() == {"liked": True, "like_count": 1}

        seen = client.get(f"/posts/{post['id']}", headers=user_c["headers"]).json()
        assert seen["liked_by_me"] is True and seen["like_count"] == 1
        assert client.get(f"/posts/{post['id']}", headers=user_a["headers"]).json()["liked_by_me"] is False

        for _ in range(2):
            resp = client.delete(f"/posts/{post['id']}/like", headers=user_c["headers"])
            assert resp.json() == {"liked": False, "like_count": 0}


# ── comments ──────────────────────────────────────────────────────────────────

class TestComments:
    def test_a_thread_reads_oldest_first_across_pages(self, client, user_a, user_c):
        post = _post(client, user_a)
        for n in range(3):
            assert _comment(client, user_c, post["id"], f"reply {n}").status_code == 201

        page1 = client.get(f"/posts/{post['id']}/comments", params={"limit": 2}, headers=user_a["headers"]).json()
        assert [c["content"] for c in page1["comments"]] == ["reply 0", "reply 1"]

        page2 = client.get(
            f"/posts/{post['id']}/comments",
            params={"limit": 2, "cursor": page1["next_cursor"]},
            headers=user_a["headers"],
        ).json()
        assert [c["content"] for c in page2["comments"]] == ["reply 2"]
        assert page2["next_cursor"] is None

        assert client.get(f"/posts/{post['id']}", headers=user_a["headers"]).json()["comment_count"] == 3

    def test_the_post_author_is_told_who_but_not_what(self, client, user_a, user_c):
        post = _post(client, user_a)

        with patch("domain.services.postService.emitter") as emitter, \
             patch("domain.services.postService.fcmService") as fcm:
            _comment(client, user_c, post["id"], "something private")
            _comment(client, user_a, post["id"], "my own reply")

        emitter.notifyPostComment.assert_called_once()
        fcm.sendPushToUser.assert_called_once()
        userId, title, body = fcm.sendPushToUser.call_args[0]
        assert userId == user_a["uid"]
        assert user_c["identity"]["username"] in body
        assert "something private" not in body
        assert fcm.sendPushToUser.call_args.kwargs["category"] == "community"

    def test_who_may_delete_a_comment(self, client, user_a, user_b, user_c):
        post = _post(client, user_a)
        comment = _comment(client, user_c, post["id"]).json()

        assert comment["can_delete"] is True
        asAuthor = client.get(f"/posts/{post['id']}/comments", headers=user_a["headers"]).json()["comments"][0]
        assert asAuthor["can_delete"] is True and asAuthor["is_mine"] is False
        asOther = client.get(f"/posts/{post['id']}/comments", headers=user_b["headers"]).json()["comments"][0]
        assert asOther["can_delete"] is False

        resp = client.delete(f"/posts/{post['id']}/comments/{comment['id']}", headers=user_b["headers"])
        assert resp.status_code == 404
        assert resp.json()["errorCode"] == "COMMENT_NOT_FOUND"

        # The post's author takes a stranger's reply off their own post (D7).
        assert client.delete(f"/posts/{post['id']}/comments/{comment['id']}", headers=user_a["headers"]).status_code == 204
        assert client.get(f"/posts/{post['id']}/comments", headers=user_a["headers"]).json()["comments"] == []

    def test_a_commenter_can_delete_their_comment_after_being_blocked(self, client, user_a, user_c):
        post = _post(client, user_a)
        comment = _comment(client, user_c, post["id"]).json()
        client.post(f"/users/{user_c['uid']}/block", headers=user_a["headers"])

        assert client.delete(f"/posts/{post['id']}/comments/{comment['id']}", headers=user_c["headers"]).status_code == 204


# ── deleting a post ───────────────────────────────────────────────────────────

class TestDelete:
    def test_only_the_author_deletes_and_it_takes_everything(self, client, user_a, user_c):
        post = _post(client, user_a)
        _comment(client, user_c, post["id"])
        client.put(f"/posts/{post['id']}/like", headers=user_c["headers"])

        assert client.delete(f"/posts/{post['id']}", headers=user_c["headers"]).status_code == 404
        assert client.delete(f"/posts/{post['id']}", headers=user_a["headers"]).status_code == 204
        assert client.get(f"/posts/{post['id']}", headers=user_a["headers"]).status_code == 404

        with _engine().connect() as conn:
            for table, column in (("tb_16", "cl_16a"), ("tb_17", "cl_17b"), ("tb_18", "cl_18a")):
                count = conn.execute(text(f"SELECT count(*) FROM {table} WHERE {column} = :id"), {"id": post["id"]}).scalar()
                assert count == 0, table


# ── blocking strangers (§1.1) ─────────────────────────────────────────────────

class TestBlockingStrangers:
    def test_the_blocked_side_cannot_unblock_itself(self, client, user_a, user_c):
        resp = client.post(f"/users/{user_c['uid']}/block", headers=user_a["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == 3
        assert resp.json()["blocked_by"] == user_a["uid"]

        resp = client.delete(f"/users/{user_a['uid']}/block", headers=user_c["headers"])
        assert resp.status_code == 403

        assert client.delete(f"/users/{user_c['uid']}/block", headers=user_a["headers"]).status_code == 200
        assert client.delete(f"/users/{user_c['uid']}/block", headers=user_a["headers"]).status_code == 404

    def test_blocking_a_friend_moves_the_friendship(self, client, user_a, user_b):
        fid = make_friends(client, user_a, user_b)

        resp = client.post(f"/users/{user_b['uid']}/block", headers=user_a["headers"])
        assert resp.json()["id"] == fid

        # The friendship route honours who blocked, too.
        assert client.post(f"/friendships/{fid}/unblock", headers=user_b["headers"]).status_code == 403

    def test_a_block_beside_a_deleted_friendship_still_stops_a_request(self, client, user_a, user_b):
        fid = make_friends(client, user_a, user_b)
        client.delete(f"/friendships/{fid}", headers=user_a["headers"])

        client.post(f"/users/{user_a['uid']}/block", headers=user_b["headers"])

        assert client.post(f"/friendships/{user_b['uid']}", headers=user_a["headers"]).status_code == 403

    def test_blocking_yourself_is_refused(self, client, user_a):
        assert client.post(f"/users/{user_a['uid']}/block", headers=user_a["headers"]).status_code == 400


# ── moderation ────────────────────────────────────────────────────────────────

class TestModeration:
    def test_removal_hides_it_from_everyone_and_tells_the_author(self, client, user_a, user_c, admin):
        post = _post(client, user_a, "x" * 300)

        resp = client.put(
            f"/posts/{post['id']}/remove",
            json={"reason": "inappropriate", "message": "Please keep it kind."},
            headers=admin["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == 3

        for viewer in (user_a, user_c):
            assert client.get(f"/posts/{post['id']}", headers=viewer["headers"]).status_code == 404

        notices = client.get("/notices/mine", headers=user_a["headers"]).json()["notices"]
        assert [n["kind"] for n in notices] == ["post_removed"]
        assert notices[0]["excerpt"].startswith("x" * 200)
        assert len(notices[0]["excerpt"]) <= 201

        # Removing again sends no second notice.
        client.put(f"/posts/{post['id']}/remove", json={"reason": "inappropriate"}, headers=admin["headers"])
        assert len(client.get("/notices/mine", headers=user_a["headers"]).json()["notices"]) == 1

        assert client.put(f"/posts/{post['id']}/restore", headers=admin["headers"]).json()["status"] == 1
        assert client.get(f"/posts/{post['id']}", headers=user_c["headers"]).status_code == 200

    def test_a_crisis_post_may_be_removed(self, client, user_a, admin):
        post = _post(client, user_a)
        resp = client.put(f"/posts/{post['id']}/remove", json={"reason": "self_harm"}, headers=admin["headers"])
        assert resp.status_code == 200
        notice = client.get("/notices/mine", headers=user_a["headers"]).json()["notices"][0]
        assert notice["reason"] == "self_harm"

    def test_comments_are_removed_the_same_way(self, client, user_a, user_c, admin):
        post = _post(client, user_a)
        comment = _comment(client, user_c, post["id"]).json()

        resp = client.put(
            f"/posts/{post['id']}/comments/{comment['id']}/remove",
            json={"reason": "harassment"},
            headers=admin["headers"],
        )
        assert resp.status_code == 200
        assert client.get(f"/posts/{post['id']}/comments", headers=user_a["headers"]).json()["comments"] == []
        assert client.get("/notices/mine", headers=user_c["headers"]).json()["notices"][0]["kind"] == "comment_removed"

    def test_moderation_is_admin_only(self, client, user_a, user_c):
        post = _post(client, user_a)
        resp = client.put(f"/posts/{post['id']}/remove", json={"reason": "spam"}, headers=user_c["headers"])
        assert resp.status_code == 404

    def test_a_post_the_author_deleted_is_404_to_moderation(self, client, user_a, admin):
        post = _post(client, user_a)
        client.delete(f"/posts/{post['id']}", headers=user_a["headers"])
        resp = client.put(f"/posts/{post['id']}/remove", json={"reason": "spam"}, headers=admin["headers"])
        assert resp.status_code == 404

    def test_the_purge_takes_only_what_is_past_the_window(self, client, db, user_a, admin):
        from infrastructure.database.repositories.postRepository import PostRepository

        old = _post(client, user_a, "old")
        recent = _post(client, user_a, "recent")
        for post in (old, recent):
            client.put(f"/posts/{post['id']}/remove", json={"reason": "spam"}, headers=admin["headers"])

        with _engine().connect() as conn:
            conn.execute(text("UPDATE tb_16 SET cl_16f = NOW() - INTERVAL '31 days' WHERE cl_16a = :id"), {"id": old["id"]})
            conn.commit()

        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        assert PostRepository(db).deleteRemovedBefore(cutoff) == 1

        with _engine().connect() as conn:
            left = conn.execute(text("SELECT cl_16a::text FROM tb_16 WHERE cl_16b = :uid"), {"uid": user_a["uid"]}).scalars().all()
        assert left == [recent["id"]]


# ── reports ───────────────────────────────────────────────────────────────────

def _report(client, reporter, reportedUid, **body):
    return client.post(f"/reports/{reportedUid}", json={"reason": "harassment", **body}, headers=reporter["headers"])


class TestReports:
    def test_reporting_a_post_captures_it(self, client, user_a, user_c, admin):
        post = _post(client, user_a, "the post in question")

        resp = _report(client, user_c, user_a["uid"], postId=post["id"])
        assert resp.status_code == 201, resp.text
        assert resp.json()["target_kind"] == "post"

        evidence = client.get(f"/reports/{resp.json()['id']}/evidence", headers=admin["headers"]).json()["evidence"]
        posts = [e for e in evidence if e["kind"] == "post"]
        assert [e["content"] for e in posts] == ["the post in question"]
        assert posts[0]["source_id"] == post["id"]

    def test_reporting_a_comment_captures_it_with_its_post(self, client, user_a, user_c, admin):
        post = _post(client, user_a, "context")
        comment = _comment(client, user_c, post["id"], "the reply").json()

        resp = _report(client, user_a, user_c["uid"], commentId=comment["id"])
        assert resp.status_code == 201, resp.text

        evidence = client.get(f"/reports/{resp.json()['id']}/evidence", headers=admin["headers"]).json()["evidence"]
        assert {e["kind"]: e["content"] for e in evidence if e["kind"] != "profile"} == {
            "comment": "the reply",
            "post": "context",
        }

    def test_the_target_rules(self, client, user_a, user_b, user_c):
        post = _post(client, user_a)
        hidden = _post(client, user_b, visibility="friends")

        assert _report(client, user_c, user_a["uid"], postId=post["id"], commentId=post["id"]).json()["errorCode"] == "REPORT_TARGET_AMBIGUOUS"
        assert _report(client, user_c, user_b["uid"], postId=post["id"]).json()["errorCode"] == "REPORT_TARGET_MISMATCH"
        assert _report(client, user_c, user_b["uid"], postId=hidden["id"]).status_code == 404

    def test_a_new_post_joins_the_open_report_instead_of_a_409(self, client, user_a, user_c, admin):
        first = _post(client, user_a, "first")
        second = _post(client, user_a, "second")

        opened = _report(client, user_c, user_a["uid"], postId=first["id"]).json()

        resp = _report(client, user_c, user_a["uid"], postId=second["id"], details="it happened again")
        assert resp.status_code == 200, resp.text
        assert resp.json()["appended"] is True
        assert resp.json()["id"] == opened["id"]

        evidence = client.get(f"/reports/{opened['id']}/evidence", headers=admin["headers"]).json()["evidence"]
        assert sorted(e["content"] for e in evidence if e["kind"] == "post") == ["first", "second"]
        assert [e["content"] for e in evidence if e["kind"] == "note"] == ["it happened again"]

        # With nothing new in it, a second report is still the duplicate it was.
        assert _report(client, user_c, user_a["uid"]).status_code == 409


# ── the export ────────────────────────────────────────────────────────────────

class TestExport:
    def test_the_export_carries_posts_comments_and_likes_including_removed(self, client, user_a, user_c, admin):
        kept = _post(client, user_a, "kept")
        removed = _post(client, user_a, "removed")
        client.put(f"/posts/{removed['id']}/remove", json={"reason": "spam"}, headers=admin["headers"])
        other = _post(client, user_c, "theirs")
        _comment(client, user_a, other["id"], "mine")
        client.put(f"/posts/{other['id']}/like", headers=user_a["headers"])

        export = client.get("/users/me/export", headers=user_a["headers"]).json()

        assert export["incomplete"] == []
        assert {p["content"]: p["removed_by_moderation"] for p in export["posts"]} == {"kept": False, "removed": True}
        assert [c["content"] for c in export["comments"]] == ["mine"]
        assert [like["post_id"] for like in export["likes"]] == [other["id"]]
