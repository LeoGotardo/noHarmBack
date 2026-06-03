# NoHarm — Frontend Design Brief

> Context for a designer or AI creating mobile screen prototypes for the NoHarm app.
> NoHarm is an **addiction recovery tracker** — it helps users stay sober, track clean-day streaks, support each other through friendship and chat, and celebrate milestones through badges.

---

## 1. App Purpose & Tone

- **Core loop**: user registers → starts a streak → checks in daily → earns badges at milestones → connects with friends for accountability → chats for peer support.
- Audience: people in recovery from addiction. Tone should feel **safe, warm, motivating** — not clinical or harsh.
- App is **mobile-first** (React Native / Expo).

---

## 2. Authentication Flow

Authentication uses **Firebase** for identity, then the app issues its own JWT tokens.

### Screens needed
| Screen | Description |
|--------|-------------|
| Splash / Onboarding | Brand introduction, "Get Started" CTA |
| Register | Fields: `username` (3–50 chars), `email`, optional profile picture URL. Username must be unique. |
| Login | Fields: `email` (Firebase auth). Banned/blocked/deleted accounts are rejected with error messaging. |
| Token Refresh | Transparent background refresh — no dedicated screen, but the app must handle 401 silently. |

### Token details (for navigation logic)
- Access token: **15 min** lifetime — refresh happens silently in background.
- Refresh token: **7 days** lifetime.
- On logout, both tokens are revoked for current device only (multi-device supported).

---

## 3. User Profile

### Data shape
```
id            UUID
username      string (3–50 chars, unique)
email         string
status        int  (see Status Codes)
profile_picture  string | null  (URL)
created_at    datetime
updated_at    datetime
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
id          UUID
owner_id    UUID
start       datetime     — when streak started
end         datetime|null — when streak ended (null = active)
status      int          (1=active, 0=expired/ended)
is_record   bool         — true if this is the user's longest streak
created_at  datetime
updated_at  datetime
```

### Business rules
- User can only have one **active** streak at a time.
- User must **check in** at least once every 24 h — otherwise the streak auto-expires on next fetch.
- Ending a streak checks if it was a personal record, then immediately starts a fresh streak.
- Streak age in days = `(now - start)` in hours / 24.

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

---

## 6. Chat

1-on-1 only (no group chats). **Both users must be accepted friends** to start a chat.

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

#### Friend notification events (server → client, pushed to `user_{id}` room)
| Event | Meaning |
|-------|---------|
| `friend_request` | Someone sent you a friend request |
| `friend_accept` | Someone accepted your request |
| `friend_reject` | Someone rejected your request |
| `friend_remove` | Someone removed you |
| `friend_block` | Someone blocked you |
| `friend_unblock` | Someone unblocked you |

---

## 10. Status Code Reference

Used across all entities.

| Code | Meaning | Used by |
|------|---------|---------|
| 0 | Disabled | Users, Streaks, Badges, UserBadges |
| 1 | Enabled / Active | Users, Streaks, Badges, Chats, Friendships |
| 2 | Deleted (soft) | Users, Friendships |
| 3 | Blocked | Users (account banned), Friendships |
| 4 | Pending | Friendships, Chats |
| 5 | Accepted | Friendships |
| 6 | Ignored / Rejected | Friendships |
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
├── Badges (Tab 4)
│   └── Badge Showcase → Badge Detail
│
└── Profile (Tab 5)
    ├── My Profile
    ├── Edit Profile
    └── Settings / Delete Account
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
9. **No in-app email verification UI** — Firebase handles that externally.
10. Pagination is supported on all list endpoints — design list screens to support infinite scroll or load-more.
