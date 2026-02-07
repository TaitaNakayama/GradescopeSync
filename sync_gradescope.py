#!/usr/bin/env python3
"""
Gradescope to Google Calendar Sync Script

This script syncs assignments from Gradescope to Google Calendar.
It handles duplicate prevention and updates existing events when due dates change.

Environment Variables Required:
- GRADESCOPE_EMAIL: Your Gradescope email address
- GRADESCOPE_PASSWORD: Your Gradescope password
- GOOGLE_TOKEN: Base64-encoded contents of token.json (for GitHub Actions)

For local development, place credentials.json and token.json in the same directory.
"""

import os
import sys
import json
import base64
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import requests
from bs4 import BeautifulSoup

# Google Calendar imports
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
GRADESCOPE_BASE_URL = "https://www.gradescope.com"


class GradescopeClient:
    """Client for interacting with Gradescope."""

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self._login()

    def _login(self):
        """Log into Gradescope."""
        # Get the login page to get CSRF token
        login_page = self.session.get(f"{GRADESCOPE_BASE_URL}/login")
        soup = BeautifulSoup(login_page.text, "html.parser")

        # Find CSRF token
        csrf_token = None
        csrf_input = soup.find("input", {"name": "authenticity_token"})
        if csrf_input:
            csrf_token = csrf_input.get("value")

        if not csrf_token:
            raise Exception("Could not find CSRF token on login page")

        # Perform login
        login_data = {
            "authenticity_token": csrf_token,
            "session[email]": self.email,
            "session[password]": self.password,
            "session[remember_me]": "0",
            "commit": "Log In",
            "session[remember_me_sso]": "0"
        }

        response = self.session.post(
            f"{GRADESCOPE_BASE_URL}/login",
            data=login_data,
            allow_redirects=True
        )

        # Check if login was successful by looking for courses page
        if "Invalid email/password combination" in response.text:
            raise Exception("Invalid credentials")

        if "/account" not in response.url and "/courses" not in response.text:
            raise Exception("Login failed - unexpected redirect")

    def get_courses(self) -> list:
        """Get all courses from the account page."""
        response = self.session.get(f"{GRADESCOPE_BASE_URL}/account")
        soup = BeautifulSoup(response.text, "html.parser")

        courses = []

        # Find all course links (new structure)
        for link in soup.find_all("a", href=re.compile(r"/courses/\d+")):
            href = link.get("href", "")
            course_id = href.split("/")[-1]

            # Get course name from the link content
            heading = link.find(["h3", "h4", "heading"])
            if heading:
                short_name = heading.get_text(strip=True)
            else:
                short_name = "Unknown Course"

            # Get full name
            name_div = link.find("div", class_=re.compile(r"courseBox--name|name"))
            full_name = name_div.get_text(strip=True) if name_div else short_name

            # Try to get assignment count
            count_div = link.find(string=re.compile(r"\d+ assignment"))

            courses.append({
                "id": course_id,
                "short_name": short_name,
                "full_name": full_name,
                "url": f"{GRADESCOPE_BASE_URL}{href}"
            })

        return courses

    def get_assignments(self, course_id: str) -> list:
        """Get all assignments for a course."""
        response = self.session.get(f"{GRADESCOPE_BASE_URL}/courses/{course_id}")
        soup = BeautifulSoup(response.text, "html.parser")

        assignments = []

        # Find assignment table rows
        for row in soup.find_all("tr", role="row"):
            # Skip header rows (they have columnheader role)
            if row.find(role="columnheader"):
                continue

            # Get assignment name and ID
            name = None
            href = None
            aid = None

            # Method 1: Link (for submitted/viewable assignments)
            name_link = row.find("a", href=re.compile(r"/assignments/\d+"))
            if name_link:
                name = name_link.get_text(strip=True)
                href = name_link.get("href", "")
                aid_match = re.search(r"/assignments/(\d+)", href)
                aid = aid_match.group(1) if aid_match else None

            # Method 2: Button with data-assignment-title (for unsubmitted assignments)
            if not name:
                submit_button = row.find("button", attrs={"data-assignment-title": True})
                if submit_button:
                    name = submit_button.get("data-assignment-title")
                    aid = submit_button.get("data-assignment-id")

            if not name:
                continue

            # Get DUE date - use the <time> element with class submissionTimeChart--dueDate
            due_date = None

            # Method 1: Best - use datetime attribute from time element
            due_time_elem = row.find("time", class_="submissionTimeChart--dueDate")
            if due_time_elem:
                due_date = due_time_elem.get("datetime")

            # Method 2: Hidden column with due date
            if not due_date:
                hidden_cells = row.find_all("td", class_="hidden-column")
                if len(hidden_cells) >= 2:
                    # Second hidden column is typically the due date
                    due_date = hidden_cells[1].get_text(strip=True)

            # Method 3: Look for time element with "Due at" in aria-label
            if not due_date:
                for time_elem in row.find_all("time"):
                    aria_label = time_elem.get("aria-label", "")
                    if "Due at" in aria_label:
                        due_date = time_elem.get("datetime") or time_elem.get_text(strip=True)
                        break

            assignments.append({
                "name": name,
                "id": aid,
                "due_date": due_date,
                "url": f"{GRADESCOPE_BASE_URL}{href}" if href else f"{GRADESCOPE_BASE_URL}/courses/{course_id}/assignments/{aid}" if aid else None
            })

        return assignments


