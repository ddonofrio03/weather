#!/usr/bin/env python3
"""
Daily Murrells Inlet weather email.
Pulls a 7-day WeatherMesh-5c point forecast from WindBorne and emails an
inbox-friendly summary via Gmail SMTP. Standard library only.

Required env:
  WB_API_KEY           WindBorne API key
  GMAIL_USER           sending Gmail address (e.g. lbidonofrio@gmail.com)
  GMAIL_APP_PASSWORD   16-char Google app password for GMAIL_USER
  MAIL_TO              comma-separated recipients

Optional env:
  PLACE  (default "Murrells Inlet, SC")
  LAT    (default "33.55")
  LON    (default "-79.04")
  MODEL  (default "wm-5c")
  TZ_NAME (default "America/New_York")
  SEND_HOUR (default "6")  local hour at which the daily send is allowed
  FORCE_SEND ("1" to ignore the hour guard, used for manual runs)
  DRY_RUN ("1" to build email.html and skip sending)
"""
import os, sys, json, math, ssl, smtplib, time, urllib.request, urllib.error
from datetime import datetime
from email.mime.text import MIMEText
from email.utils import formataddr
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

KEY     = os.environ["WB_API_KEY"]
PLACE   = os.environ.get("PLACE", "Murrells Inlet, SC")
LAT     = os.environ.get("LAT", "33.55")
LON     = os.environ.get("LON", "-79.04")
MODEL   = os.environ.get("MODEL", "wm-5c")
TZ_NAME = os.environ.get("TZ_NAME", "America/New_York")
SEND_HOUR = int(os.environ.get("SEND_HOUR", "6"))
FORCE   = os.environ.get("FORCE_SEND") == "1"
DRY     = os.environ.get("DRY_RUN") == "1"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def local_tz():
    if ZoneInfo:
        try:
            return ZoneInfo(TZ_NAME)
        except Exception:
            pass
    from datetime import timezone, timedelta
    return timezone(timedelta(hours=-4))  # EDT fallback

TZ = local_tz()

def fetch():
    url = (f"https://api.windbornesystems.com/forecasts/v1/{MODEL}/point_forecast.json"
           f"?coordinates={LAT},{LON}&min_forecast_hour=0&max_forecast_hour=168")
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {KEY}", "User-Agent": UA, "Accept": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(65); continue
            raise SystemExit(f"WindBorne error {e.code}: {e.read().decode()[:300]}")
    raise SystemExit("WindBorne request failed after retry")

def cf(c): return c * 9 / 5 + 32
def rh(t, td):
    a, b = 17.625, 243.04
    return max(0, min(100, 100 * math.exp((a*td/(b+td)) - (a*t/(b+t)))))
