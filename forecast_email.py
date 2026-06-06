#!/usr/bin/env python3
"""
Daily Murrells Inlet weather email.
Pulls a 7-day forecast from Open-Meteo (no API key required) and emails an
inbox-friendly summary via Gmail SMTP. Standard library only.

Required env:
  GMAIL_USER           sending Gmail address (e.g. lbidonofrio@gmail.com)
  GMAIL_APP_PASSWORD   16-char Google app password for GMAIL_USER
  MAIL_TO              comma-separated recipients

Optional env:
  PLACE     (default "Murrells Inlet, SC")
  LAT       (default "33.55")
  LON       (default "-79.04")
  TZ_NAME   (default "America/New_York")
  SEND_HOUR (default "6")  local hour at which a scheduled send is allowed
  FORCE_SEND ("1" to ignore the hour guard, used for manual runs)
  DRY_RUN   ("1" to build email.html and skip sending)

Legacy WB_API_KEY / MODEL env vars are ignored if still present.
"""
import os, ssl, json, smtplib, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime
from email.mime.text import MIMEText
from email.utils import formataddr
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

PLACE   = os.environ.get("PLACE", "Murrells Inlet, SC")
LAT     = os.environ.get("LAT", "33.55")
LON     = os.environ.get("LON", "-79.04")
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

# WMO weather codes -> short, mobile-friendly labels
WMO = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy",
    45: "Fog", 48: "Fog",
    51: "Lt drizzle", 53: "Drizzle", 55: "Hvy drizzle", 56: "Frz drizzle", 57: "Frz drizzle",
    61: "Lt rain", 63: "Rain", 65: "Hvy rain", 66: "Frz rain", 67: "Frz rain",
    71: "Lt snow", 73: "Snow", 75: "Hvy snow", 77: "Snow",
    80: "Lt showers", 81: "Showers", 82: "Hvy showers", 85: "Snow showers", 86: "Snow showers",
    95: "T-storm", 96: "T-storm", 99: "T-storm",
}
def code_label(c):
    if c is None:
        return ""
    try:
        return WMO.get(int(c), "")
    except Exception:
        return ""