class GoogleCalendarClient:
    """Client for interacting with Google Calendar."""

    def __init__(self, token_path: str = "token.json", credentials_path: str = "credentials.json"):
        self.token_path = Path(token_path)
        self.credentials_path = Path(credentials_path)
        self.service = self._get_service()

    def _get_service(self):
        """Get authenticated Google Calendar service."""
        creds = None

        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif self.credentials_path.exists():
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)
            else:
                raise Exception("No valid credentials found")

            # Save refreshed credentials
            with open(self.token_path, 'w') as f:
                f.write(creds.to_json())

        return build('calendar', 'v3', credentials=creds)

    def get_calendar_id(self, calendar_name: str) -> Optional[str]:
        """Find a calendar ID by its name."""
        try:
            calendar_list = self.service.calendarList().list().execute()
            for calendar in calendar_list.get('items', []):
                if calendar.get('summary') == calendar_name:
                    return calendar.get('id')
        except Exception as e:
            print(f"Warning: Error listing calendars: {e}")
        return None

    def find_event(self, title: str, calendar_id: str = 'primary') -> Optional[dict]:
        """Find an existing event by title."""
        try:
            # Search for events with matching title
            events_result = self.service.events().list(
                calendarId=calendar_id,
                q=title,
                maxResults=10,
                singleEvents=True
            ).execute()

            events = events_result.get('items', [])
            for event in events:
                if event.get('summary') == title:
                    return event
        except Exception as e:
            print(f"Warning: Error searching for event: {e}")

        return None

    def create_or_update_event(self, title: str, due_date: str, description: str = "",
                               location: str = "", calendar_id: str = 'primary') -> dict:
        """Create or update a calendar event."""
        # Parse the due date
        event_datetime = self._parse_date(due_date)
        if not event_datetime:
            print(f"Warning: Could not parse date '{due_date}' for '{title}'")
            return None

        event_body = {
            'summary': title,
            'description': description,
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
                    {'method': 'popup', 'minutes': 60},
                    {'method': 'popup', 'minutes': 1440},  # 24 hours
                ],
            },
        }

        if location:
            event_body['location'] = location

        # Check if event already exists
        existing_event = self.find_event(title, calendar_id)

        if existing_event:
            # Update existing event
            event = self.service.events().update(
                calendarId=calendar_id,
                eventId=existing_event['id'],
                body=event_body
            ).execute()
            return {'action': 'updated', 'event': event}
        else:
            # Create new event
            event = self.service.events().insert(
                calendarId=calendar_id,
                body=event_body
            ).execute()
            return {'action': 'created', 'event': event}

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats from Gradescope."""
        if not date_str:
            return None

        # Clean up the string
        date_str = date_str.strip()

        # Get current year for dates without year
        current_year = datetime.now().year

        # Common date formats from Gradescope (with year)
        formats_with_year = [
            "%Y-%m-%d %H:%M:%S %z",  # "2026-01-22 12:30:00 -0800" (from datetime attr)
            "%Y-%m-%dT%H:%M:%S%z",   # ISO format with timezone
            "%Y-%m-%dT%H:%M:%S",     # ISO format without timezone
            "%b %d, %Y %I:%M %p",    # "Jan 15, 2026 11:59 PM"
            "%b %d, %Y at %I:%M %p", # "Jan 15, 2026 at 11:59 PM"
            "%B %d, %Y %I:%M %p",    # "January 15, 2026 11:59 PM"
            "%B %d, %Y at %I:%M %p", # "January 15, 2026 at 11:59 PM"
            "%m/%d/%Y %I:%M %p",     # "01/15/2026 11:59 PM"
        ]

        # Try formats with year first
        for fmt in formats_with_year:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Formats WITHOUT year (need to add current year)
        formats_without_year = [
            "%B %d at %I:%M%p",      # "January 24 at 4:00PM"
            "%B %d at %I:%M %p",     # "January 24 at 4:00 PM"
            "%b %d at %I:%M%p",      # "Jan 24 at 4:00PM"
            "%b %d at %I:%M %p",     # "Jan 24 at 4:00 PM"
            "%B %d %I:%M%p",         # "January 24 4:00PM"
            "%B %d %I:%M %p",        # "January 24 4:00 PM"
        ]

        for fmt in formats_without_year:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # Add current year
                return parsed.replace(year=current_year)
            except ValueError:
                continue

        # Try regex extraction for "Month DD at HH:MMAM/PM" pattern
        match = re.search(
            r"(\w+)\s+(\d+)\s+at\s+(\d+):(\d+)\s*([AP]M)",
            date_str,
            re.IGNORECASE
        )
        if match:
            month_str, day, hour, minute, ampm = match.groups()
            try:
                # Parse month name
                month_dt = datetime.strptime(month_str, "%B")
                month = month_dt.month
            except ValueError:
                try:
                    month_dt = datetime.strptime(month_str, "%b")
                    month = month_dt.month
                except ValueError:
                    return None

            hour = int(hour)
            minute = int(minute)
            day = int(day)

            # Convert to 24-hour format
            if ampm.upper() == "PM" and hour != 12:
                hour += 12
            elif ampm.upper() == "AM" and hour == 12:
                hour = 0

            return datetime(current_year, month, day, hour, minute)

        return None


def setup_google_credentials():
    """Set up Google credentials from environment variable or local file."""
    token_path = Path(__file__).parent / "token.json"

    # Check if running in GitHub Actions (token passed as env var)
    google_token = os.environ.get("GOOGLE_TOKEN")
    if google_token:
        try:
            # Decode base64 token and write to file
            token_data = base64.b64decode(google_token).decode("utf-8")
            token_path.write_text(token_data)
            print("Google credentials loaded from environment variable.")
        except Exception as e:
            print(f"Error decoding GOOGLE_TOKEN: {e}")
            sys.exit(1)
    elif token_path.exists():
        print("Using local token.json file.")
    else:
        print("ERROR: No Google credentials found.")
        print("Either set GOOGLE_TOKEN environment variable or run setup_google_auth.py first.")
        sys.exit(1)


def main():
    """Main sync function."""
    # Get Gradescope credentials from environment
    email = os.environ.get("GRADESCOPE_EMAIL")
    password = os.environ.get("GRADESCOPE_PASSWORD")

    if not email or not password:
        print("ERROR: Missing Gradescope credentials.")
        print("Set GRADESCOPE_EMAIL and GRADESCOPE_PASSWORD environment variables.")
        sys.exit(1)

    # Set up Google credentials
    setup_google_credentials()

    try:
        # Connect to Gradescope
        print(f"Logging into Gradescope as {email}...")
        gs_client = GradescopeClient(email, password)
        print("Logged in successfully!")

        # Get courses
        print("Fetching courses...")
        courses = gs_client.get_courses()
        print(f"Found {len(courses)} courses")

        # Connect to Google Calendar
        print("Connecting to Google Calendar...")
        gcal_client = GoogleCalendarClient()

        # Get target calendar (Berkeley Calendar or fall back to primary)
        target_calendar_name = os.environ.get("GOOGLE_CALENDAR_NAME", "Berkeley Calendar")
        calendar_id = gcal_client.get_calendar_id(target_calendar_name)
        if calendar_id:
            print(f"Using calendar: {target_calendar_name}")
        else:
            print(f"Calendar '{target_calendar_name}' not found, using primary calendar")
            calendar_id = 'primary'

        # Process each course
        total_created = 0
        total_updated = 0
        total_skipped = 0

        for course in courses:
            print(f"\nProcessing: {course['short_name']} - {course['full_name']}")

            assignments = gs_client.get_assignments(course['id'])
            print(f"  Found {len(assignments)} assignments")

            for assignment in assignments:
                if not assignment['due_date']:
                    print(f"    Skipping '{assignment['name']}' - no due date")
                    total_skipped += 1
                    continue

                title = f"{assignment['name']} - {course['short_name']}"
                description = f"Course: {course['full_name']}\n"
                if assignment['url']:
                    description += f"Link: {assignment['url']}"

                result = gcal_client.create_or_update_event(
                    title=title,
                    calendar_id=calendar_id,
                    due_date=assignment['due_date'],
                    description=description
                )

                if result:
                    if result['action'] == 'created':
                        print(f"    Created: {assignment['name']}")
                        total_created += 1
                    else:
                        print(f"    Updated: {assignment['name']}")
                        total_updated += 1
                else:
                    print(f"    Skipped '{assignment['name']}' - could not parse date")
                    total_skipped += 1

        print(f"\n{'='*50}")
        print("Sync completed!")
        print(f"  Created: {total_created}")
        print(f"  Updated: {total_updated}")
        print(f"  Skipped: {total_skipped}")
        print(f"{'='*50}")

    except Exception as e:
        print(f"ERROR: Sync failed - {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cleanup_old_events():
    """Delete Gradescope events from the personal calendar (one-time cleanup)."""
    setup_google_credentials()

    gcal_client = GoogleCalendarClient()

    # Course codes to look for in event titles
    course_patterns = [
        "COMPSCI 61B", "CS 70", "LS 22", "MATH 54", "Math 54",
        "ASTRON C10", "CS 198"
    ]

    print("Searching for Gradescope events in primary calendar...")

    # Get all events from primary calendar
    deleted_count = 0
    try:
        page_token = None
        while True:
            events_result = gcal_client.service.events().list(
                calendarId='primary',
                maxResults=100,
                singleEvents=True,
                pageToken=page_token
            ).execute()

            events = events_result.get('items', [])

            for event in events:
                title = event.get('summary', '')
                # Check if this is a Gradescope event (has course code pattern)
                for pattern in course_patterns:
                    if pattern in title and ' - ' in title:
                        # This looks like a Gradescope event
                        print(f"  Deleting: {title}")
                        gcal_client.service.events().delete(
                            calendarId='primary',
                            eventId=event['id']
                        ).execute()
                        deleted_count += 1
                        break

            page_token = events_result.get('nextPageToken')
            if not page_token:
                break

    except Exception as e:
        print(f"Error during cleanup: {e}")

    print(f"\nDeleted {deleted_count} Gradescope events from personal calendar.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
        cleanup_old_events()
    else:
        main()