DIRS = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
def wind(u, v):
    spd = math.sqrt(u*u + v*v) * 2.23694
    frm = math.degrees(math.atan2(-u, -v)) % 360
    return round(spd, 1), DIRS[int((frm + 11.25)//22.5) % 16]

def process(data):
    fc = data["forecasts"][0]
    hourly = []
    for p in fc:
        t = datetime.fromisoformat(p["time"].replace("Z", "+00:00")).astimezone(TZ)
        spd, comp = wind(p["wind_u_10m"], p["wind_v_10m"])
        hourly.append({"date": t.strftime("%Y-%m-%d"), "dow": t.strftime("%a"),
                       "dt": t, "tempF": cf(p["temperature_2m"]),
                       "rh": rh(p["temperature_2m"], p["dewpoint_2m"]),
                       "precip_in": p["precipitation"]/25.4,
                       "wind": spd, "wdir": comp})
    days = {}
    for h in hourly:
        days.setdefault(h["date"], []).append(h)
    daily = []
    for date, hs in days.items():
        temps = [x["tempF"] for x in hs]
        daily.append({"date": date, "dow": hs[0]["dow"], "dt": hs[0]["dt"],
                      "hi": round(max(temps)), "lo": round(min(temps)),
                      "precip": round(sum(x["precip_in"] for x in hs), 2),
                      "wethrs": sum(1 for x in hs if x["precip_in"] >= 0.01),
                      "wind": round(max(x["wind"] for x in hs)),
                      "rh": round(sum(x["rh"] for x in hs)/len(hs)),
                      "full": len(hs) >= 24})
    return hourly, daily

def build_html(daily, hourly, init_iso):
    init = datetime.fromisoformat(init_iso.replace("Z", "+00:00")).astimezone(TZ)
    now = datetime.now(TZ)
    floor = now.replace(minute=0, second=0, microsecond=0)
    today = [h for h in hourly if h["dt"] >= floor and h["dt"].date() == now.date()]
    if len(today) < 4:                         # late in the day: show next 12 hrs
        today = [h for h in hourly if h["dt"] >= floor][:12]
    today = today[:18]
    wk_hi = max(d["hi"] for d in daily); wk_lo = min(d["lo"] for d in daily)
    total = round(sum(d["precip"] for d in daily), 2)
    rows = []
    for d in daily:
        wet = d["precip"] >= 0.05
        bg = "#eef4f5" if wet else "#ffffff"
        rain = f'{d["precip"]:.2f}&Prime; &middot; {d["wethrs"]}h' if wet else "&mdash;"
        rcol = "#2f6f82" if wet else "#9aa0a6"
        part = ' <span style="font-size:11px;color:#9aa0a6;">(partial)</span>' if not d["full"] else ""
        rows.append(f'''<tr style="background:{bg};">
  <td style="padding:10px 12px;border-bottom:1px solid #e7e3da;font-weight:600;color:#16263d;">{d['dow']} <span style="color:#9aa0a6;font-weight:400;">{d['dt'].strftime('%b %-d')}</span>{part}</td>
  <td style="padding:10px 12px;border-bottom:1px solid #e7e3da;text-align:right;"><b style="color:#c9742a;">{d['hi']}&deg;</b> <span style="color:#9aa0a6;">/ {d['lo']}&deg;</span></td>
  <td style="padding:10px 12px;border-bottom:1px solid #e7e3da;text-align:right;color:{rcol};font-weight:600;">{rain}</td>
  <td style="padding:10px 12px;border-bottom:1px solid #e7e3da;text-align:right;color:#3b4a5e;">{d['wind']} mph</td>
  <td style="padding:10px 12px;border-bottom:1px solid #e7e3da;text-align:right;color:#3b4a5e;">{d['rh']}%</td>
</tr>''')
    rows = "\n".join(rows)

    # ---- today's hourly block ----
    hrows = []
    for i, h in enumerate(today):
        bg = "#eef4f5" if h["precip_in"] >= 0.01 else ("#ffffff" if i % 2 == 0 else "#faf7f0")
        rain = f'{h["precip_in"]:.2f}&Prime;' if h["precip_in"] >= 0.005 else "&mdash;"
        rcol = "#2f6f82" if h["precip_in"] >= 0.005 else "#c4bdae"
        hrows.append(f'''<tr style="background:{bg};">
  <td style="padding:7px 12px;border-bottom:1px solid #eee7da;color:#3b4a5e;">{h['dt'].strftime('%-I %p')}</td>
  <td style="padding:7px 12px;border-bottom:1px solid #eee7da;text-align:right;font-weight:600;color:#c9742a;">{round(h['tempF'])}&deg;</td>
  <td style="padding:7px 12px;border-bottom:1px solid #eee7da;text-align:right;color:{rcol};">{rain}</td>
  <td style="padding:7px 12px;border-bottom:1px solid #eee7da;text-align:right;color:#3b4a5e;">{round(h['wind'])} mph <span style="color:#9aa0a6;">{h['wdir']}</span></td>
  <td style="padding:7px 12px;border-bottom:1px solid #eee7da;text-align:right;color:#3b4a5e;">{round(h['rh'])}%</td>
</tr>''')
    hrows = "\n".join(hrows)
    today_label = today[0]["dt"].strftime("%A, %B %-d") if today else now.strftime("%A, %B %-d")
    hourly_section = f'''
  <tr><td style="padding:4px 22px 6px;">
    <div style="font-size:18px;font-weight:700;color:#16263d;padding:0 4px;">Today, hour by hour</div>
    <div style="font-size:12px;color:#9aa0a6;padding:2px 4px 10px;">{today_label}</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px;">
      <tr style="background:#1c2d44;">
        <th style="padding:8px 12px;text-align:left;color:#f4efe6;font-size:11px;letter-spacing:.06em;text-transform:uppercase;">Time</th>
        <th style="padding:8px 12px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.06em;text-transform:uppercase;">Temp</th>
        <th style="padding:8px 12px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.06em;text-transform:uppercase;">Rain</th>
        <th style="padding:8px 12px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.06em;text-transform:uppercase;">Wind</th>
        <th style="padding:8px 12px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.06em;text-transform:uppercase;">Hum</th>
      </tr>
      {hrows}
    </table>
  </td></tr>'''

    return f'''<!doctype html><html><body style="margin:0;background:#f4efe6;padding:24px 0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4efe6;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#fbf8f2;border:1px solid #e7e3da;border-radius:14px;overflow:hidden;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <tr><td style="background:#16263d;padding:22px 26px;">
    <div style="color:#9fc3cf;font-size:11px;letter-spacing:.18em;text-transform:uppercase;">7-Day Forecast &middot; WeatherMesh-5c</div>
    <div style="color:#fbf8f2;font-size:26px;font-weight:700;margin-top:6px;">{PLACE}</div>
    <div style="color:#c7cdd6;font-size:12px;margin-top:6px;">Model run {init.strftime('%A, %B %-d at %-I:%M %p')} ET &middot; {LAT}&deg;, {LON}&deg;</div>
  </td></tr>
  <tr><td style="padding:18px 26px 4px;">
    <table role="presentation" width="100%"><tr>
      <td style="text-align:center;"><div style="font-size:26px;font-weight:700;color:#16263d;">{wk_hi}&deg;</div><div style="font-size:11px;color:#9aa0a6;text-transform:uppercase;letter-spacing:.1em;">Week high</div></td>
      <td style="text-align:center;"><div style="font-size:26px;font-weight:700;color:#16263d;">{wk_lo}&deg;</div><div style="font-size:11px;color:#9aa0a6;text-transform:uppercase;letter-spacing:.1em;">Week low</div></td>
      <td style="text-align:center;"><div style="font-size:26px;font-weight:700;color:#16263d;">{total:.2f}&Prime;</div><div style="font-size:11px;color:#9aa0a6;text-transform:uppercase;letter-spacing:.1em;">Total rain</div></td>
    </tr></table>
  </td></tr>
  {hourly_section}
  <tr><td style="padding:6px 22px 22px;">
    <div style="font-size:18px;font-weight:700;color:#16263d;padding:0 4px 10px;">7-day outlook</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:14px;">
      <tr style="background:#1c2d44;">
        <th style="padding:9px 12px;text-align:left;color:#f4efe6;font-size:11px;letter-spacing:.06em;text-transform:uppercase;">Day</th>
        <th style="padding:9px 12px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.06em;text-transform:uppercase;">Hi / Lo</th>
        <th style="padding:9px 12px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.06em;text-transform:uppercase;">Rain</th>
        <th style="padding:9px 12px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.06em;text-transform:uppercase;">Wind</th>
        <th style="padding:9px 12px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.06em;text-transform:uppercase;">Hum</th>
      </tr>
      {rows}
    </table>
  </td></tr>
  <tr><td style="padding:0 26px 22px;color:#9aa0a6;font-size:11px;line-height:1.6;">
    Source: WindBorne Systems WeatherMesh-5c point forecast. Temperatures in &deg;F, rain in inches, wind in mph (max gust-level 10m). Rolling 168-hour window, so the first and last days are partial. Generated automatically.
  </td></tr>
</table>
</td></tr></table></body></html>'''

def main():
    now_local = datetime.now(TZ)
    if not (DRY or FORCE) and now_local.hour != SEND_HOUR:
        print(f"Local hour {now_local.hour} != SEND_HOUR {SEND_HOUR}; skipping.")
        return
    data = fetch()
    hourly, daily = process(data)
    html = build_html(daily, hourly, data["initialization_time"])
    subj = f"{PLACE} weather \u2014 {now_local.strftime('%a %b %-d')}"
    if DRY:
        open("email.html", "w").write(html)
        print("DRY_RUN wrote email.html;", len(daily), "days")
        return
    user = os.environ["GMAIL_USER"]
    pw   = os.environ["GMAIL_APP_PASSWORD"]
    to   = [a.strip() for a in os.environ["MAIL_TO"].split(",") if a.strip()]
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subj
    msg["From"] = formataddr(("Murrells Inlet Forecast", user))
    msg["To"] = ", ".join(to)
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(user, pw)
        s.sendmail(user, to, msg.as_string())
    print(f"Sent to {to}")

if __name__ == "__main__":
    main()
