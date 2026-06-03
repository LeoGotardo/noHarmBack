# Claude Design Prompt — NoHarm Mobile App

Paste this prompt into Claude Design to generate screen prototypes.

---

## Prompt

You are designing a mobile app called **NoHarm** — an addiction recovery tracker for people trying to stay sober. The app runs on iOS and Android (React Native / Expo).

---

### App Purpose & Tone

NoHarm helps users:
1. Track their **sober streak** (consecutive clean days)
2. **Check in daily** to keep the streak alive
3. Connect with **friends** for accountability
4. **Chat** 1-on-1 with friends for peer support
5. Earn **badges** at streak milestones (7 days, 30 days, 90 days, 1 year, etc.)

Tone: **warm, safe, motivating, human**. Never clinical or punishing. Users are in a vulnerable moment of their lives — every design decision should reinforce that they are doing something brave.

---

### Design System

- **Platform**: Mobile (375px wide — iPhone 14 base)
- **Style**: Clean, minimal, calming. Soft rounded corners. Generous white space.
- **Color palette suggestion**: Soft greens and warm neutrals for hope/growth. Avoid red for negative states — use soft amber or muted tones instead.
- **Typography**: Large, legible. The streak counter should be the biggest number on the home screen.
- **Icons**: Simple outline icons. Badge icons can be more illustrative/celebratory.
- **Dark mode**: Design in light mode first, but make it easy to invert.

---

### Motion & Geometric Background System

Every screen must include **layered geometric background patterns with motion**. This is a core visual identity rule — not optional decoration.

#### Background pattern rules

- Use **low-opacity geometric shapes** (5–15% opacity) layered behind all content so they never compete with text or interactive elements.
- Shapes vocabulary: **circles, arcs, hexagons, irregular polygons, fine dot grids, thin diagonal lines**. Mix 2–3 shape types per screen — not all at once.
- Shapes should feel **organic and intentional**, not random noise. Think: large soft circle in the top-right corner, faint hexagon grid in the lower third, a thin arc cutting across the hero area.
- Colors for shapes come from the screen's accent palette — never introduce new colors just for the background.

#### Motion behavior (describe in annotations, implement in code with React Native Animated / Reanimated)

- **Slow drift**: background shapes translate very slowly (20–40s full cycle, 4–8px travel). Creates a breathing, alive feeling without distracting.
- **Parallax on scroll**: background shapes move at 20–30% of the scroll speed, giving depth.
- **Pulse on check-in**: when the user taps Check In, background shapes scale up slightly (1.0 → 1.06) and fade back — a subtle celebration pulse.
- **Streak counter entrance**: on screen load, the geometric shapes behind the counter bloom outward from center (scale 0.8 → 1.0, opacity 0 → target opacity, 600ms ease-out).
- **Idle breathing**: shapes very slowly oscillate in opacity (target ± 3%) on a 6–10s loop when the screen is at rest.

#### Per-screen background direction

| Screen | Background concept |
|--------|-------------------|
| Splash / Onboarding | Large overlapping circles, soft gradient from top. Full bleed. |
| Login / Register | Subtle dot grid + one large arc in the corner. Calm, focused. |
| Dashboard (Home) | Radial burst of thin lines from streak counter center. Hexagon grid in lower half. Most animated screen. |
| Streak History | Diagonal line texture, low opacity. Minimal motion. |
| Friends List | Soft circle clusters in top-right. Gentle drift only. |
| Chat Thread | Extremely minimal — tiny dot grid far in background. Never distracts from messages. |
| Badge Showcase | Honeycomb / hexagon grid fills the background. Badge unlock triggers a local ripple on the unlocked cell. |
| Badge Detail (earned) | Confetti-like polygon burst frozen in time (no loop), full bleed behind the badge icon. |
| Profile | Soft concentric arcs centered on avatar. Slow pulse. |

#### Implementation note for the developer
Annotate each screen mockup with:
1. Shape type + approximate size + position
2. Opacity value
3. Animation type (drift / pulse / parallax / bloom / breathe) + duration
4. Whether the shape is on a dedicated background layer (z-index 0) or between content layers

---

### Screens to Design

Design all of the following screens. Group them by flow.

---

#### Auth Flow

1. **Splash / Onboarding**
   - App logo + tagline
   - "Get Started" and "I already have an account" CTAs

2. **Register**
   - Fields: Username (3–50 chars), Email, optional Profile Picture
   - Username must be unique (show inline error if taken)
   - Submit button

3. **Login**
   - Field: Email
   - Error states: banned account, deleted account, blocked account

---

#### Home (Tab 1) — Most important screen

