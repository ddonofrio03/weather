# weather

Emails a 7-day Murrells Inlet forecast every morning at 6am ET to a fixed list
of recipients. Runs as a scheduled GitHub Action. No server, no laptop required.

- Data: WindBorne WeatherMesh-5c point forecast (hourly, 168 hours)
- Send: Gmail SMTP from `lbidonofrio@gmail.com`
- Recipients: `ddonofrio@thecaseygroup.us`, `stephdonofrio@gmail.com`
- Schedule: 6am America/New_York, daylight-saving-proof (see workflow comments)

## One-time setup

### 1. Add the two repository secrets
Repo -> **Settings -> Secrets and variables -> Actions -> New repository secret**

| Secret | Value |
| --- | --- |
| `WB_API_KEY` | your WindBorne API key |
| `GMAIL_APP_PASSWORD` | a Google **app password** for `lbidonofrio@gmail.com` (see below) |

Recipients, the sending address, and the location are plain settings in
`.github/workflows/daily-forecast.yml`, not secrets. Edit them there.

### 2. Create the Gmail app password
A normal Gmail password will not work for SMTP. You need a 16-character app password.

1. On `lbidonofrio@gmail.com`, turn on **2-Step Verification**
   (myaccount.google.com -> Security). App passwords require it.
2. Go to **myaccount.google.com/apppasswords**, create one named "weather",
   copy the 16 characters, and paste it into the `GMAIL_APP_PASSWORD` secret.

### 3. Test it
Repo -> **Actions -> Daily Weather Email -> Run workflow**. A manual run always
sends regardless of the time of day. Check both inboxes.

## Notes
- **Trial key expires.** A WindBorne free-trial key lasts about two weeks / 2,000
  requests. When it lapses the Action will start failing. Swap a fresh or
  commercial key into the `WB_API_KEY` secret to resume; no code change needed.
- **Schedule drift.** GitHub scheduled runs are best-effort and can start a few
  minutes late under load.
- **Change recipients or location.** Edit the `MAIL_TO`, `LAT`, `LON`, and
  `PLACE` values in the workflow file.

## Files
- `forecast_email.py` - fetch, format, send (standard library only)
- `.github/workflows/daily-forecast.yml` - the schedule
