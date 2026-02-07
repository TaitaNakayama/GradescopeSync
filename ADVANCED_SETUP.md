# Advanced Setup: Google Calendar OAuth Sync

This guide is for users who want **real-time two-way sync** with Google Calendar via OAuth. This provides more features than the iCal subscription but requires more setup.

> **Most users should use the simpler iCal subscription method.** See the main [README](README.md) for instructions.

## Why Use OAuth Sync?

| Feature | iCal Subscription | OAuth Sync |
|---------|-------------------|------------|
| Setup complexity | Easy (2 secrets) | Complex (3 secrets + Google Cloud) |
| Calendar updates | Every few hours (depends on calendar app) | Immediate on workflow run |
| Event reminders | Set by your calendar app | Custom (1 hour + 24 hours before) |
| Duplicate handling | Via stable UIDs | Via event search |
| Works offline | No | Events persist in Google Calendar |

## Prerequisites

- A GitHub account with your own repository created from this template
- A Google account
- Access to [Google Cloud Console](https://console.cloud.google.com/) (your own project)

## Setup Instructions

### 1. Set Up Google Calendar API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Search for "Google Calendar API" and enable it
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > OAuth client ID**
6. If prompted, configure the OAuth consent screen:
   - Choose "External" user type
   - Fill in the required fields (app name, email)
   - Add your email to test users
7. Select **Desktop application** as the application type
8. Download the JSON file and save it as `credentials.json` in the repo directory

### 2. Generate Google OAuth Token

Run the setup script locally (one-time only):

```bash
pip install -r requirements.txt
python setup_google_auth.py
```

This will open a browser for Google authentication and create `token.json`.

### 3. Encode Token for GitHub

On macOS:
```bash
base64 -i token.json | pbcopy
```

On Linux:
```bash
base64 -w 0 token.json
```

Copy the output for the next step.

### 4. Configure GitHub Secrets

Go to your repository's **Settings > Secrets and variables > Actions** and add:

| Secret Name | Value |
|-------------|-------|
| `GRADESCOPE_EMAIL` | Your Gradescope email address |
| `GRADESCOPE_PASSWORD` | Your Gradescope password |
| `GOOGLE_TOKEN` | The base64-encoded token from step 3 |

### 5. Enable the OAuth Workflow

The OAuth sync workflow is in `.github/workflows/sync.yml`. It runs on the same schedule as the iCal generator.

To trigger a manual sync:
1. Go to your repository on GitHub
2. Click **Actions** tab
3. Click **Sync Gradescope to Google Calendar**
4. Click **Run workflow**

### 6. Verify It Works

1. Trigger the workflow manually
2. Check the Actions log for success
3. Open Google Calendar and verify assignments appear

## Configuration Options

### Target Calendar

By default, the sync targets a calendar named "Berkeley Calendar". To use a different calendar:

1. Create the calendar in Google Calendar (or use "primary" for your main calendar)
2. Add a secret `GOOGLE_CALENDAR_NAME` with the calendar name

### Sync Schedule

Modify the cron schedule in `.github/workflows/sync.yml`:

```yaml
schedule:
  - cron: '0 */2 * * *'  # Every 2 hours
  # - cron: '0 * * * *'  # Every hour
  # - cron: '0 8,12,18 * * *'  # At 8am, 12pm, and 6pm UTC
```

## Troubleshooting

### "No Google credentials found"
Run `python setup_google_auth.py` to generate the token.

### "Missing Gradescope credentials"
Make sure `GRADESCOPE_EMAIL` and `GRADESCOPE_PASSWORD` are set as GitHub Secrets.

### Token expired
Google OAuth tokens can expire. If syncs start failing:
1. Run `setup_google_auth.py` locally again
2. Re-encode and update the `GOOGLE_TOKEN` secret

### Events appearing in wrong calendar
Check that `GOOGLE_CALENDAR_NAME` matches your target calendar exactly, or remove it to use "Berkeley Calendar".

## Local Development

To run the OAuth sync locally:

```bash
export GRADESCOPE_EMAIL="your-email@example.com"
export GRADESCOPE_PASSWORD="your-password"
python sync_gradescope.py
```

Make sure `credentials.json` and `token.json` are in the same directory.

## Cleanup Utility

To remove Gradescope events from your primary calendar (useful if you previously synced to the wrong calendar):

```bash
python sync_gradescope.py --cleanup
```

## Security Notes

- `credentials.json` and `token.json` contain sensitive data - never commit them
- Use a private repository for additional security
- The `GOOGLE_TOKEN` secret is encrypted by GitHub
- Consider using a dedicated Google account for the integration
