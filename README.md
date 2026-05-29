# Influencer Data Tool

A Flask service that reads the `influencers.xlsx` workbook, calculates any metrics already present in the sheet, and fetches Instagram profile/media details through RocketAPI for the Instagram links in the workbook.

## RocketAPI setup

RocketAPI is now the primary fetch path. The app uses RocketAPI's documented HTTP endpoints equivalent to the Python SDK examples:

- `get_web_profile_info(username)` / `/instagram/user/get_web_profile_info` for profile data such as followers.
- `get_user_media_by_username(username, count=12)` / `/instagram/user/get_media_by_username` for recent media.
- `get_user_clips(id, count=12)` / `/instagram/user/get_clips` for recent Reels/clips when a user id is available.

A placeholder key is included in the UI and code:

```text
ROCKETAPI_API_KEY_REPLACE_ME
```

Replace it in the UI before clicking **Fetch RocketAPI details**, or set an environment variable:

```bash
export ROCKETAPI_TOKEN="your-real-rocketapi-key"
```

RocketAPI's public/profile/media endpoints can fetch followers and recent video/view-like metrics. If your RocketAPI plan/response exposes audience demographics or reach insights, the app will normalize them into the requested fields. If RocketAPI does not return a specific field for a profile, the response lists that field in `missing_fields` rather than inventing values.

## Requested fields

The RocketAPI fetcher attempts to return these fields per Instagram profile:

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

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app influencer_service.app run --debug
```

Then open `http://127.0.0.1:5000/` and choose one of the buttons:

- **Calculate workbook details** reads the workbook only.
- **Fetch RocketAPI details** reads Instagram links from the workbook and calls RocketAPI using the key in the UI or `ROCKETAPI_TOKEN`.
- **Update Excel details** fetches RocketAPI details and immediately writes them back into the selected `.xlsx` file.

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

### Combined details payload with RocketAPI

```bash
curl "http://127.0.0.1:5000/api/details?include_rocketapi=1&rocketapi_token=your-real-rocketapi-key"
```

The combined endpoint returns `data_source`, workbook `metrics`, `influencer_count`, normalized `influencers`, and `provider_insights` when RocketAPI fetching is enabled. Add `update_workbook=1` to also save the fetched details into the workbook immediately.

### Fetch RocketAPI details

```bash
curl -X POST "http://127.0.0.1:5000/api/fetch-rocketapi?rocketapi_token=your-real-rocketapi-key"
```

### Update Excel with RocketAPI details

```bash
curl -X POST "http://127.0.0.1:5000/api/update-workbook?rocketapi_token=your-real-rocketapi-key"
```

This appends/updates the following columns in the first worksheet: RocketAPI status fields plus all requested metrics (locations, gender ratios, age ratios, engagement per reach, followers summary, average video reach, and average video views).

Filter before fetching:

```bash
curl -X POST "http://127.0.0.1:5000/api/fetch-rocketapi?city=Visakhapatnam&gender=Female&rocketapi_token=your-real-rocketapi-key"
```

### Best-effort public Instagram fallback

```bash
curl -X POST http://127.0.0.1:5000/api/fetch-public-instagram
```

This fallback may fail when Instagram blocks logged-out automated requests. Use RocketAPI for the main workflow.

### Influencer records

```bash
curl http://127.0.0.1:5000/api/influencers
```

Filter by name, city, state, gender, or language:

```bash
curl "http://127.0.0.1:5000/api/influencers?city=Visakhapatnam&gender=Female"
```