DIRS = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
def compass(deg):
    if deg is None:
        return ""
    return DIRS[int((float(deg) + 11.25)//22.5) % 16]

def fetch():
    params = {
        "latitude": LAT, "longitude": LON,
        "hourly": ("temperature_2m,relative_humidity_2m,precipitation,"
                   "precipitation_probability,weather_code,cloud_cover,"
                   "wind_speed_10m,wind_direction_10m"),
        "daily": ("weather_code,temperature_2m_max,temperature_2m_min,"
                  "precipitation_sum,precipitation_probability_max,"
                  "wind_speed_10m_max,wind_direction_10m_dominant"),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": TZ_NAME,
        "forecast_days": "7",
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 2:
                time.sleep(20); continue
            raise SystemExit(f"Open-Meteo error {e.code}: {e.read().decode()[:300]}")
        except urllib.error.URLError as e:
            if attempt < 2:
                time.sleep(10); continue
            raise SystemExit(f"Open-Meteo request failed: {e}")
    raise SystemExit("Open-Meteo request failed after retries")

def parse_local(s):
    # Open-Meteo returns local wall-clock time when a timezone is requested.
    return datetime.fromisoformat(s).replace(tzinfo=TZ)

def process(data):
    H = data["hourly"]
    hourly = []
    for i, ts in enumerate(H["time"]):
        temp = H["temperature_2m"][i]
        if temp is None:
            continue
        t = parse_local(ts)
        hourly.append({
            "date": t.strftime("%Y-%m-%d"), "dow": t.strftime("%a"), "dt": t,
            "tempF": temp,
            "rh": H["relative_humidity_2m"][i],
            "precip_in": H["precipitation"][i] or 0.0,
            "pop": H["precipitation_probability"][i],
            "code": H["weather_code"][i],
            "cloud": H["cloud_cover"][i],
            "wind": H["wind_speed_10m"][i] or 0.0,
            "wdir": compass(H["wind_direction_10m"][i]),
        })
    rh_by_day = {}
    for h in hourly:
        if h["rh"] is not None:
            rh_by_day.setdefault(h["date"], []).append(h["rh"])

    D = data["daily"]
    daily = []
    for i, ds in enumerate(D["time"]):
        dt = parse_local(ds + "T00:00")
        rhs = rh_by_day.get(ds, [])
        daily.append({
            "date": ds, "dow": dt.strftime("%a"), "dt": dt,
            "code": D["weather_code"][i],
            "hi": round(D["temperature_2m_max"][i]),
            "lo": round(D["temperature_2m_min"][i]),
            "precip": round(D["precipitation_sum"][i] or 0.0, 2),
            "pop": D["precipitation_probability_max"][i],
            "wind": round(D["wind_speed_10m_max"][i] or 0.0),
            "rh": round(sum(rhs)/len(rhs)) if rhs else None,
        })
    return hourly, daily

def build_html(daily, hourly):
    now = datetime.now(TZ)
    floor = now.replace(minute=0, second=0, microsecond=0)
    today = [h for h in hourly if h["dt"] >= floor and h["dt"].date() == now.date()]
    if len(today) < 4:                         # late in the day: show next 12 hrs
        today = [h for h in hourly if h["dt"] >= floor][:12]
    today = today[:18]
    wk_hi = max(d["hi"] for d in daily); wk_lo = min(d["lo"] for d in daily)
    total = round(sum(d["precip"] for d in daily), 2)

    # ---- 7-day rows ----
    rows = []
    for d in daily:
        wet = d["precip"] >= 0.05
        bg = "#eef4f5" if wet else "#ffffff"
        rain = f'{d["precip"]:.2f}&Prime;' if wet else '<span style="color:#c4bdae;">&middot;</span>'
        rcol = "#2f6f82" if wet else "#9aa0a6"
        sky = code_label(d["code"])
        hum = f'{d["rh"]}%' if d["rh"] is not None else ""
        rows.append(f'''<tr style="background:{bg};">
  <td style="padding:10px 12px;border-bottom:1px solid #e7e3da;font-weight:600;color:#16263d;white-space:nowrap;">{d['dow']} <span style="color:#9aa0a6;font-weight:400;">{d['dt'].strftime('%b %-d')}</span></td>
  <td style="padding:10px 12px;border-bottom:1px solid #e7e3da;color:#3b4a5e;">{sky}</td>
  <td style="padding:10px 12px;border-bottom:1px solid #e7e3da;text-align:right;white-space:nowrap;"><b style="color:#c9742a;">{d['hi']}&deg;</b> <span style="color:#9aa0a6;">/ {d['lo']}&deg;</span></td>
  <td style="padding:10px 12px;border-bottom:1px solid #e7e3da;text-align:right;color:{rcol};font-weight:600;">{rain}</td>
  <td style="padding:10px 12px;border-bottom:1px solid #e7e3da;text-align:right;color:#3b4a5e;white-space:nowrap;">{d['wind']} mph</td>
  <td style="padding:10px 12px;border-bottom:1px solid #e7e3da;text-align:right;color:#3b4a5e;">{hum}</td>
</tr>''')
    rows = "\n".join(rows)

    # ---- today's hourly block ----
    hrows = []
    for i, h in enumerate(today):
        p = h["precip_in"] or 0.0
        bg = "#eef4f5" if p >= 0.01 else ("#ffffff" if i % 2 == 0 else "#faf7f0")
        rain = f'{p:.2f}&Prime;' if p >= 0.005 else '<span style="color:#c4bdae;">&middot;</span>'
        rcol = "#2f6f82" if p >= 0.005 else "#c4bdae"
        sky = code_label(h["code"])
        hum = f'{round(h["rh"])}%' if h["rh"] is not None else ""
        hrows.append(f'''<tr style="background:{bg};">
  <td style="padding:7px 10px;border-bottom:1px solid #eee7da;color:#3b4a5e;white-space:nowrap;">{h['dt'].strftime('%-I %p')}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #eee7da;color:#3b4a5e;">{sky}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #eee7da;text-align:right;font-weight:600;color:#c9742a;">{round(h['tempF'])}&deg;</td>
  <td style="padding:7px 10px;border-bottom:1px solid #eee7da;text-align:right;color:{rcol};">{rain}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #eee7da;text-align:right;color:#3b4a5e;white-space:nowrap;">{round(h['wind'])} <span style="color:#9aa0a6;">{h['wdir']}</span></td>
  <td style="padding:7px 10px;border-bottom:1px solid #eee7da;text-align:right;color:#3b4a5e;">{hum}</td>
</tr>''')
    hrows = "\n".join(hrows)
    today_label = today[0]["dt"].strftime("%A, %B %-d") if today else now.strftime("%A, %B %-d")

    return f'''<!doctype html><html><body style="margin:0;background:#f4efe6;padding:24px 0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4efe6;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#fbf8f2;border:1px solid #e7e3da;border-radius:14px;overflow:hidden;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <tr><td style="background:#16263d;padding:22px 26px;">
    <div style="color:#9fc3cf;font-size:11px;letter-spacing:.18em;text-transform:uppercase;">7-Day Forecast &middot; Open-Meteo</div>
    <div style="color:#fbf8f2;font-size:26px;font-weight:700;margin-top:6px;">{PLACE}</div>
    <div style="color:#c7cdd6;font-size:12px;margin-top:6px;">Updated {now.strftime('%A, %B %-d at %-I:%M %p')} ET &middot; {LAT}&deg;, {LON}&deg;</div>
  </td></tr>
  <tr><td style="padding:18px 26px 4px;">
    <table role="presentation" width="100%"><tr>
      <td style="text-align:center;"><div style="font-size:26px;font-weight:700;color:#16263d;">{wk_hi}&deg;</div><div style="font-size:11px;color:#9aa0a6;text-transform:uppercase;letter-spacing:.1em;">Week high</div></td>
      <td style="text-align:center;"><div style="font-size:26px;font-weight:700;color:#16263d;">{wk_lo}&deg;</div><div style="font-size:11px;color:#9aa0a6;text-transform:uppercase;letter-spacing:.1em;">Week low</div></td>
      <td style="text-align:center;"><div style="font-size:26px;font-weight:700;color:#16263d;">{total:.2f}&Prime;</div><div style="font-size:11px;color:#9aa0a6;text-transform:uppercase;letter-spacing:.1em;">Total rain</div></td>
    </tr></table>
  </td></tr>
  <tr><td style="padding:4px 22px 6px;">
    <div style="font-size:18px;font-weight:700;color:#16263d;padding:0 4px;">Today, hour by hour</div>
    <div style="font-size:12px;color:#9aa0a6;padding:2px 4px 10px;">{today_label}</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px;">
      <tr style="background:#1c2d44;">
        <th style="padding:8px 10px;text-align:left;color:#f4efe6;font-size:11px;letter-spacing:.05em;text-transform:uppercase;">Time</th>
        <th style="padding:8px 10px;text-align:left;color:#f4efe6;font-size:11px;letter-spacing:.05em;text-transform:uppercase;">Sky</th>
        <th style="padding:8px 10px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.05em;text-transform:uppercase;">Temp</th>
        <th style="padding:8px 10px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.05em;text-transform:uppercase;">Rain</th>
        <th style="padding:8px 10px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.05em;text-transform:uppercase;">Wind</th>
        <th style="padding:8px 10px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.05em;text-transform:uppercase;">Hum</th>
      </tr>
      {hrows}
    </table>
  </td></tr>
  <tr><td style="padding:6px 22px 22px;">
    <div style="font-size:18px;font-weight:700;color:#16263d;padding:0 4px 10px;">7-day outlook</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:14px;">
      <tr style="background:#1c2d44;">
        <th style="padding:9px 12px;text-align:left;color:#f4efe6;font-size:11px;letter-spacing:.05em;text-transform:uppercase;">Day</th>
        <th style="padding:9px 12px;text-align:left;color:#f4efe6;font-size:11px;letter-spacing:.05em;text-transform:uppercase;">Sky</th>
        <th style="padding:9px 12px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.05em;text-transform:uppercase;">Hi / Lo</th>
        <th style="padding:9px 12px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.05em;text-transform:uppercase;">Rain</th>
        <th style="padding:9px 12px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.05em;text-transform:uppercase;">Wind</th>
        <th style="padding:9px 12px;text-align:right;color:#f4efe6;font-size:11px;letter-spacing:.05em;text-transform:uppercase;">Hum</th>
      </tr>
      {rows}
    </table>
  </td></tr>
  <tr><td style="padding:0 26px 22px;color:#9aa0a6;font-size:11px;line-height:1.6;">
    Temperatures in &deg;F, rain in inches, wind in mph. Sky shows each hour's condition and the dominant condition for each day. Generated automatically. Weather data by <a href="https://open-meteo.com" style="color:#2f6f82;text-decoration:none;">Open-Meteo.com</a> (CC BY 4.0).
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
    html = build_html(daily, hourly)
    subj = f"{PLACE} weather: {now_local.strftime('%a %b %-d')}"
    if DRY:
        open("email.html", "w").write(html)
        print("DRY_RUN wrote email.html;", len(daily), "days,", len(hourly), "hours")
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
