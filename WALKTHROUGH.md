# Complete Walkthrough: Gradescope to Google Calendar Sync

A detailed explanation of how this project was built, for learning purposes.

## 1. The Problem

**Goal**: Automatically sync Gradescope assignment due dates to Google Calendar, running in the cloud (not dependent on your laptop being on).

**Constraints**:
- Gradescope has no official API
- Need to authenticate with both Gradescope and Google
- Must run automatically without user intervention
- Free solution (no paid services)

---

## 2. Initial Thought Process

### What do we need?

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Gradescope    │────▶│   Our Script    │────▶│ Google Calendar │
│   (scraping)    │     │   (Python)      │     │     (API)       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                    ┌─────────────────┐
                    │  GitHub Actions │
                    │  (runs script)  │
                    └─────────────────┘
```

### Technology Choices

| Need | Solution | Why |
|------|----------|-----|
| Scrape Gradescope | `requests` + `BeautifulSoup` | No API available, need to parse HTML |
| Google Calendar | Google Calendar API | Official API, reliable |
| Run automatically | GitHub Actions | Free, runs on schedule, no server needed |
| Store credentials | GitHub Secrets | Encrypted, secure |
| Language | Python | Great libraries for web scraping and APIs |

---

## 3. The Code - Step by Step

### File Structure

```
gradescope-calendar-sync/
├── .github/
│   └── workflows/
│       └── sync.yml          # GitHub Actions workflow
├── sync_gradescope.py        # Main script
├── setup_google_auth.py      # One-time OAuth setup
├── requirements.txt          # Dependencies
├── credentials.json          # Google OAuth client (local only)
├── token.json               # Google OAuth token (local only)
└── DEVELOPMENT.md           # Documentation
```

---

### Part A: Gradescope Scraper

#### The Challenge
Gradescope doesn't have an API. We need to:
1. Log in like a browser would
2. Navigate to pages and parse HTML
3. Extract assignment data

#### Step 1: Login

```python
import requests
from bs4 import BeautifulSoup

class GradescopeClient:
    def __init__(self, email: str, password: str):
        self.session = requests.Session()  # Maintains cookies across requests
        self._login(email, password)
```

**Why `requests.Session()`?**
- A session persists cookies automatically
- After login, the session "remembers" we're authenticated

#### Step 2: Handle CSRF Token

Websites use CSRF tokens to prevent automated logins. We need to:
1. GET the login page
2. Extract the hidden CSRF token
3. Include it in our POST request

```python
def _login(self):
    # Step 1: Get login page
    login_page = self.session.get("https://www.gradescope.com/login")
    soup = BeautifulSoup(login_page.text, "html.parser")

    # Step 2: Find CSRF token (hidden input field)
    csrf_input = soup.find("input", {"name": "authenticity_token"})
    csrf_token = csrf_input.get("value")

    # Step 3: POST login with token
    login_data = {
        "authenticity_token": csrf_token,
        "session[email]": self.email,
        "session[password]": self.password,
        "session[remember_me]": "0",
        "commit": "Log In",
    }

    response = self.session.post(
        "https://www.gradescope.com/login",
        data=login_data,
        allow_redirects=True
    )
```

**How I figured this out:**
1. Opened browser DevTools (F12)
2. Went to Network tab
3. Logged into Gradescope manually
4. Looked at the POST request to `/login`
5. Copied the form fields

#### Step 3: Get Courses

After login, we're redirected to `/account` which lists all courses.

```python
def get_courses(self) -> list:
    response = self.session.get("https://www.gradescope.com/account")
    soup = BeautifulSoup(response.text, "html.parser")

    courses = []

    # Find all links that match /courses/{number}
    for link in soup.find_all("a", href=re.compile(r"/courses/\d+")):
        href = link.get("href")  # e.g., "/courses/1226014"
        course_id = href.split("/")[-1]  # e.g., "1226014"

        # Get course name from heading inside the link
        heading = link.find(["h3", "h4"])
        short_name = heading.get_text(strip=True) if heading else "Unknown"

        courses.append({
            "id": course_id,
            "short_name": short_name,
            "url": f"https://www.gradescope.com{href}"
        })

    return courses
```

**The regex `r"/courses/\d+"`:**
- `/courses/` - literal text
- `\d+` - one or more digits
- Matches: `/courses/1226014`, `/courses/999`, etc.

#### Step 4: Get Assignments (The Tricky Part)

Each course page has a table of assignments. The HTML structure:

```html
<tr role="row">
  <th>
    <a href="/courses/123/assignments/456">Assignment Name</a>
    <!-- OR for unsubmitted: -->
    <button data-assignment-title="HW 1">Submit HW 1</button>
  </th>
  <td>
    <time class="submissionTimeChart--dueDate"
          datetime="2026-01-24 16:00:00 -0800">
      Jan 24 at 4:00PM
    </time>
  </td>
