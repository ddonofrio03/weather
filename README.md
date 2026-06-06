# weather

Emails a Murrells Inlet forecast every morning at 6am ET to a fixed list of
recipients: today hour-by-hour plus a 7-day outlook, each with sky conditions.
Runs as a scheduled GitHub Action. No server, no laptop required.

- Data: Open-Meteo forecast API (hourly + daily, 7 days). No API key required.
- Send: Gmail SMTP from `lbidonofrio@gmail.com`
- Recipients: `ddonofrio@thecaseygroup.us`, `stephdonofrio@gmail.com`
- Schedule: 6am America/New_York (see the workflow file for the exact cron)

## One-time setup

### Repository secret (only one needed)
Repo -> **Settings -> Secrets and variables -> Actions**

| Secret | Value |
| --- | --- |
| `GMAIL_APP_PASSWORD` | a Google **app password** for `lbidonofrio@gmail.com` |

Recipients, the sending address, and the location are plain settings in
`.github/workflows/daily-forecast.yml`, not secrets. Edit them there.

There is **no weather API key**. Open-Meteo is free and keyless for this volume.
Any leftover `WB_API_KEY` secret or env line is ignored and can be deleted.

### Gmail app password
A normal Gmail password will not work for SMTP. You need a 16-character app password.
1. On `lbidonofrio@gmail.com`, turn on **2-Step Verification** (myaccount.google.com -> Security).
2. Go to **myaccount.google.com/apppasswords**, create one named "weather",
   paste the 16 characters into the `GMAIL_APP_PASSWORD` secret.

### Test it
Repo -> **Actions -> Daily Weather Email -> Run workflow**. A manual run always
sends regardless of time of day. Check both inboxes.

## Notes
- **No expiry.** Unlike the previous WindBorne trial key, Open-Meteo needs no key
  and will not lapse.
- **Attribution.** The email footer credits Open-Meteo (CC BY 4.0), as their
  license requires. Keep that line.
- **Schedule drift.** GitHub scheduled runs are best-effort and can start a few
  minutes late under load.
- **Change recipients or location.** Edit `MAIL_TO`, `LAT`, `LON`, `PLACE` in the
  workflow file.

## Files
- `forecast_email.py` - fetch from Open-Meteo, format, send (standard library only)
- `.github/workflows/daily-forecast.yml` - the schedule
