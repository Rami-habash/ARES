---
name: session-report
description: Generate a structured clinical session report for a doctor or PT from session memories
user-invocable: true
metadata: {"openclaw": {"emoji": "📋"}}
---

# Session Report Skill

When asked to generate a report, produce a structured markdown report using the session memories provided in the `session_ended` event. Each memory entry is formatted as `timestamp: exercise | coaching note`.

## Report Format

```
## Solstice Session Report — {patient_id} — {date}

### Exercises Performed
- List each distinct exercise seen in the memories

### Form Issues Flagged
- List specific form problems mentioned in coaching notes

### Coaching Given
- Bullet each distinct coaching cue that was given

### Recommendations for PT/Doctor
- 2-3 actionable recommendations based on recurring issues
```

## Rules
- Only include what is in the memories. Do not invent findings.
- If a form issue appeared more than once, note the frequency (e.g. "flagged 3x").
- Keep recommendations grounded — phrase them as observations, not diagnoses.
- Output the report as clean markdown, nothing else.
