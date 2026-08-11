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

Instagram requires an authenticated account to retrieve comments. Export the account ID and
password as environment variables before starting the CLI or Flask process. An optional
session file avoids logging in again on every run:

```bash
export INSTAGRAM_USERNAME=your_username
export INSTAGRAM_PASSWORD='your_password'
export INSTAGRAM_SESSION_FILE=/secure/path/session-your_username
```

On the first run the collector logs in with the ID/password and saves the resulting session.
Later runs validate and reuse that session. If it has expired, the password refreshes it. If
you omit `INSTAGRAM_SESSION_FILE`, the collector logs in for that process without writing a
session to disk. Never put the ID, password, or session file in a workbook, URL, API request,
or repository. Use a dedicated account, protect these environment variables, and restrict
the session file to the service user (for example, `chmod 600`). Collection is limited to
data available to that account; private/deleted posts and hidden like/view counts cannot be
bypassed. Ensure your use complies with Instagram's terms, privacy requirements, and the
consent applicable to the campaign.

#### Instagram “Checkpoint required” on Windows

This is an Instagram account-security challenge, not a workbook error. The collector now
prints a short, clickable `https://www.instagram.com/auth_platform/...` URL instead of a
Python traceback. Resolve it as follows:

1. Open the printed URL in a browser where the same Instagram account is already signed in.
2. Confirm that the login was you and complete any verification Instagram requests.
3. Keep the same three environment variables configured, especially a writable
   `INSTAGRAM_SESSION_FILE` path.
4. Run the same collector command again. The successful login will be saved to the session
   file, and future runs will reuse it instead of repeatedly submitting the password.

For Windows Command Prompt, configure the variables in the same window used to run Python:

```bat
set INSTAGRAM_USERNAME=your_username
set INSTAGRAM_PASSWORD=your_password
set INSTAGRAM_SESSION_FILE=%USERPROFILE%\.instagram-session-your_username
python -m influencer_service.cli campaign.xlsx --output campaign_results.xlsx --max-comments 500
```

For PowerShell, use `$env:INSTAGRAM_USERNAME`, `$env:INSTAGRAM_PASSWORD`, and
`$env:INSTAGRAM_SESSION_FILE` instead. A checkpoint must be approved by the account owner;
the application intentionally does not attempt to bypass Instagram's security challenge.

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
