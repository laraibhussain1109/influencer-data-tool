# Influencer Data Tool

A small Flask service that reads the `influencers.xlsx` workbook, calculates workbook-derived influencer metrics, and can fetch the requested Instagram insight fields from a configured provider API or JSON export.

## Why provider-backed fetching is required

Logged-out Instagram page scraping is unreliable: Instagram can block automated requests, require login, or remove data from public HTML. Audience demographics, reach, and engagement-per-reach are not public page data.

For a dependable one-click solution, configure one of these sources:

1. `INSTAGRAM_INSIGHTS_PROVIDER_FILE` or the UI **Provider JSON path** field for an export from a vendor/provider.
2. `INSTAGRAM_INSIGHTS_API_URL` plus optional `INSTAGRAM_INSIGHTS_API_TOKEN` for an approved analytics/provider API that can return the requested fields for workbook usernames.

The old public-page fetch endpoint remains available as a best-effort fallback, but the **Fetch complete insights** workflow uses provider-backed data so it does not fail just because Instagram blocks logged-out automated requests.

## Requested fields

The provider-backed insight fetcher expects these fields per Instagram profile:

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

The workbook metrics endpoint still calculates any fields already present in the sheet. If a provider/export omits any requested field, the API marks that profile as incomplete and lists the missing fields instead of inventing values.

## Provider JSON format

Use a JSON list, a username mapping, or an object with `profiles`. This example contains every requested field:

```json
{
  "profiles": [
    {
      "username": "example.creator",
      "top_5_locations_percent": [
        {"location": "Mumbai", "percentage": 42},
        {"location": "Delhi", "percentage": 18}
      ],
      "female_gender_ratio_percent": 61,
      "male_gender_ratio_percent": 39,
      "18_24_age_ratio_percent": 20,
      "25_34_age_ratio_percent": 55,
      "35_45_age_ratio_percent": 20,
      "45_plus_age_ratio_percent": 5,
      "engagement_rate_per_reach_percent": 8.4,
      "followers_summary": {"total": 17000, "average": 17000, "min": 17000, "max": 17000},
      "avg_video_reach_last_10": 12000,
      "avg_video_views_last_10": 9800
    }
  ]
}
```

Several common aliases are also accepted, such as `female_percent`, `age_18_24_percent`, `engagement_rate`, `follower_count`, `average_video_reach`, and `average_video_views`.

## Provider API format

When `INSTAGRAM_INSIGHTS_API_URL` is set, the app sends a `POST` request like this:

```json
{
  "profiles": [
    {"username": "example.creator", "instagram_link": "https://www.instagram.com/example.creator/"}
  ],
  "fields": ["top_5_locations_percent", "female_gender_ratio_percent", "avg_video_views_last_10"]
}
```

The provider should return either a JSON list of profile objects or `{ "profiles": [...] }` using the same field names/aliases as the JSON file format.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app influencer_service.app run --debug
```

Then open `http://127.0.0.1:5000/` and choose one of the buttons:

- **Calculate workbook details** reads the workbook only.
- **Fetch complete insights** reads the workbook and then fetches all requested fields from the configured provider API or JSON export.

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

Include provider-backed complete insights:

```bash
curl "http://127.0.0.1:5000/api/details?include_provider_insights=1&insights_file=/path/to/provider-export.json"
```

The combined endpoint returns `data_source`, `metrics`, `influencer_count`, normalized `influencers`, and optionally `provider_insights`. It accepts the same `file`, `name`, `city`, `state`, `gender`, and `language` query parameters as the other endpoints.

### Fetch complete insights

```bash
curl -X POST "http://127.0.0.1:5000/api/fetch-insights?insights_file=/path/to/provider-export.json"
```

Filter before fetching:

```bash
curl -X POST "http://127.0.0.1:5000/api/fetch-insights?city=Visakhapatnam&gender=Female&insights_file=/path/to/provider-export.json"
```

### Best-effort public Instagram fallback

```bash
curl -X POST http://127.0.0.1:5000/api/fetch-public-instagram
```

This fallback may fail when Instagram blocks logged-out automated requests and should not be used for private insight fields.

### Influencer records

```bash
curl http://127.0.0.1:5000/api/influencers
```

Filter by name, city, state, gender, or language:

```bash
curl "http://127.0.0.1:5000/api/influencers?city=Visakhapatnam&gender=Female"
```