</tr>
```

```python
def get_assignments(self, course_id: str) -> list:
    response = self.session.get(f"https://www.gradescope.com/courses/{course_id}")
    soup = BeautifulSoup(response.text, "html.parser")

    assignments = []

    for row in soup.find_all("tr", role="row"):
        # Skip header rows
        if row.find(role="columnheader"):
            continue

        # Method 1: Get name from link (submitted assignments)
        name_link = row.find("a", href=re.compile(r"/assignments/\d+"))
        if name_link:
            name = name_link.get_text(strip=True)
        else:
            # Method 2: Get name from button (unsubmitted)
            button = row.find("button", attrs={"data-assignment-title": True})
            if button:
                name = button.get("data-assignment-title")
            else:
                continue  # No assignment found in this row

        # Get due date from <time> element
        due_time = row.find("time", class_="submissionTimeChart--dueDate")
        if due_time:
            due_date = due_time.get("datetime")  # "2026-01-24 16:00:00 -0800"

        assignments.append({
            "name": name,
            "due_date": due_date
        })

    return assignments
```

**Why two methods for getting names?**
- Submitted assignments have a **link** to view submission
- Unsubmitted assignments have a **button** to submit
- We need to handle both cases

**The bug we fixed:**
Initially, I grabbed the wrong date (release date instead of due date). The fix was to specifically target `class="submissionTimeChart--dueDate"` instead of just any `<time>` element.

---

### Part B: Google Calendar Integration

#### The Challenge
Google Calendar requires OAuth 2.0 authentication - a multi-step process.

#### OAuth Flow Explained

```
┌──────────┐    1. Request auth     ┌──────────┐
│   User   │───────────────────────▶│  Google  │
│          │◀───────────────────────│          │
└──────────┘    2. Auth code        └──────────┘
      │
      │ 3. Exchange code
      ▼
┌──────────┐    4. Access token     ┌──────────┐
│Our Script│◀───────────────────────│  Google  │
│          │───────────────────────▶│ Calendar │
└──────────┘    5. API requests     └──────────┘
```

#### Step 1: Google Cloud Setup (One-time)

1. Create project in Google Cloud Console
2. Enable Google Calendar API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download `credentials.json`

#### Step 2: Generate Token (One-time)

```python
# setup_google_auth.py
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/calendar']

def main():
    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json', SCOPES
    )

    # Opens browser for user to authorize
    creds = flow.run_local_server(port=0)

    # Save token for future use
    with open('token.json', 'w') as f:
        f.write(creds.to_json())
```

**What's in token.json?**
```json
{
  "token": "ya29.xxx...",           // Access token (expires in 1 hour)
  "refresh_token": "1//xxx...",     // Used to get new access tokens
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "xxx.apps.googleusercontent.com",
  "client_secret": "xxx",
  "scopes": ["https://www.googleapis.com/auth/calendar"]
}
```

The **refresh_token** is key - it lets us get new access tokens forever without user interaction.

#### Step 3: Use the Calendar API

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class GoogleCalendarClient:
    def __init__(self):
        # Load saved credentials
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

        # Auto-refresh if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        # Build the API client
        self.service = build('calendar', 'v3', credentials=creds)
```

#### Step 4: Create/Update Events

```python
def create_or_update_event(self, title, due_date, calendar_id='primary'):
    # Parse the date string into datetime
    event_datetime = self._parse_date(due_date)

    # Build event body
    event_body = {
        'summary': title,
        'start': {
            'dateTime': event_datetime.isoformat(),
            'timeZone': 'America/Los_Angeles',
        },
        'end': {
            'dateTime': event_datetime.isoformat(),
            'timeZone': 'America/Los_Angeles',
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': 60},      # 1 hour before
                {'method': 'popup', 'minutes': 1440},    # 24 hours before
            ],
        },
    }

    # Check if event already exists (prevent duplicates)
    existing = self.find_event(title, calendar_id)

    if existing:
        # Update existing event
        self.service.events().update(
            calendarId=calendar_id,
            eventId=existing['id'],
            body=event_body
        ).execute()
    else:
        # Create new event
        self.service.events().insert(
            calendarId=calendar_id,
            body=event_body
        ).execute()
```

#### Step 5: Find Calendar by Name

```python
def get_calendar_id(self, calendar_name):
    """Find 'Berkeley Calendar' instead of using 'primary'"""
    calendar_list = self.service.calendarList().list().execute()

    for calendar in calendar_list.get('items', []):
        if calendar.get('summary') == calendar_name:
            return calendar.get('id')

    return None  # Not found
```

