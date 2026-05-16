---
name: datetime
description: Fetch the current date and time from the system clock
user-invocable: true
metadata: {"openclaw": {"emoji": "🕐"}}
---

# DateTime

Fetches the current date and time directly from the system clock. Always run the command — never guess or use training knowledge for the current time.

## Usage

**Full human-readable datetime:**

	date '+%A, %B %-d %Y at %I:%M:%S %p %Z'

**ISO 8601 (UTC):**

	date -u '+%Y-%m-%dT%H:%M:%SZ'

**Date only:**

	date '+%Y-%m-%d'

**Time only (local):**

	date '+%H:%M:%S'

**Specific timezone:**

	TZ=America/New_York date '+%A, %B %-d %Y at %I:%M:%S %p %Z'
	TZ=Europe/London date '+%A, %B %-d %Y at %I:%M:%S %p %Z'
	TZ=Asia/Tokyo date '+%A, %B %-d %Y at %I:%M:%S %p %Z'

## Rules

- ALWAYS run the `date` command — never rely on training data for the current time
- Report the exact output from the command, unmodified
- If the user specifies a timezone, use `TZ=<Region/City>` prefix
- If the user asks "what time is it" or "what's today's date", invoke this skill immediately
- Do not add commentary about the date unless asked
