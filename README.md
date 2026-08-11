# Influencer Data Tool

A small Flask service that reads the `influencers.xlsx` workbook in this repository and exposes influencer analytics over HTTP.

It also provides a batch Instagram deliverable collector. Give it an XLSX file with an
influencer-name column and an Instagram post/reel URL column; it writes likes, video views,
comment totals, and aggregate VADER comment sentiment to a new workbook.

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

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app influencer_service.app run --debug
```

### Collect deliverable results

Your first worksheet should contain headers such as `Influencer Name` and `Deliverable URL`.
Accepted URL headers also include `Instagram Reel URL`, `Reel URL`, `Post URL`, and
`Instagram Link`. Run:

```bash
python -m influencer_service.cli campaign.xlsx --output campaign_results.xlsx --max-comments 500
```

Only comments actually returned (up to `--max-comments`) are analyzed; `Comments` remains
Instagram's total comment count and `Comments Analyzed` makes sampling explicit. A failed or
private post is recorded as an error row, so it does not stop the rest of the campaign.

Instagram may require authentication or throttle collection. For access you are authorized
to use, create an Instaloader session file and set both variables before running:

```bash
export INSTAGRAM_USERNAME=your_username
export INSTAGRAM_SESSION_FILE=/secure/path/session-your_username
```

Do not put passwords or session files in the workbook or repository. Collection is limited
to data Instagram makes available to the supplied session; private/deleted posts and hidden
like/view counts cannot be bypassed. Ensure your use complies with Instagram's terms,
privacy requirements, and the consent applicable to the campaign.

## API

### Health check

```bash
curl http://127.0.0.1:5000/health
```

### Aggregate metrics

```bash
curl http://127.0.0.1:5000/api/metrics
```

Use a different workbook path:

```bash
curl "http://127.0.0.1:5000/api/metrics?file=/path/to/influencers.xlsx"
```

### Influencer records

```bash
curl http://127.0.0.1:5000/api/influencers
```

Filter by name, city, state, gender, or language:

```bash
curl "http://127.0.0.1:5000/api/influencers?city=Visakhapatnam&gender=Female"
```

### Trigger a deliverable batch through HTTP

```bash
curl -X POST http://127.0.0.1:5000/api/deliverables/collect \
  -H 'Content-Type: application/json' \
  -d '{"file":"/data/campaign.xlsx","output":"/data/results.xlsx","max_comments":500}'
```

This endpoint performs collection synchronously and returns per-row results plus success and
failure counts. For large campaigns, use the CLI from a scheduled/background job rather than
holding an HTTP request open.
