# Cascades Ski Report

A weekly email, sent Thursday mornings while there's snow, with the status and conditions of every downhill
area, nordic area and backcountry zone in the Oregon Cascades (Crater Lake to the Columbia River), plus Mt Adams,
Mt St. Helens and Mt Rainier (Paradise / Muir Snowfield), plus the summits of Hood, Jefferson, Three Fingered
Jack, Washington, the three Sisters, Adams and St. Helens as backcountry objectives.

For each area it gives the current status and condition, and a projection for the weekend. Each value comes with
a confidence percentage. The email is a fixed template filled in from data the same way every week; nothing in
it is generated text.

On Mondays the same workflow checks the forecast through Sunday and sends a short storm alert only if a big
snowfall or rain-on-snow event is coming.

## Data

| Source | Used for |
|---|---|
| Resort lift / snow reports | Downhill status, base depth, new snow |
| Nordic grooming reports | Groomed status for nordic centers |
| NRCS SNOTEL (AWDB API) | Measured depth, new snow, rain and freeze-thaw since the last snow |
| NOAA NOHRSC snow analysis | Modeled depth at each area's exact point |
| NOAA National Blend of Models (NOMADS) | Snowfall, precipitation percentiles, snow level, temperature, wind through Sunday |
| NWS gridpoint forecast | Cross-check on NBM snowfall and snow level (forecaster-edited); disagreement lowers confidence |
| avalanche.org | NWAC / COAC danger ratings (quoted, never computed) |
| ODOT TripCheck, WSDOT, NPS | Road closures and chain requirements |
| OpenStreetMap (OSRM routing, Nominatim geocoding) | Drive time from `BASE_LOCATION`, normal road conditions |

## How scoring works

Everything is rule-based (`skireport/scoring.py`, `skireport/analysis.py`):

- **Condition (1-5):**
  - 5 Powder: 6 in or more of new snow in 3 days, no crust since.
  - 4 Packed powder: new snow in 7 days, or groomed in the last 48 hours.
  - 3 Packed / Spring corn.
  - 2 Crust / ice: rain, freeze-thaw or wind since the last snow.
  - 1 Too thin / No snow: below the skiable depth (12 in backcountry and nordic, 18 in downhill).
  - Between skiable and good coverage (30 / 24 / 36 in), the condition is capped at 2 (thin cover).
- **Status:**
  - Downhill uses the resort's own report.
  - Groomed nordic uses the grooming report.
  - Sno-parks and backcountry are inferred from snow depth and road status.
- **Weekend:** the current snowpack, projected forward with the NBM forecast.
- **Confidence:** a product of factors:
  - source type and data age
  - agreement between resort, SNOTEL and NOHRSC depths
  - distance and elevation gap to the nearest SNOTEL station
  - how far the depth is from the area's minimum
  - for the weekend: the NBM 10th-90th percentile precipitation spread, whether the snow level is within
    1,000 ft of the area, and NBM vs. NWS agreement on snowfall and snow level

Every run is archived in `history/`. `python -m skireport calibrate` compares each Thursday's weekend projection
with the following Monday's observation, and prints how often each stated confidence level was right. Adjust the
weights in `skireport/config.py` from that table.

## When it runs

- `ski-report.yml` runs Thursdays (report) and Mondays (storm check) at 14:00 UTC, **October through June only**.
- The first step is a snow gate. It continues only if some area or nearby SNOTEL station has more than 12 in of
  snow. Permanent snow (Muir Snowfield and the summits) doesn't count. No snow means no email.
- `keepalive.yml` runs on the 1st of each month. It pushes an empty commit only if the repo has been quiet for
  30 days, because GitHub disables scheduled workflows in public repos after 60 days without activity. It
  fetches nothing and sends nothing.

## Setup

1. Push this repo to GitHub (public is fine; nothing personal is in the code).
2. On the Gmail account that will send the report, turn on 2-Step Verification and create an App Password
   (Google Account > Security > App passwords).
3. In the repo, go to Settings > Secrets and variables > Actions > New repository secret, and add:

   | Secret | Value |
   |---|---|
   | `SMTP_USER` | the Gmail address that sends |
   | `SMTP_APP_PASSWORD` | the app password |
   | `REPORT_TO` | where the report goes (comma-separated for more than one) |
   | `BASE_LOCATION` | optional: where you drive from, as `lat,lon` or a street address. Adds a drive time to every area. |

4. Test it: Actions > ski-report > Run workflow, with "build without sending" checked. The rendered email is
   attached to the run as an artifact. Run it again unchecked to send a real one.

The recipient address only lives in the `REPORT_TO` secret. GitHub masks secrets in the public run logs.

## Local use

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m skireport thursday --dry-run --out out/email.html
.venv/bin/python -m unittest discover -s tests -t .
```

## Adding or changing areas

Areas live in `skireport/areas.yaml`, grouped by zone, with:
- coordinates and elevation in feet
- kind: `downhill`, `nordic` or `backcountry`
- webcam links for the zone

Resort and grooming adapters are keyed by area id in `skireport/sources/resorts.py` and
`skireport/sources/nordic.py`.
