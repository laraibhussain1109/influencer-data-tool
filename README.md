# Influencer Data Tool

A small Flask service that reads the `influencers.xlsx` workbook in this repository and exposes influencer analytics over HTTP, plus a one-click browser page for fetching the requested insight summary.

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

If the workbook does not contain the columns required for a metric, the API returns `null` for that metric and lists it under `unavailable_fields` rather than inventing data. Private Instagram Insights such as audience age splits, audience locations, reach, and recent video views must come from a compliant Instagram export/API/provider feed in the workbook before the tool can calculate them.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app influencer_service.app run --debug
```

Then open `http://127.0.0.1:5000/` and click **Fetch details**. You can keep the default workbook path or paste another `.xlsx` path into the input before fetching.

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

The combined endpoint powers the **Fetch details** button and returns `metrics`, `influencer_count`, and normalized `influencers` in one response. It accepts the same `file`, `name`, `city`, `state`, `gender`, and `language` query parameters as the other endpoints.

### Influencer records

```bash
curl http://127.0.0.1:5000/api/influencers
```

Filter by name, city, state, gender, or language:

```bash
curl "http://127.0.0.1:5000/api/influencers?city=Visakhapatnam&gender=Female"
```
