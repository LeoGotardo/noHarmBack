# NoHarm — Frontend Design Brief

> Context for a designer or AI creating mobile screen prototypes for the NoHarm app.
> NoHarm is an **addiction recovery tracker** — it helps users stay sober, track clean-day streaks, support each other through friendship and chat, and celebrate milestones through badges.

---

## 1. App Purpose & Tone

- **Core loop**: user registers → starts a streak → checks in daily → earns badges at milestones → connects with friends for accountability → chats for peer support.
- Audience: people in recovery from addiction. Tone should feel **safe, warm, motivating** — not clinical or harsh.
- App is **mobile-first**: a Vite + React 19 SPA, wrapped with Capacitor for iOS and Android, and served on the web at `noharm.site` (phone layout below 900px, a side rail above).

---

## 2. Authentication Flow

Authentication uses **Firebase** for identity, then the app issues its own JWT tokens.

### Screens needed
| Screen | Description |
|--------|-------------|
| Splash / Onboarding | Brand introduction, "Get Started" CTA |
| Register | **Google sign-in** (Firebase). The app sends the Firebase ID token plus a username (3–50 chars, `[a-zA-Z0-9_-]`, unique), a date of birth (refused under `MINIMUM_AGE_YEARS`, 18) and three separate answers: terms, privacy, health data. The first two are required. |
| Login | **Google sign-in**; the backend takes the Firebase ID token only. Banned (`ACCOUNT_BANNED`, or `ACCOUNT_SUSPENDED` with a date), blocked and deleted accounts are refused with their own codes; one inside its deletion window gets `ACCOUNT_PENDING_DELETION` and can be restored. |
| Token Refresh | Transparent background refresh — no dedicated screen, but the app must handle 401 silently. |

### Token details (for navigation logic)
- Access token: **15 min** lifetime — refresh happens silently in background.
- Refresh token: **7 days** lifetime.
- On logout, both tokens are revoked for current device only (multi-device supported).
- "Log out of all devices" (`POST /auth/logout-all`) revokes every token of the account and stops its push notifications on every device.

---

## 3. User Profile

### Data shape
```
id            string   — the Firebase UID, not a UUID
username      string   (3–50 chars, unique)
profile_picture  string | null  (URL, from the Google account)
role          "official" | "admin" | null   — the mark beside the name
created_at    datetime
updated_at    datetime

GET /users/me adds: email, status, health_data_consent, pending_consents,
must_change_username, picture_blocked
```

### Screens needed
| Screen | Notes |
|--------|-------|
| My Profile | Shows `username`, `profile_picture`, `email`, account status, join date. Edit button for username + photo. |
| Edit Profile | Editable: `username`, `profile_picture` only. Email changes require a separate Firebase flow (not in-app yet). |
| Public Profile | Other users' profile — shows username, profile picture, current streak days, mutual badge count. Blocked users cannot view their blocker's profile. |
| Delete Account | Confirmation dialog. Soft-delete only (status → deleted). |

---

## 4. Streaks

The streak is the **core feature**. A streak tracks how many consecutive days the user has been sober.

### Data shape
```
id            UUID
owner_id      string        — Firebase UID
start_at      datetime      — when the streak started (may be backdated)
end_at        datetime|null — when it ended (null = active)
last_checkin  datetime|null — the most recent check-in
status        int           (1=active, 0=ended)
is_record     bool          — true if this is the user's longest streak
created_at    datetime
updated_at    datetime

All instants are UTC with an explicit offset.
```

### Business rules
- User can only have one **active** streak at a time.
- A streak **never expires**. Check-ins are a daily ritual, not a condition: a missed one changes nothing on the server, and the app asks about the missed days when the user comes back.
- Ending a streak (relapse) checks if it was a personal record, then immediately starts a fresh streak.
- Streak age in days = `(now - start_at)` in hours / 24. Starting a streak needs health-data consent (`HEALTH_CONSENT_REQUIRED` otherwise).

### Screens needed
| Screen | Notes |
|--------|-------|
| Home / Dashboard | Primary screen. Large display of current streak days counter. Check-in button (if not checked in today). "I relapsed" / End streak button (destructive, needs confirm dialog). Personal record badge if `is_record = true`. |
| Streak History | List of all past streaks. Show start date, end date, duration in days, whether it was a record. |
| Record Streak | Can be a card on the profile or a dedicated stats screen. Shows longest streak ever. |

### Key UX considerations
- The check-in action is a **daily ritual** — make it satisfying (animation, haptic feedback idea).
- "End streak" / relapse is emotionally sensitive — the reset message should be **compassionate**, not punishing. The app immediately starts a new streak so the user isn't left at zero without a path forward.

---

## 5. Friendships

