# Rock Eternal Prayer Platform

## Run it in PyCharm

1. Open this folder in PyCharm.
2. Open `server.py`.
3. Right-click it and select **Run 'server'**.
4. Open `http://localhost:8000` in your browser.

The first time it runs, a secure local database is automatically created in `data/prayer_platform.db`.

## Leader Dashboard

Open `http://localhost:8000/admin.html`.

For local testing, the password is:

`change-me`

Before sharing this website publicly, change that password in PyCharm:

1. Select **Run** → **Edit Configurations**.
2. Select the `server` configuration.
3. Add this Environment Variable:

`ROCK_ETERNAL_ADMIN_PASSWORD=your-strong-private-password`

4. Run `server.py` again.

## What leaders can do

- Review every new request privately.
- Publish a request to the group Prayer Wall.
- Keep names anonymous or show them only with permission.
- Correct text, choose a category, archive, or permanently delete a request.
- Mark an active request as an answered prayer.

## Sharing with the Life Group

`localhost` works only on the computer running PyCharm. To send a link to phones and other computers, deploy this application to a Python hosting service with HTTPS and persistent storage. Do not use a static-only host such as Netlify Drop for this version.

Prayer requests can contain sensitive personal information. Keep the Leader Dashboard password private, use leader approval before publishing, and only publish requests with the person's permission.
