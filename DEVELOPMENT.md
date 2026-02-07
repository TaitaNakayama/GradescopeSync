# Development Notes - Gradescope Calendar Sync

## Project Overview

Automatically syncs Gradescope assignments to calendars. Two methods available:

| Method | Workflow | Output | Best For |
|--------|----------|--------|----------|
| **iCal** | `generate-ical.yml` | `.ics` file via GitHub Pages | New users (simple setup) |
| **OAuth** | `sync.yml` | Direct Google Calendar sync | You (advanced features) |

Both run twice daily at 8 AM and 8 PM Pacific.

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │         GitHub Actions              │
                    │       (runs on schedule)            │
                    └─────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
           ┌───────────────┐               ┌───────────────┐
           │ generate-ical │               │   sync.yml    │
           │     .yml      │               │   (OAuth)     │
           └───────────────┘               └───────────────┘
                    │                               │
                    ▼                               ▼
           ┌───────────────┐               ┌───────────────┐
           │ docs/         │               │ Google        │
           │ gradescope.ics│               │ Calendar API  │
           └───────────────┘               └───────────────┘
                    │                               │
                    ▼                               ▼
           ┌───────────────┐               ┌───────────────┐
           │ GitHub Pages  │               │ Berkeley      │
           │ (subscribe)   │               │ Calendar      │
           └───────────────┘               └───────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `sync_gradescope.py` | Gradescope scraper + Google Calendar integration |
| `ical_generator.py` | iCal file generation logic |
| `generate_ical.py` | Script to generate `.ics` from Gradescope |
| `.github/workflows/sync.yml` | OAuth workflow (your setup) |
| `.github/workflows/generate-ical.yml` | iCal workflow (for sharing) |
| `setup_google_auth.py` | One-time OAuth token generator |
| `docs/index.html` | Landing page for iCal subscribers |
| `docs/gradescope.ics` | Generated iCal file (committed by workflow) |

## GitHub Secrets

### For iCal (minimum - what new users need)
| Secret | Value |
|--------|-------|
| `GRADESCOPE_EMAIL` | Gradescope email |
| `GRADESCOPE_PASSWORD` | Gradescope direct login password |

### For OAuth (your setup - adds Google sync)
| Secret | Value |
|--------|-------|
| `GRADESCOPE_EMAIL` | aryanvalsa@berkeley.edu |
| `GRADESCOPE_PASSWORD` | Gradescope direct login password |
| `GOOGLE_TOKEN` | Base64-encoded contents of token.json |

To update GOOGLE_TOKEN:
```bash
base64 -i token.json | pbcopy  # Copies to clipboard
# Then paste into GitHub Secrets
```

## Local Development

```bash
# Setup
cd /Users/aryan/Documents/CodeProjects/gradescope-calendar-sync
source venv/bin/activate
pip install -r requirements.txt

# Test iCal generation
GRADESCOPE_EMAIL="aryanvalsa@berkeley.edu" GRADESCOPE_PASSWORD="xxx" python generate_ical.py
cat docs/gradescope.ics

# Test OAuth sync (your calendar)
GRADESCOPE_EMAIL="aryanvalsa@berkeley.edu" GRADESCOPE_PASSWORD="xxx" python sync_gradescope.py

# Cleanup old events from personal calendar
python sync_gradescope.py --cleanup
```

## How the Gradescope Scraper Works

1. **Login**: POST to `/login` with CSRF token + credentials
2. **Get courses**: Parse `/account` page for course links (`/courses/{id}`)
3. **Get assignments**: For each course, parse the assignments table
   - Assignment names from `<a>` links or `<button data-assignment-title="...">`
   - Due dates from `<time class="submissionTimeChart--dueDate" datetime="...">`

## iCal Generation

The iCal generator creates events with stable UIDs:
```
{course_id}-{assignment_id}@gradescope-sync
```

This allows calendar apps to update existing events when due dates change, rather than creating duplicates.

## Common Issues & Fixes

### "Invalid credentials"
- User uses Berkeley SSO, not direct password
- Fix: Set a direct Gradescope password in Account Settings

### Wrong dates (release date instead of due date)
- Old code grabbed wrong column
- Fix: Use `<time class="submissionTimeChart--dueDate">` element's `datetime` attribute

### Missing assignments
- Some assignments have buttons (unsubmitted) instead of links
- Fix: Also check `<button data-assignment-title="...">` for assignment names

### Google token expired (OAuth only)
- Re-run `setup_google_auth.py` locally
- Update `GOOGLE_TOKEN` secret with new base64-encoded token

### iCal not updating in Google Calendar
- Google Calendar caches aggressively (can take 12-24 hours)
- For immediate updates, remove and re-add the subscription

## Gradescope Page Structure (as of Jan 2026)

```html
<!-- Course page assignment row -->
<tr role="row">
  <th>
    <a href="/courses/123/assignments/456/submissions/789">Assignment Name</a>
    <!-- OR for unsubmitted: -->
    <button data-assignment-title="Assignment Name" data-assignment-id="456">Submit</button>
  </th>
  <td>Submitted / No Submission</td>
  <td>
    <time class="submissionTimeChart--releaseDate" datetime="2026-01-20 12:00:00 -0800">Jan 20</time>
    <time class="submissionTimeChart--dueDate" datetime="2026-01-24 16:00:00 -0800">Jan 24 at 4:00PM</time>
  </td>
</tr>
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GRADESCOPE_EMAIL` | (required) | Gradescope login email |
| `GRADESCOPE_PASSWORD` | (required) | Gradescope direct password |
| `GOOGLE_TOKEN` | (optional) | Base64 token for OAuth sync |
| `GOOGLE_CALENDAR_NAME` | "Berkeley Calendar" | Target calendar name (OAuth only) |

## Cron Schedule

Both workflows: `0 4,16 * * *` (8 AM and 8 PM Pacific in UTC)

- GitHub Actions uses UTC
- 8 AM Pacific = 16:00 UTC (PST) / 15:00 UTC (PDT)
- 8 PM Pacific = 04:00 UTC (PST) / 03:00 UTC (PDT)

## If Gradescope Changes Their Website

1. Log into Gradescope in browser
2. Inspect the assignments table structure
3. Update `get_assignments()` method in `sync_gradescope.py`
4. Key things to find:
   - How assignment names are displayed
   - Where the due date is stored (look for `<time>` elements)
   - Any new class names or data attributes

## Repository Structure

```
gradescope-calendar-sync/
├── .github/workflows/
│   ├── sync.yml              # OAuth sync (your calendar)
│   └── generate-ical.yml     # iCal generation (shareable)
├── docs/
│   ├── index.html            # Landing page for subscribers
│   └── gradescope.ics        # Generated iCal (auto-committed)
├── sync_gradescope.py        # Gradescope + Google Calendar
├── ical_generator.py         # iCal creation logic
├── generate_ical.py          # iCal generation script
├── setup_google_auth.py      # OAuth token setup
├── requirements.txt          # Dependencies
├── README.md                 # User-facing (iCal setup)
├── ADVANCED_SETUP.md         # OAuth setup guide
├── DEVELOPMENT.md            # This file
└── WALKTHROUGH.md            # How the code works
```