Users connect for accountability. Friendship is directional (sender / receiver) but mutual once accepted.

### Data shape
```
id          UUID
sender      UUID       — who sent the request
reciver     UUID       — who received it
send_at     datetime
recived_at  datetime|null
status      int        (see Status Codes)
created_at  datetime
updated_at  datetime
```

### Status values
| Code | Meaning |
|------|---------|
| 4 | Pending (request sent, not yet accepted) |
| 5 | Accepted (active friendship) |
| 6 | Ignored / Rejected |
| 3 | Blocked |
| 2 | Deleted (removed) |

### Screens needed
| Screen | Notes |
|--------|-------|
| Friends List | Shows all accepted friends. Shows their username, profile picture, optional online indicator (via WebSocket). |
| Friend Requests — Received | Pending requests with Accept / Reject buttons. |
| Friend Requests — Sent | Outgoing pending requests. Can be cancelled (delete). |
| Add Friend / Search User | Search by username. Shows public profile. Send request button if no existing friendship. |
| Friendship Actions | On a friend's profile: Message, Remove friend, Block. If blocked: Unblock only. |

### Rules
- Cannot send a request to yourself.
- Cannot send if a non-deleted friendship already exists (even pending/blocked).
- Blocked users cannot view the profile of their blocker.
- Anyone can block anyone — a friend or a stranger (`POST /users/{id}/block`) — and only the person who blocked can unblock.

### Reporting a user

Blocking is a private remedy — it hides two people from each other and tells
nobody. Reporting is how something reaches the team.

```
POST /reports/{userId}   { reason, details?, chatId? }  → 201 Report
GET  /reports/mine                                      → the reports I filed
```

```
Report
  id                UUID
  reporter          string      — the Firebase UID that filed it (null once purged)
  reported          string|null — the UID it names (null once that account is purged)
  reported_uid      string      — the same UID, copied at filing time; never null
  reported_username string|null — their username at filing time
  reason            string      — harassment | inappropriate | spam
                                |   impersonation | self_harm | other
  details           string|null — max 1000 chars, optional
  status            int         — 4 open · 5 actioned · 6 dismissed
  created_at        datetime
  updated_at        datetime
```

**`chatId` attaches the conversation.** Send it when the two have a chat: the
backend copies that chat's last 20 messages, both sides, as evidence stored with
the report. It is an **id, not content** — there is no field for message text,
and one would be refused, because a reporter must not be able to attribute
invented lines to someone. The app has no way to read that copy back; it is a
moderator's, and even the reporter gets 404.

| Rule | Answer |
|------|--------|
| Report yourself | 400 |
| Unknown or deleted account | 404 |
| Same user again while the first is still open | 409 `REPORT_ALREADY_OPEN` |
| Unknown reason, or details over 1000 chars | 422 |
| `chatId` of a conversation the reporter is not in | 403 (or 404) — nothing is filed |
| `chatId` of a conversation the reported user is not in | 400 — nothing is filed |
| Rate limit | 5/minute |

- No friendship is required — harassment arrives from strangers too.
- **The reported user is never told**, and cannot read reports about them. Say
  so in the UI: it is what makes the feature usable.
- Reporting changes nothing else. If the reporter also wants them gone, that is
  the existing block action, offered beside it.
- `self_harm` is worded as concern ("I'm worried about their safety"), not an
  accusation. In a recovery app that report is usually a friend asking for help
  for someone else.
- A report outlives both accounts. Deleting yours erases neither the reports you
  filed nor the ones about you — `reported_uid` is a copy the purge cannot
  clear.

### When an account is suspended

Moderation can pause an account for a while instead of banning it for good. The
app sees that on sign-in:

```
403 ACCOUNT_SUSPENDED   { details: { suspendedUntil } }   — a pause, with a date
403 ACCOUNT_BANNED                                        — permanent
```

Say the date. "This account is paused until March 3" and "your account is gone"
are different sentences, and in a recovery app the account holds a streak and a
friend list — `LoginScreen` draws the first from `suspendedUntil`.

Nothing has to be polled or scheduled: the suspension lifts itself the first
time the account signs in past the date, so the same button that failed
yesterday simply works. A still-valid access token stops working immediately
when the suspension starts, so a suspended user mid-session gets 403 on their
next request.

### What moderation tells the user

```
GET  /notices/mine?pending=true   → what to show on open
POST /notices/{id}/ack            → "I understand"
```

```
Notice
  id               UUID
  kind             string    — warning | suspension
  reason           string    — the conduct: harassment | inappropriate | spam
                             |   impersonation | other
  message          string|null — the moderator's own words, shown verbatim
  acknowledged_at  datetime|null
  created_at       datetime
```

