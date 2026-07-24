# Connect the Prayer Platform to Google Sheets

The website stores every prayer request in a Google Sheet. The website visitors never see your Google credentials.

## 1. Create the Google Sheet

1. Create a new blank Google Sheet in the Google account that owns the church data.
2. Name it something clear, such as **Rock Eternal Prayer Requests**.
3. Copy the **Spreadsheet ID** from its URL. It is the long text between `/d/` and `/edit`.

Example:

`https://docs.google.com/spreadsheets/d/THIS_IS_THE_SPREADSHEET_ID/edit`

The app automatically creates a tab named **Prayer Requests** and its columns on first launch.

## 2. Create secure Google credentials

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project, for example **Rock Eternal Prayer Platform**.
3. Open **APIs & Services** → **Library** → enable **Google Sheets API**.
4. Open **APIs & Services** → **Credentials** → **Create Credentials** → **Service account**.
5. Open the new service account and create a **JSON key**.
6. Download that file and rename it to `google-service-account.json`.
7. Put it in the same folder as `server.py`.

Never email, upload, or commit this file to GitHub. This project already excludes it with `.gitignore`.

## 3. Share the Sheet with the service account

1. Open `google-service-account.json` with PyCharm.
2. Copy the value beside `client_email`. It looks like an email address ending in `iam.gserviceaccount.com`.
3. In your Google Sheet, click **Share**.
4. Add that service-account email as an **Editor**.

This allows the website server, and only the server, to write requests to your sheet.

## 4. Install the Google libraries

In the PyCharm terminal, run:

```bash
pip install -r requirements.txt
```

## 5. Add your Sheet ID in PyCharm

1. In PyCharm, select **Run** → **Edit Configurations**.
2. Select the `server` configuration.
3. In **Environment variables**, add:

```text
GOOGLE_SHEET_ID=your-spreadsheet-id
ROCK_ETERNAL_ADMIN_PASSWORD=your-strong-private-leader-password
```

4. Click **Apply** then run `server.py`.

Open `http://localhost:8000`. Submit a test request, then check the Google Sheet. It will appear in the **Prayer Requests** tab with `pending` status until a leader publishes it.

## Security note

Use a strong leader password before public sharing. Keep the Google Sheet and the service-account key private because prayer requests can contain sensitive personal information.
