# Tools

## datetime

**Installed at:** `~/.openclaw/skills/datetime/SKILL.md`

Fetches current date and time from the system clock using the `date` command. No external API or network needed.

**Invoke when:** user asks what time it is, what day it is, or needs a timestamp.

**Key commands:**
- Full readable: `date '+%A, %B %-d %Y at %I:%M:%S %p %Z'`
- ISO 8601 UTC: `date -u '+%Y-%m-%dT%H:%M:%SZ'`
- Specific timezone: `TZ=America/New_York date '+%H:%M:%S %Z'`

---

## form_monitor

**Source:** `NemoDemo/form_monitor_daemon.py` (runs on host, pushes events via `openclaw agent`)

Monitors a webcam feed and pushes structured events to this agent when a patient starts or stops an exercise.

**Events pushed:**
- `exercise_identified` — motion detected and classified
- `patient_paused` — patient stopped moving
- `form_score` — per-tick form quality score (once comparator is implemented)

No commands to run — events arrive as inbound messages.
