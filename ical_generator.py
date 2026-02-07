#!/usr/bin/env python3
"""
iCal Generator Module for Gradescope Assignments

This module provides functions to generate iCal (.ics) files from Gradescope
assignment data. Each event has a stable UID to enable calendar updates.
"""

import re
from datetime import datetime, timedelta
from typing import Optional
from icalendar import Calendar, Event, vText


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats from Gradescope.

    Args:
        date_str: Date string in various formats from Gradescope

    Returns:
        Parsed datetime object or None if parsing fails
    """
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


def create_calendar(assignments: list, prodid: str = "-//Gradescope Calendar Sync//EN") -> Calendar:
    """Create an iCal calendar from a list of assignments.

    Args:
        assignments: List of assignment dicts with keys:
            - name: Assignment name
            - course_name: Course name (short)
            - course_id: Course ID
            - assignment_id: Assignment ID
            - due_date: Due date string
            - url: Assignment URL (optional)
        prodid: Product identifier for the calendar

    Returns:
        icalendar.Calendar object
    """
    cal = Calendar()
    cal.add('prodid', prodid)
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    cal.add('x-wr-calname', 'Gradescope Assignments')
    cal.add('x-wr-timezone', 'America/Los_Angeles')

    for assignment in assignments:
        event = create_event(assignment)
        if event:
            cal.add_component(event)

    return cal


def create_event(assignment: dict) -> Optional[Event]:
    """Create an iCal event from an assignment.

    Args:
        assignment: Dict with assignment data

    Returns:
        icalendar.Event object or None if date parsing fails
    """
    due_date = parse_date(assignment.get('due_date'))
    if not due_date:
        return None

    event = Event()

    # Create title: "Assignment Name - Course Name"
    title = f"{assignment['name']} - {assignment['course_name']}"
    event.add('summary', title)

    # Create stable UID for updates
    course_id = assignment.get('course_id', 'unknown')
    assignment_id = assignment.get('assignment_id', 'unknown')
    uid = f"{course_id}-{assignment_id}@gradescope-sync"
    event.add('uid', uid)

    # Set times (due date as both start and end for deadline-style event)
    event.add('dtstart', due_date)
    event.add('dtend', due_date)

    # Add timestamp for when the event was created/modified
    event.add('dtstamp', datetime.utcnow())

    # Build description
    description_parts = [f"Course: {assignment.get('course_full_name', assignment['course_name'])}"]
    if assignment.get('url'):
        description_parts.append(f"Link: {assignment['url']}")
    event.add('description', '\n'.join(description_parts))

    # Add URL if available
    if assignment.get('url'):
        event.add('url', assignment['url'])

    return event


def generate_ics_content(assignments: list) -> str:
    """Generate iCal file content as a string.

    Args:
        assignments: List of assignment dicts

    Returns:
        iCal file content as string
    """
    cal = create_calendar(assignments)
    return cal.to_ical().decode('utf-8')


def save_ics_file(assignments: list, filepath: str) -> int:
    """Generate and save an iCal file.

    Args:
        assignments: List of assignment dicts
        filepath: Path to save the .ics file

    Returns:
        Number of events added to the calendar
    """
    cal = create_calendar(assignments)

    # Count events
    event_count = len([c for c in cal.walk() if c.name == 'VEVENT'])

    with open(filepath, 'wb') as f:
        f.write(cal.to_ical())

    return event_count