---

### Part C: Date Parsing

#### The Challenge
Gradescope dates come in various formats:
- `"2026-01-24 16:00:00 -0800"` (from datetime attribute)
- `"January 24 at 4:00PM"` (from display text)
- `"Jan 24 at 4:00 PM"` (abbreviated)

```python
def _parse_date(self, date_str: str) -> datetime:
    # Try multiple formats
    formats = [
        "%Y-%m-%d %H:%M:%S %z",   # "2026-01-24 16:00:00 -0800"
        "%B %d at %I:%M%p",        # "January 24 at 4:00PM"
        "%b %d at %I:%M %p",       # "Jan 24 at 4:00 PM"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Fallback: regex extraction
    match = re.search(r"(\w+)\s+(\d+)\s+at\s+(\d+):(\d+)\s*([AP]M)", date_str)
    if match:
        month_str, day, hour, minute, ampm = match.groups()
        # ... convert to datetime
```

**Why so many formats?**
- Different elements on the page show dates differently
- We want to handle all cases gracefully

---

### Part D: GitHub Actions

#### The Workflow File

```yaml
# .github/workflows/sync.yml
name: Sync Gradescope to Google Calendar

on:
  schedule:
    # Cron syntax: minute hour day month weekday
    # "0 4,16 * * *" = at minute 0, hours 4 and 16, every day
    # 4:00 UTC = 8 PM Pacific, 16:00 UTC = 8 AM Pacific
    - cron: '0 4,16 * * *'

  workflow_dispatch:  # Allow manual trigger

jobs:
  sync:
    runs-on: ubuntu-latest  # Free Linux VM

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'  # Cache dependencies for speed

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run sync script
        run: python sync_gradescope.py
        env:
          # Secrets are injected as environment variables
          GRADESCOPE_EMAIL: ${{ secrets.GRADESCOPE_EMAIL }}
          GRADESCOPE_PASSWORD: ${{ secrets.GRADESCOPE_PASSWORD }}
          GOOGLE_TOKEN: ${{ secrets.GOOGLE_TOKEN }}
```

#### How Secrets Work

```python
# In sync_gradescope.py
import os
import base64

# Read from environment variables (set by GitHub Actions)
email = os.environ.get("GRADESCOPE_EMAIL")
password = os.environ.get("GRADESCOPE_PASSWORD")

# Google token is base64-encoded (because it's JSON with special chars)
google_token = os.environ.get("GOOGLE_TOKEN")
if google_token:
    token_data = base64.b64decode(google_token).decode('utf-8')
    with open('token.json', 'w') as f:
        f.write(token_data)
```

**Why base64 encode the token?**
- `token.json` contains JSON with quotes, newlines, special characters
- GitHub Secrets handle plain strings better
- Base64 converts any data to safe ASCII characters

---

## 4. Challenges Faced & Solutions

### Challenge 1: SSO Login
**Problem**: User logs into Gradescope via Berkeley SSO, not email/password.
**Solution**: Set a direct Gradescope password in Account Settings.

### Challenge 2: Wrong Dates
**Problem**: Script grabbed release date instead of due date.
**Solution**: Target specific `<time class="submissionTimeChart--dueDate">` element.

### Challenge 3: Missing Assignments
**Problem**: Unsubmitted assignments weren't found.
**Solution**: Also check for `<button data-assignment-title="...">`.

### Challenge 4: Broken Library
**Problem**: `gradescopecalendar` package was outdated.
**Solution**: Wrote custom scraper from scratch.

### Challenge 5: Duplicate Events
**Problem**: Events were in wrong calendar.
**Solution**: Added `get_calendar_id()` to find "Berkeley Calendar", plus cleanup function.

---

## 5. Final Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     GitHub Actions                          │
│                   (runs at 8 AM & 8 PM)                     │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │                  sync_gradescope.py                    │ │
│  │                                                        │ │
│  │  ┌─────────────────┐      ┌──────────────────────┐   │ │
│  │  │ GradescopeClient│      │ GoogleCalendarClient │   │ │
│  │  │                 │      │                      │   │ │
│  │  │ • _login()      │      │ • get_calendar_id()  │   │ │
│  │  │ • get_courses() │ ───▶ │ • find_event()       │   │ │
│  │  │ • get_assign()  │      │ • create_or_update() │   │ │
│  │  └─────────────────┘      └──────────────────────┘   │ │
│  │           │                         │                 │ │
│  │           ▼                         ▼                 │ │
│  │    ┌───────────┐            ┌─────────────┐          │ │
│  │    │Gradescope │            │Google Cal   │          │ │
│  │    │  Website  │            │    API      │          │ │
│  │    └───────────┘            └─────────────┘          │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  Environment Variables (from GitHub Secrets):               │
│  • GRADESCOPE_EMAIL                                        │
│  • GRADESCOPE_PASSWORD                                     │
│  • GOOGLE_TOKEN (base64)                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. How to Build Something Similar

