# ReadBack — live demo runbook

A ~15 minute walkthrough of everything implemented. Every step below has been
verified against the current build.

---

## 1. Setup (do this ~10 minutes before)

**Terminal 1 — database**
```bash
cd ~/ReadBack-Reading-Platform
docker compose up -d db          # Docker Desktop must already be running
```

**Terminal 2 — backend**
```bash
cd ~/ReadBack-Reading-Platform/backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**Terminal 3 — frontend**
```bash
cd ~/ReadBack-Reading-Platform/frontend
npm run dev
```

**Terminal 4 — put the database into demo state**
```bash
cd ~/ReadBack-Reading-Platform/backend
source .venv/bin/activate
python -m scripts.demo_setup --email sakshee@gmail.com --clean
```

This is re-runnable — run it again between rehearsals and once more right
before the real thing. It sets:

- streak = **2**, last read **yesterday** → the nudge fires, and the next
  completed session hits **3** = milestone celebration
- session size level = **1** (short sessions, quick to demo)
- quiz attempts cleared, so checkpoints fire again
- Alice parked at **Session_38** with the last read backdated 30h, so the
  recap banner appears

Add `--wipe-events` if you want a completely empty CSV to fill up live.

**Browser prep**
- Log in as `sakshee@gmail.com`
- Zoom to ~110% so the audience can read
- Settings → make sure **Reduce motion is OFF** (you want the animations)
- Have a second tab ready for the CSV export URL

---

## 2. The walkthrough

### Opening line (~30s)
> Reading is declining, but not because people can't read. Streaming is
> engineered with autoplay, cliffhangers and streaks; books have none of that.
> ReadBack borrows those mechanics for public-domain literature — while
> protecting the one thing reading gives you that watching doesn't: you build
> the pictures yourself.

---

### A. Library + reminder nudge → *habit architecture*
**Do:** land on `/library`.

**Point out:** the banner at the top — *"Your 2-day streak is still alive…"*
with a **Continue reading** button that jumps straight back to the saved
position.

> Activation energy is the whole problem. Nothing here asks you to want to read
> more — it just makes starting take one click. In-app only, no email or push.

Five books, each with its own progress bar.

---

### B. Open Alice → *mood theming + progress*
**Do:** click **Alice's Adventures in Wonderland**.

**Point out:**
- the page tints **green** — each book has its own palette, stored in the
  database so every pilot user sees the same one. Decorative only, never scene
  imagery. Contrast is automatically tested to WCAG AA.
- top bar: **progress ring** (how far through this session), streak, reading
  pace, book progress bar underneath.

---

### C. The recap banner → *situation model reactivation*
**Point out:** *"Previously… Alice enters the Duchess's chaotic kitchen…"*

> You last read this 30 hours ago. Coming back to a novel cold is expensive —
> you've lost the thread. This replays the last few chapters so you can re-enter
> without re-reading. It's cached in the database, never generated live.

---

### D. Visualization checkpoint → **the thesis moment**
**Do:** Sessions → **Session_4** → scroll to the bottom of the passage.
**Important: do NOT press Continue during this step** — it would clear the
recap setup for the finale.

**Point out:** *"Picture this scene before continuing…"* then **How vivid was
it? 1–5**.

> This is the heart of the project. Dual Coding Theory says reading makes you
> generate the visual channel yourself — watching hands it to you. We built an
> artwork reveal, then **deliberately deleted it**, because showing a picture
> supplies the very imagery we're trying to train. Instead we ask how vivid
> *your* mental picture was, which gives us a per-scene imagery measure to set
> against the VVIQ questionnaire in the pilot.

Tap a rating — that logs an event.

---

### E. RSVP focus mode → *attention recovery*
**Do:** click **RSVP mode** in the top bar.

**Point out:** words highlight one at a time, adjustable 100–600 wpm, and the
control bar stays pinned as you scroll.

> RSVP removes eye-movement time, but comprehension drops at high speed, so we
> never use it as the main reading mode — only as a way back in when you stall.

**Optional (needs 25s of stillness):** exit RSVP, then don't touch anything for
~25 seconds. A non-blocking prompt appears: *"Lost focus? Try a 20-second focus
burst."* Accepting streams just the next paragraph, then returns you.
*If you're short on time, describe this rather than waiting for it.*

---

### F. The finale: autoplay → celebration → quiz
**Do:** Sessions → **Session_38** → the recap banner is showing → press
**Continue**.

Three things happen in sequence:

1. **Confetti + "3-day streak!"** — the milestone celebration. Rules are fixed:
   3, 7 and 14 days get progressively bigger bursts, everything else the
   standard one. Deterministic, so the reward schedule can't contaminate the
   pilot data.
2. **Autoplay countdown** — *"Next micro-session starting… 3, 2, 1"* with
   pause / cancel / continue-now.
   > Straight out of Netflix. The default is to keep going; stopping is the
   > thing that takes a decision.
3. **The comprehension quiz** fires, with all three question types:
   - **sequencing** — put 4 events in story order (click them in sequence)
   - **relationship** — match characters to their roles via dropdowns
   - **inference** — why does the Cheshire Cat's grin suggest…

Answer and submit → scored server-side, shows a percentage.

> Retrieval practice: being tested on material strengthens memory more than
> rereading it. It's also our objective comprehension measure for the pilot.

---

### G. Pace, progressive length, settings
**Point out** in the top bar: **wpm with a trend arrow** and *"1h 20m left"*.

> Words per minute of *active* time, derived from the event log — we subtract
> time the tab was hidden, and throw out implausible samples.

**Say** (nothing to click): sessions start as single ~2–3 minute chunks, then
merge into 2 after 5 completed sessions and 3 after 15 — never crossing a
cliffhanger or a chapter break.

> Habituation. You rebuild attention tolerance the way you'd build endurance.

**Do:** open **Settings**.
- **Reduce motion** — turns off every animation; follows the OS setting by
  default. Accessibility, not decoration.
- **Plain theme** — opt out of the tint.
- **Ambient sound** — pick Rain → **Play**, nudge the volume slider.
  > Off by default, starts only on a click, and completely separate from
  > session timing.

---

### H. The research layer → *close here*
**Do:** open in the second tab:
```
http://localhost:8000/admin/export/events.csv?token=readback-admin-dev
```
Open the downloaded file.

**Point out:** every row is `user, book, chapter, micro-session, event type,
JSON metadata, timestamp` — session durations, RSVP wpm, quiz scores, vividness
ratings, nudge clicks, celebrations.

> This is an academic project, so instrumentation came before polish. **22
> event types** are logged. Nothing in the pilot is measured by asking people
> what they remember doing — it's all in here, exportable to Sheets. The
> endpoint is token-protected because it's participant data.

**Optional, if there's time:**
```bash
cd backend && python -m pytest tests/ -q      # 172 passed
```
> Tests cover streak maths, chapter detection across 6 extra books, quiz
> scoring, pace outlier rejection — and one that parses the theme CSS and fails
> if any palette drops below WCAG AA contrast.

---

## 3. Exact jump targets

| Book | URL | Theme | Visualization prompts at | Quiz |
|---|---|---|---|---|
| Alice | `/read/2` | meadow | 4, 8, 11, 15, 16, 20 | jump to **38**, press Continue |
| Tom Sawyer | `/read/3` | sunlit | 4, 8, 12, 16, 19, 23 | jump to **41**, press Continue |
| Frankenstein | `/read/4` | moonlit | 4, 7, 10, 11, 15, 19 | jump to **47**, press Continue |
| Pride & Prejudice | `/read/5` | rose | 4, 7, 9, 11, 13, 17 | jump to **53**, press Continue |
| Yellow Wallpaper | `/read/1` | faded | 4, 7, 10, 11 | none (single chapter) |

Visualization prompts sit at the **bottom** of the passage — scroll down.

---

## 4. If something breaks

| Problem | Fix |
|---|---|
| Nudge banner missing | Re-run `demo_setup`, then hard-refresh the library |
| Recap banner missing | You pressed Continue earlier, which reset the timestamp — re-run `demo_setup` |
| Quiz doesn't fire | Already answered it — `demo_setup` clears attempts; re-run it |
| No confetti | Reduce motion is on (Settings), or the streak wasn't at 2 — re-run `demo_setup` |
| `connection refused` on 5433 | `docker compose up -d db`, wait ~10s |
| Page blank / 404s | Backend isn't running — check Terminal 2 |
| Ambient sound silent | Check system volume; it only starts on a click, never automatically |

**Golden rule:** almost everything is fixed by re-running `demo_setup` and
refreshing.

---

## 5. Be honest about these if asked

- **Recaps** are currently first-sentence extraction plus hand-written
  summaries for Alice. The Groq pipeline is built and cached-at-seed-time, but
  the generated recaps haven't been human-reviewed yet.
- **No artwork** on the visualization checkpoint is a **deliberate design
  decision**, not an unfinished feature. Say so — otherwise it reads as a gap.
- **Chapter detection is heuristic.** Verified on the 5 seed books plus Dracula,
  Moby Dick, Jane Eyre, Metamorphosis and A Tale of Two Cities. Sherlock Holmes
  still picks up spurious front matter, which is why it isn't seeded.
- **Ambient audio licences** aren't recorded in CREDITS.md yet.
- **Not deployed** — local only so far. Deployment is the next milestone before
  the pilot.
- **The survey** is designed but not yet collecting responses.
