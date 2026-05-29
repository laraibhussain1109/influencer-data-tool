# Influencer Data Tool

A small Flask service that reads the `influencers.xlsx` workbook, calculates workbook-derived influencer metrics, and can fetch public Instagram profile-page data from the Instagram links in the sheet.

## What it can return

The workbook metrics endpoint returns:

- Top 5 locations (%)
- Female gender ratio (%)
- Male gender ratio (%)
- 18-24 age ratio (%)
- 25-34 age ratio (%)
- 35-45 age ratio (%)
- 45+ age ratio (%)
- Engagement rate per reach
- Followers summary
- Avg. video reach (last 10 video average)
- Avg. video views (last 10 video average)

The public Instagram fetcher can additionally try to fetch these public profile-page fields for each Instagram link in the workbook:

- Followers
- Following
- Post count
- Public full name and bio
- Public verified/private flags
- Avg. video views from recent public videos when Instagram exposes those values in the public profile HTML

If the workbook or public Instagram page does not contain the columns/data required for a metric, the API returns `null` for that metric and lists workbook-only missing metrics under `unavailable_fields` rather than inventing data.

> **Important:** this app does not log in to Instagram, bypass privacy controls, or fetch private audience Insights directly. It only reads the workbook and public Instagram profile pages. Private audience locations, gender split, age split, reach, and engagement insights still require a compliant Instagram Graph API or approved provider integration with account authorization.

## Public Instagram fetching limitations

Instagram can rate-limit, block, or change public page HTML at any time. The public fetcher is best-effort and reports per-profile errors in `public_instagram.errors` instead of pretending unavailable data exists.

For a production-grade solution, use an approved Instagram Graph API/provider integration and store returned fields in the workbook/API schema.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app influencer_service.app run --debug
```

Then open `http://127.0.0.1:5000/` and choose one of the buttons:

- **Calculate workbook details** reads the workbook only.
- **Fetch public Instagram data** reads the workbook and then attempts to fetch public data for the Instagram links in the sheet.

## API

### Health check

```bash
curl http://127.0.0.1:5000/health
```

### One-click details page

```bash
curl http://127.0.0.1:5000/
```

### Aggregate workbook metrics

```bash
curl http://127.0.0.1:5000/api/metrics
```

Use a different workbook path:

```bash
curl "http://127.0.0.1:5000/api/metrics?file=/path/to/influencers.xlsx"
```

### Combined details payload

```bash
curl http://127.0.0.1:5000/api/details
```

Include public Instagram fetching in the combined details payload:

```bash
curl "http://127.0.0.1:5000/api/details?include_public_instagram=1"
```

The combined endpoint returns `data_source`, `metrics`, `influencer_count`, normalized `influencers`, and optionally `public_instagram`. It accepts the same `file`, `name`, `city`, `state`, `gender`, and `language` query parameters as the other endpoints.

### Fetch public Instagram data

```bash
curl -X POST http://127.0.0.1:5000/api/fetch-public-instagram
```

Filter before fetching:

```bash
curl -X POST "http://127.0.0.1:5000/api/fetch-public-instagram?city=Visakhapatnam&gender=Female"
```

### Influencer records

```bash
curl http://127.0.0.1:5000/api/influencers
```

Filter by name, city, state, gender, or language:

```bash
curl "http://127.0.0.1:5000/api/influencers?city=Visakhapatnam&gender=Female"
```