A **warning** changes nothing about the account — no ban, no limits — and the
copy has to say that, or it reads as "you are about to lose this". A
**suspension** notice waits until the account comes back, which is the only
moment it can be read: a suspended token is refused everywhere, including here.

The notice never names who reported them, and never the moderator. Do not add
either to the UI — the response does not carry them, and the promise that a
reported user is never told is what makes reports fileable.

Show it over everything on open, before the check-in modal: being asked "all
clean today?" with an unread warning waiting is the wrong order. One button,
"I understand", which acknowledges it and never shows it again.

Say where to appeal on the notice and on a refused sign-in —
`VITE_SUPPORT_EMAIL`. A suspension nobody can argue with is the thing that
makes moderation feel arbitrary.

---

## 6. Chat

1-on-1 only (no group chats). **Both users must be accepted friends** to start a chat — except an official account, which can write to anyone, and whose conversations are read-only for the other side.

### Data shape
```
id          UUID
sender      UUID        — who initiated
reciver     UUID        — the other participant
started_at  datetime
ended_at    datetime|null
status      int         (1=enabled/active, 4=pending, 0=disabled/ended)
messages    MessageListResponse
created_at  datetime
updated_at  datetime
```

### Chat lifecycle
```
[Create] → status=pending → [Accept] → status=enabled → [End] → status=disabled
```
- Either participant can accept or end.
- No new messages can be sent after a chat is ended.
- If the same two users open a new chat after one was ended, a new chat object is created.

### Screens needed
| Screen | Notes |
|--------|-------|
| Chat List | All chats. Show other participant's name/avatar, last message preview, unread count, timestamp. |
| Chat Thread | Full message history. Input bar at bottom. Typing indicator. Read receipts. |
| Pending Chat Banner | If chat is in `pending` status — show "Accept conversation?" prompt with Accept button. |
| Ended Chat View | Read-only history, no input bar, "This conversation has ended" banner. |

---

## 7. Messages

Text-only messages (max 2000 characters). HTML is sanitised server-side.

### Data shape
```
id          UUID
chat        UUID        — parent chat ID
sender      UUID        — who sent it
message     string      (max 2000 chars)
status      int         (7=unread, 8=read)
send_at     datetime
recived_at  datetime|null
created_at  datetime
updated_at  datetime
```

### Read receipts
- Single message: mark individual message read.
- Bulk: mark all unread messages in a chat as read (called when opening chat thread).

---

## 8. Badges

Achievement system. Badges are global (defined by admins). Users earn badges when their streak reaches a milestone.

### Badge data shape
```
id          UUID
name        string (3–50 chars)
description string (3–500 chars)
milestone   datetime    — the streak milestone this badge represents
icon        string      — URL of badge icon image
status      int         (1=active, 0=disabled)
created_at  datetime
updated_at  datetime
```

### User Badge (earned badge) data shape
```
id          UUID
user_id     UUID
badge_id    UUID
given_at    datetime    — when it was granted
status      int         (1=active, 0=revoked)
created_at  datetime
updated_at  datetime
```

### Screens needed
| Screen | Notes |
|--------|-------|
| Badge Showcase | Grid or list of all badges. Locked vs. unlocked state. Shows icon, name, milestone description. |
| Badge Detail | Tapped badge: shows full description, when it was earned (or what milestone to reach). |
| Profile Badge Strip | Small row of most recent/rarest earned badges on profile screen. |

---

## 8b. Community (posts)

The contract is section 3 of [`POSTS_PLAN.md`](POSTS_PLAN.md) — shapes,
endpoints, errors — and the backend implements it as written. What the plan
left open, and how it was settled:

- `GET /posts` defaults to `scope=friends` when the parameter is omitted. Send
  it explicitly.
- A 403 `CONSENT_REQUIRED` carries `details.pending` (`["terms"]`,
  `["privacy"]` or both). Refetch `GET /users/me` and the gate appears.
- A 400 `INVALID_CURSOR` means the cursor was mangled; drop it and reload from
  the top.
- Blocking anyone: `POST /users/{userId}/block` / `DELETE /users/{userId}/block`,
  answering a `FriendshipResponse`. Every `FriendshipResponse` now carries
  `blocked_by`: show "Unblock" only when it is the current user (or null, on
  rows blocked before it existed). The blocked side gets 403 on unblock; no
  block is 404 `NOT_BLOCKED`.
- A report that joins an open one (D8) answers **200** with `appended: true`;
  a new report is still 201. `target_kind` is on every report.
- Removal notices: `NoticeResponse.kind` is `post_removed` / `comment_removed`
  and `excerpt` holds the first 200 characters of what was removed.
