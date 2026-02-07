# Gradescope Calendar Sync

Automatically sync your Gradescope assignment deadlines to any calendar app.

## Quick Start (5 minutes)

### 1. Use this template

Click **Use this template** and create your own repository.

### 2. Add your Gradescope credentials

Go to your repository's **Settings > Secrets and variables > Actions** and add:

| Secret Name | Value |
|-------------|-------|
| `GRADESCOPE_EMAIL` | Your Gradescope email |
| `GRADESCOPE_PASSWORD` | Your Gradescope password |

### 3. Enable GitHub Pages

1. Go to **Settings > Pages**
2. Under "Source", select **Deploy from a branch**
3. Select the `main` branch and `/ (root)` folder
4. Click **Save**

### 4. Run the workflow

1. Go to **Actions** tab
2. Click **Generate iCal Feed**
3. Click **Run workflow**

### 5. Subscribe to your calendar

After the workflow completes, your calendar feed will be available at:

```
https://YOUR-USERNAME.github.io/YOUR-REPO/gradescope.ics
```

**Subscribe in your calendar app:**

- **Google Calendar**: Settings > Add calendar > From URL
- **Apple Calendar**: File > New Calendar Subscription
- **Outlook**: Add calendar > Subscribe from web

That's it! Your calendar will automatically update twice daily.

---

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Gradescope │ --> │   GitHub    │ --> │  Your       │
│  (scrapes)  │     │   Actions   │     │  Calendar   │
└─────────────┘     └─────────────┘     └─────────────┘
                    Runs 2x daily        Subscribes to
                    Generates .ics       the feed URL
```

1. GitHub Actions runs twice daily (8 AM and 8 PM Pacific)
2. The workflow logs into Gradescope and fetches all assignments
3. It generates an iCal file and commits it to your repo
4. Your calendar app refreshes from the URL automatically

## Features

- **Auto-updates**: Syncs twice daily automatically
- **Works everywhere**: Any calendar app that supports iCal subscriptions
- **No duplicates**: Uses stable event IDs for clean updates
- **Zero maintenance**: Runs on GitHub's free tier

## Customization

### Change sync schedule

Edit `.github/workflows/generate-ical.yml`:

```yaml
schedule:
  - cron: '0 4,16 * * *'  # Default: 8 AM and 8 PM Pacific
  # - cron: '0 */6 * * *'  # Every 6 hours
  # - cron: '0 12 * * *'   # Once daily at noon UTC
```

### Manual sync

Go to **Actions > Generate iCal Feed > Run workflow** anytime.

## Advanced: Google Calendar OAuth Sync

Want real-time sync with custom reminders? See [ADVANCED_SETUP.md](ADVANCED_SETUP.md) for OAuth-based Google Calendar integration.

| Method | Setup Time | Features |
|--------|------------|----------|
| **iCal** (this guide) | 5 min | Subscribe URL, auto-refresh, works with any calendar |
| **OAuth** ([advanced](ADVANCED_SETUP.md)) | 30 min | Direct Google Calendar sync, custom reminders, faster updates |

## Troubleshooting

### Calendar not updating

- Trigger a manual workflow run from the Actions tab
- Check that GitHub Pages is enabled and the URL is correct
- Some calendar apps cache aggressively; try removing and re-adding the subscription

### Workflow failing

- Verify your `GRADESCOPE_EMAIL` and `GRADESCOPE_PASSWORD` secrets are correct
- Check the workflow logs in the Actions tab for error details

### Missing assignments

- The sync only includes assignments with due dates
- Assignments from courses where you're not enrolled won't appear

## Privacy, Ownership, and Security

- All workflows run in your repository and count against **your** GitHub Actions quota
- Your Gradescope credentials are stored as encrypted GitHub Secrets in your repository
- You control your own Pages URL and generated calendar feed

- Credentials are never logged or exposed in workflow runs
- Consider using a **private repository** if you don't want your assignment schedule to be public
- The generated `.ics` file contains assignment names and due dates

## Local Development

Test the iCal generation locally:

```bash
pip install -r requirements.txt
export GRADESCOPE_EMAIL="your-email@example.com"
export GRADESCOPE_PASSWORD="your-password"
python generate_ical.py
```

The output will be saved to `docs/gradescope.ics`.
