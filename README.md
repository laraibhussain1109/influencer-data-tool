# Influencer Data Tool

A small Flask service that reads the `influencers.xlsx` workbook in this repository and exposes influencer analytics over HTTP, plus a one-click browser page for calculating the requested insight summary from workbook data.

## What it returns

The main metrics endpoint returns:

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

If the workbook does not contain the columns required for a metric, the API returns `null` for that metric and lists it under `unavailable_fields` rather than inventing data.

> **Important:** this app does **not** call Instagram, scrape Instagram, or fetch private Instagram Insights directly. Private Instagram Insights such as audience age splits, audience locations, reach, and recent video views must come from a compliant Instagram export/API/provider feed in the workbook before the tool can calculate them.

## Getting live Instagram Insights

To truly fetch these fields from Instagram instead of reading them from the workbook, the app needs a separate integration that is not present in this repository today:

1. Use Instagram Graph API or an approved analytics/provider API.
2. Get Creator/Business account authorization from each influencer whose private insights are required.
3. Store the returned audience demographics, reach, video reach, and video view fields in the workbook columns that the analytics layer can detect.

The service intentionally does not include a scraper because arbitrary scraping of private Instagram Insights is not a reliable or compliant way to obtain these metrics.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app influencer_service.app run --debug
```

Then open `http://127.0.0.1:5000/` and click **Calculate workbook details**. You can keep the default workbook path or paste another `.xlsx` path into the input before calculating.

## API

### Health check

```bash
curl http://127.0.0.1:5000/health
```

### One-click details page

```bash
curl http://127.0.0.1:5000/
```

### Aggregate metrics

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

The combined endpoint powers the **Calculate workbook details** button and returns `data_source`, `metrics`, `influencer_count`, and normalized `influencers` in one response. `data_source.instagram_api_enabled` is `false` so consumers cannot mistake workbook calculations for live Instagram API results. It accepts the same `file`, `name`, `city`, `state`, `gender`, and `language` query parameters as the other endpoints.

### Influencer records

```bash
curl http://127.0.0.1:5000/api/influencers
```

Filter by name, city, state, gender, or language:

```bash
curl "http://127.0.0.1:5000/api/influencers?city=Visakhapatnam&gender=Female"
```