- Moderator actions (`PUT /posts/{id}/remove`, `…/restore`, and the comment
  pair) answer `{id, kind, author_id, status, removed_at}` — never the content.
- Push: `POST /notifications` takes `community` beside `messages` and
  `friends` (default `true`).

---

## 9. Real-Time (WebSocket / Socket.IO)

Connection is authenticated via JWT at connect time. Users auto-join their personal room `user_{userId}`.

### Events the app needs to handle

#### Chat events
| Direction | Event | Payload |
|-----------|-------|---------|
| Client → Server | `join_chat` | `{ chatId }` |
| Client → Server | `leave_chat` | `{ chatId }` |
| Client → Server | `send_message` | `{ chatId, content }` |
| Client → Server | `mark_read` | `{ chatId }` |
| Client → Server | `typing` | `{ chatId, isTyping: bool }` |
| Server → Client | `new_message` | `{ message }` |
| Server → Client | `messages_read` | `{ chatId }` |
| Server → Client | `typing_indicator` | `{ chatId, userId, isTyping }` |
| Server → Client | `chat_error` | `{ code, message }` |

#### Presence events
| Direction | Event | Payload |
|-----------|-------|---------|
| Client → Server | `get_online_status` | `{ userIds: [...] }` |
| Server → Client | `online_status` | `{ userId, online: bool }` |

#### Connection events (server → client)

| Event | Meaning |
|-------|---------|
| `session_replaced` | This socket was the oldest of the account's three and a newer device took its place. It is disconnected right after; reconnect when the screen is used again, not immediately |

#### Friend notification events (server → client, pushed to `user_{id}` room)
| Event | Meaning |
|-------|---------|
| `friend_request` | Someone sent you a friend request |
| `friend_accept` | Someone accepted your request |
| `friend_reject` | Someone rejected your request |
| `friend_remove` | Someone removed you |
| `friend_block` | Someone blocked you |
| `friend_unblock` | Someone unblocked you |

#### Community events (server → client, pushed to `user_{id}` room)
| Event | Payload | Meaning |
|-------|---------|---------|
| `post_comment` | `{ post_id, comment_id, author: { id, username } }` | Someone commented on your post. Never sent for your own comments, never for likes, and never with the text |

---

## 10. Status Code Reference

Used across all entities.

| Code | Meaning | Used by |
|------|---------|---------|
| 0 | Disabled | Users, Streaks, Badges, UserBadges |
| 1 | Enabled / Active | Users, Streaks, Badges, Chats, Friendships |
| 2 | Deleted (soft) | Users, Friendships |
| 3 | Blocked | Users (account blocked), Friendships, removed posts/comments |
| 4 | Pending | Friendships, Chats |
| 5 | Accepted | Friendships |
| 6 | Ignored / Rejected | Friendships, dismissed reports |
| 7 | Unread | Messages |
| 8 | Read | Messages |
| 9 | Banned | Users (account level ban) |

---

## 11. Suggested Screen Map (Navigation)

```
Auth Stack
├── Splash / Onboarding
├── Login
└── Register

Main Tab Navigator (authenticated)
├── Home (Tab 1)
│   ├── Dashboard — streak counter, check-in button, relapse button
│   └── Streak History
│
├── Friends (Tab 2)
│   ├── Friends List
│   ├── Friend Requests (Received / Sent)
│   └── Search Users → Public Profile
│
├── Chat (Tab 3)
│   ├── Chat List
│   └── Chat Thread
│
├── Community (Tab 4)
│   ├── Feed (Everyone / Friends)
│   └── Post Detail → comments
│
└── Profile (Tab 5)
    ├── My Profile → Badges → Badge Detail
    ├── Edit Profile
    └── Settings → Privacy & data, Notifications, moderation and admin (admins only), Delete Account
```

---

## 12. Key UX Notes for Designer

1. **Streak counter** is the emotional anchor — it should dominate the home screen visually.
2. **Relapse / end streak** is a sensitive moment. Use a compassionate confirmation (e.g., "It's okay. Every day is a new start."). Immediately show the new streak starting at 0 so the user feels continuity.
3. **Daily check-in** should feel rewarding — a clear "done for today" state vs. "needs check-in" state.
4. **Online indicators** (green dot) are available via WebSocket — useful in Friends and Chat List.
5. **Unread message badges** should show on Chat tab and in Chat List rows.
6. **Friend request notifications** arrive in real-time — show in-app notification or badge on Friends tab.
7. **Profile pictures** are URLs (currently optional/nullable) — always design with a fallback avatar.
8. **No group chats** — all messaging is strictly 1-on-1.
9. **No in-app email verification UI** — Google sign-in arrives verified.
10. Pagination is supported on all list endpoints — design list screens to support infinite scroll or load-more.
