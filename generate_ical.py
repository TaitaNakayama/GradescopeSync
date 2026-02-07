#!/usr/bin/env python3
"""
Generate iCal file from Gradescope assignments.

This script scrapes Gradescope for assignments and generates an iCal (.ics) file
that can be subscribed to via any calendar application.

Environment Variables Required:
- GRADESCOPE_EMAIL: Your Gradescope email address
- GRADESCOPE_PASSWORD: Your Gradescope password

Usage:
    python generate_ical.py
"""

import os
import sys
from pathlib import Path

from sync_gradescope import GradescopeClient
from ical_generator import save_ics_file


def main():
    """Main function to generate iCal file from Gradescope assignments."""
    # Get Gradescope credentials from environment
    email = os.environ.get("GRADESCOPE_EMAIL")
    password = os.environ.get("GRADESCOPE_PASSWORD")

    if not email or not password:
        print("ERROR: Missing Gradescope credentials.")
        print("Set GRADESCOPE_EMAIL and GRADESCOPE_PASSWORD environment variables.")
        sys.exit(1)

    try:
        # Connect to Gradescope
        print(f"Logging into Gradescope as {email}...")
        gs_client = GradescopeClient(email, password)
        print("Logged in successfully!")

        # Get courses
        print("Fetching courses...")
        courses = gs_client.get_courses()
        print(f"Found {len(courses)} courses")

        # Collect all assignments
        all_assignments = []

        for course in courses:
            print(f"\nProcessing: {course['short_name']} - {course['full_name']}")

            assignments = gs_client.get_assignments(course['id'])
            print(f"  Found {len(assignments)} assignments")

            for assignment in assignments:
                if not assignment['due_date']:
                    print(f"    Skipping '{assignment['name']}' - no due date")
                    continue

                # Format assignment for iCal generator
                all_assignments.append({
                    'name': assignment['name'],
                    'course_name': course['short_name'],
                    'course_full_name': course['full_name'],
                    'course_id': course['id'],
                    'assignment_id': assignment['id'],
                    'due_date': assignment['due_date'],
                    'url': assignment['url']
                })

        # Create output directory
        output_dir = Path(__file__).parent / "docs"
        output_dir.mkdir(exist_ok=True)

        output_path = output_dir / "gradescope.ics"

        # Generate iCal file
        print(f"\nGenerating iCal file...")
        event_count = save_ics_file(all_assignments, str(output_path))

        print(f"\n{'='*50}")
        print("iCal generation completed!")
        print(f"  Events created: {event_count}")
        print(f"  Output file: {output_path}")
        print(f"{'='*50}")

    except Exception as e:
        print(f"ERROR: iCal generation failed - {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