4. **Dashboard**
   - Giant streak counter: "**42** clean days"
   - Subtitle: streak start date (e.g., "Since April 21, 2025")
   - Personal record badge: visible if this is the user's longest streak ever
   - **Check-in button** (primary CTA) — shown only if user hasn't checked in today. Once pressed: changes to "Checked in today ✓" with a celebratory micro-animation.
   - **"I relapsed" button** (secondary, subtle) — opens a compassionate confirmation bottom sheet: _"It's okay. Every day is a new start."_ with a soft "Reset & Start Over" confirm button. Never use harsh language.
   - Quick stats row: current streak / personal record / total streaks

5. **Streak History**
   - Scrollable list of past streaks
   - Each row: duration in days, start → end dates, record badge if applicable
   - Empty state: "Your first streak is still going strong!"

---

#### Friends (Tab 2)

6. **Friends List**
   - List of accepted friends: avatar, username, online indicator (green dot if online)
   - Tap → opens that friend's public profile
   - FAB or header button: "Add Friend"
   - Badge on tab: pending request count

7. **Friend Requests**
   - Two sub-tabs: Received / Sent
   - Received: avatar, username, Accept and Reject buttons
   - Sent: avatar, username, "Pending…" state, Cancel option

8. **Search Users**
   - Search bar
   - Results: avatar, username
   - Tap result → Public Profile with "Add Friend" button (disabled if already friends/blocked)

9. **Public Profile**
   - Avatar, username
   - Current streak days (big number)
   - Badge strip (up to 5 most recent badges)
   - Action buttons: "Message", "Add Friend" / "Remove Friend", "Block"
   - If blocked by this user: profile not accessible (show "User not found")

---

#### Chat (Tab 3)

10. **Chat List**
    - Each row: avatar, username, last message preview (truncated), timestamp, unread count badge
    - Unread chats visually distinct (bold name, colored badge)
    - Empty state: "No conversations yet. Message a friend!"

11. **Chat Thread**
    - Message bubbles: user's messages right-aligned, peer's left-aligned
    - Timestamps grouped by day
    - Read receipt: small "Read" under last sent message when status=read
    - Typing indicator: animated "..." bubble from peer
    - Text input bar + Send button at bottom (above keyboard)
    - If chat is **pending**: banner at top — "Accept this conversation?" with Accept button
    - If chat is **ended**: read-only, no input bar, banner — "This conversation has ended."

---

#### Badges (Tab 4)

12. **Badge Showcase**
    - Grid layout (2 columns)
    - Each badge: icon (large), name, milestone label (e.g., "30 days")
    - Earned badges: full color, with "Earned on [date]" label
    - Locked badges: grayscale / desaturated with a lock icon overlay
    - Tap → Badge Detail

13. **Badge Detail**
    - Full-size badge icon
    - Name, description
    - Milestone: "Reach 30 clean days"
    - If earned: "You earned this on [date]" — celebration feel
    - If locked: progress bar toward milestone (current streak / milestone target)

---

#### Profile (Tab 5)

14. **My Profile**
    - Avatar (tappable to change), username, email
    - Streak stats summary card
    - Badge strip: first 5 earned badges
    - "Edit Profile" button
    - "Settings" and "Log Out" options

15. **Edit Profile**
    - Editable: Username field, Profile Picture URL field
    - Save / Cancel buttons

16. **Settings / Account**
    - Log Out
    - Delete Account (destructive — confirmation required: "This will permanently delete your account.")

---

### Component States to Include

For each interactive element, show at least:
- **Default**
- **Loading** (skeleton or spinner)
- **Error** (inline, non-blocking where possible)
- **Empty state**

---

### Key UX Rules (enforce in every screen)

1. The streak counter is always the **largest typographic element** on screens where it appears.
2. "Relapse" / "Reset streak" language must always be paired with a compassionate message. No red, no warning icons.
3. The daily check-in must have a clear **done state** — the button changes, not just disappears.
4. Friend request and new message notifications should appear as **in-app banners** (not just tab badges).
5. Profile pictures are optional — always design with a **letter-avatar fallback** (first letter of username on a colored circle).
6. All lists support **infinite scroll** — design with a load-more or spinner at the bottom.
7. Blocked users: show "User not found" — never reveal that a block exists.
8. Chat that has ended: preserve message history in read-only view.

---

### Navigation Structure

```
Bottom Tab Bar (5 tabs)
├── Home       — streak counter + check-in
├── Friends    — friend list + requests
├── Chat       — conversations
├── Badges     — achievements
└── Profile    — account + settings
```

Tab bar badges:
- **Friends**: number of pending received requests
- **Chat**: total unread message count

---

### Data Notes for Realistic Mockups

Use these sample values in your mockups:

- Username: `alex_recovery`
- Current streak: **47 days** (started 2025-04-16)
- Personal record: **89 days**
- Badges earned: "First Week" (7d), "One Month" (30d) — locked: "90 Days Strong", "6 Months", "One Year"
- Friends: 3 accepted, 1 pending request received
- Unread messages: 2 in one chat

---

Generate high-fidelity mobile screens for all 16 screens listed above. Use a consistent design system across all screens.
