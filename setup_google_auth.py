#!/usr/bin/env python3
"""
Google Calendar OAuth Setup Script

Run this script ONCE locally to generate the token.json file needed for
Google Calendar access. After running, the token.json can be encoded and
stored as a GitHub Secret.

Prerequisites:
1. Go to https://console.cloud.google.com/
2. Create a project (or select existing)
3. Enable the Google Calendar API
4. Create OAuth 2.0 credentials (Desktop application type)
5. Download the credentials and save as 'credentials.json' in this directory

Usage:
    python setup_google_auth.py

After successful auth, this will create 'token.json' which you can then
encode for GitHub Secrets:
    base64 -i token.json | pbcopy  # macOS - copies to clipboard
    base64 token.json              # Linux - prints to stdout
"""

import os
import sys
from pathlib import Path

# Google Calendar API scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]

def main():
    script_dir = Path(__file__).parent
    credentials_path = script_dir / "credentials.json"
    token_path = script_dir / "token.json"

    if not credentials_path.exists():
        print("ERROR: credentials.json not found!")
        print("\nTo set up Google Calendar API credentials:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create or select a project")
        print("3. Enable the Google Calendar API")
        print("4. Go to APIs & Services > Credentials")
        print("5. Create OAuth 2.0 Client ID (Desktop application)")
        print("6. Download the JSON and save as 'credentials.json' here")
        sys.exit(1)

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Installing required packages...")
        os.system(f"{sys.executable} -m pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None

    # Check for existing token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("Opening browser for Google authentication...")
            print("(If browser doesn't open, check the terminal for a URL)")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the token
        token_path.write_text(creds.to_json())
        print(f"\nToken saved to: {token_path}")
    else:
        print("Existing token is still valid.")

    print("\n" + "=" * 60)
    print("SUCCESS! Google Calendar authentication complete.")
    print("=" * 60)
    print("\nNext steps for GitHub Actions:")
    print("1. Encode the token for GitHub Secrets:")
    print(f"   base64 -i {token_path} | pbcopy")
    print("\n2. Add these secrets to your GitHub repository:")
    print("   - GRADESCOPE_EMAIL: Your Gradescope email")
    print("   - GRADESCOPE_PASSWORD: Your Gradescope password")
    print("   - GOOGLE_TOKEN: The base64-encoded token (from step 1)")
    print("\n3. Push the repository to GitHub")
    print("4. The workflow will run every 2 hours automatically")

if __name__ == "__main__":
    main()
