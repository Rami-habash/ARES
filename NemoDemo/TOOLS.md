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

<!-- Add new tools below this line as you install them -->