### General Pattern for Any Scraper → API Integration

1. **Understand the source** (Gradescope)
   - Use browser DevTools to see network requests
   - Identify authentication method (cookies, tokens, etc.)
   - Find the data you need in the HTML

2. **Understand the destination** (Google Calendar)
   - Read the API documentation
   - Set up authentication (OAuth, API keys, etc.)
   - Test with simple requests first

3. **Write the glue code**
   - Scrape data into a standard format
   - Transform to match API requirements
   - Handle errors gracefully

4. **Automate it**
   - GitHub Actions for scheduled runs
   - Store secrets securely
   - Add logging for debugging

### Key Libraries to Know

```python
# Web scraping
import requests              # HTTP requests
from bs4 import BeautifulSoup  # HTML parsing
import re                    # Pattern matching

# Google APIs
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Utilities
from datetime import datetime
import os                    # Environment variables
import base64               # Encoding
```

---

---

## 7. Making It Shareable: iCal Support

### The Problem with OAuth

The original OAuth approach works great for one person, but sharing is hard:
- Each user needs to set up Google Cloud Console
- Each user needs to generate their own OAuth token
- 30+ minutes of setup per person

### The iCal Solution

iCal is a universal calendar format (`.ics` files). Instead of pushing to Google Calendar, we generate a file that any calendar app can subscribe to.

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Gradescope    │────▶│  GitHub Actions │────▶│  .ics file      │
│   (scraping)    │     │  (generates)    │     │  (GitHub Pages) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                              ┌──────────────────┬──────┴──────┐
                              ▼                  ▼             ▼
                        ┌──────────┐      ┌──────────┐  ┌──────────┐
                        │  Google  │      │  Apple   │  │ Outlook  │
                        │ Calendar │      │ Calendar │  │          │
                        └──────────┘      └──────────┘  └──────────┘
```

### How iCal Works

```python
from icalendar import Calendar, Event

def create_calendar(assignments):
    cal = Calendar()
    cal.add('prodid', '-//Gradescope Calendar Sync//EN')
    cal.add('version', '2.0')

    for assignment in assignments:
        event = Event()
        event.add('summary', f"{assignment['name']} - {assignment['course']}")
        event.add('dtstart', assignment['due_date'])
        event.add('dtend', assignment['due_date'])

        # Stable UID enables updates without duplicates
        uid = f"{assignment['course_id']}-{assignment['assignment_id']}@gradescope-sync"
        event.add('uid', uid)

        cal.add_component(event)

    return cal.to_ical()
```

**Key insight**: The UID (Unique Identifier) lets calendar apps know when an event is being updated vs. when it's new. Format: `{course_id}-{assignment_id}@gradescope-sync`

### The Template Model

Each user creates their own repository from the template and runs their own instance:

```
┌─────────────────────────────────────────────────────────────────┐
│  Original repo (template)                                       │
└─────────────────────────────────────────────────────────────────┘
                              │ use template
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│ alice/repo    │     │ bob/repo      │     │ carol/repo    │
│ - her creds   │     │ - his creds   │     │ - her creds   │
│ - her .ics    │     │ - his .ics    │     │ - her .ics    │
└───────────────┘     └───────────────┘     └───────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
alice.github.io/...   bob.github.io/...   carol.github.io/...
```

Benefits:
- No central server
- Each user's credentials stay in their own repo
- Free (GitHub Actions + GitHub Pages)
- 5-minute setup vs 30+ minutes for OAuth

### Workflow Comparison

| Step | iCal (new) | OAuth (original) |
|------|------------|------------------|
| 1 | Use template | Use template |
| 2 | Add 2 secrets | Add 2 secrets |
| 3 | Enable GitHub Pages | Create Google Cloud project |
| 4 | Done! | Enable Calendar API |
| 5 | | Create OAuth credentials |
| 6 | | Run local auth script |
| 7 | | Encode token as base64 |
| 8 | | Add 3rd secret |

---

## 8. Summary

**Total lines of code**: ~700
**Time to build**: ~4 hours (with debugging)
**Cost**: Free (GitHub Actions + GitHub Pages)

**The core insight**: Most websites can be automated by:
1. Mimicking browser requests
2. Parsing the HTML response
3. Extracting the data you need

**The sharing insight**: Universal formats (like iCal) make it easy for others to use your tool without complex setup.

The trickiest parts are usually authentication and handling edge cases in the HTML structure.
