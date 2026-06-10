name: Daily Weather Email

on:
  schedule:
    - cron: '15 10 * * *'   # ~6:15am ET during EDT; change to '15 11 * * *' for EST in November
  workflow_dispatch:

jobs:
  send:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Send forecast email
        env:
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          GMAIL_USER:         lbidonofrio@gmail.com
          MAIL_TO:            "ddonofrio@thecaseygroup.us,stephdonofrio@gmail.com"
          PLACE:              "Murrells Inlet, SC"
          LAT:                "33.55"
          LON:                "-79.04"
          FORCE_SEND:         "1"
        run: python forecast_email.py
