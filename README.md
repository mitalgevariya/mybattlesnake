# My Battlesnake

A simple Battlesnake written in Python using Flask.

## What This Snake Does

Currently, this snake:
- Avoids walls (stays within bounds)
- Avoids hitting itself
- Chooses random safe moves

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

## Local Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the server:
```bash
python main.py
```

Your server will start on `http://localhost:8000`

3. Test the server:
```bash
curl http://localhost:8000
```

You should see JSON output with your snake's metadata.

## Deployment Options

### Option 1: Google Cloud Platform (GCP App Engine)

**Prerequisites:**
- Google Cloud account
- gcloud CLI installed ([Install guide](https://cloud.google.com/sdk/docs/install))

**Steps:**

1. Initialize gcloud (if not already done):
```bash
gcloud init
```

2. Create a new GCP project or select existing one:
```bash
gcloud projects create battlesnake-PROJECT_ID --name="Battlesnake"
gcloud config set project battlesnake-PROJECT_ID
```

3. Enable App Engine:
```bash
gcloud app create --region=us-central
```

4. Deploy your snake:
```bash
gcloud app deploy
```

5. View your snake:
```bash
gcloud app browse
```

Your Battlesnake URL will be: `https://battlesnake-PROJECT_ID.uc.r.appspot.com`

**Update your snake:**
```bash
gcloud app deploy
```

**View logs:**
```bash
gcloud app logs tail -s default
```

### Option 2: Replit (Easiest - Recommended!)

**Step 1: Create a Replit Account**
- Go to [Replit](https://replit.com) and sign up/log in

**Step 2: Import Your Project**
1. Click "Create Repl"
2. Choose "Import from GitHub" OR "Upload files"
3. If uploading files, drag and drop all files from this project

**Step 3: Configure and Run**
1. Replit will auto-detect Python and install dependencies from requirements.txt
2. Click the big "Run" button at the top
3. Wait for the server to start (you'll see "Running on http://0.0.0.0:8000")
4. Your Repl URL will be shown at the top (format: https://your-repl-name.your-username.repl.co)

**Step 4: Keep Your Snake Alive**
- Free Repls sleep after inactivity
- Consider upgrading to Replit Hacker plan for always-on hosting
- Or use a free uptime monitor service like [UptimeRobot](https://uptimerobot.com)

**Step 5: Get Your Snake URL**
- Copy your Repl URL from the webview panel
- This is what you'll register at play.battlesnake.com

### Option 3: Render, Railway, or Heroku
Follow their Python deployment guides and use `gunicorn` as the web server:
```bash
gunicorn main:app
```

## Register Your Snake

1. Go to [play.battlesnake.com](https://play.battlesnake.com)
2. Sign in or create an account
3. Click "Create a Battlesnake"
4. Enter your server URL
5. Give your snake a name
6. Click "Save"

## Customize Your Snake

Edit the `/` route in `main.py` to change:
- `color`: Hex color code (e.g., "#FF0000" for red)
- `head`: Head style (default, beluga, bendr, dead, evil, fang, pixel, safe, sand-worm, shades, silly, smile, tongue)
- `tail`: Tail style (default, block-bum, bolt, curled, fat-rattle, freckled, hook, pixel, round-bum, sharp, skinny, small-rattle)
- `author`: Your username

## Next Steps

Improve your snake by:
1. Moving toward food when hungry
2. Avoiding other snakes
3. Controlling the center of the board
4. Looking ahead multiple moves

## Resources

- [Battlesnake Documentation](https://docs.battlesnake.com)
- [API Reference](https://docs.battlesnake.com/api)
- [Game Rules](https://docs.battlesnake.com/rules)
- [Discord Community](https://play.battlesnake.com/discord)

## File Structure

```
battlesnake/
├── main.py              # Main server code
├── requirements.txt     # Python dependencies
├── app.yaml            # GCP App Engine configuration
├── .replit             # Replit configuration
├── replit.nix          # Replit environment setup
├── .gitignore          # Git ignore patterns
└── README.md           # This file
```
