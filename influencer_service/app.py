"""Flask app for serving Instagram influencer analytics from an XLSX file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template_string, request

from influencer_service.analytics import build_metrics, detect_columns, filter_records, normalize_records
from influencer_service.rocketapi_insights import DEFAULT_ROCKETAPI_TOKEN, fetch_rocketapi_insights_for_records
from influencer_service.instagram_public import fetch_public_profiles
from influencer_service.xlsx_reader import load_first_sheet
from influencer_service.xlsx_writer import update_workbook_with_insights

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = REPO_ROOT / "influencers.xlsx"
DATA_SOURCE_DISCLOSURE = {
    "mode": "workbook_plus_rocketapi",
    "instagram_public_fetch_enabled": False,
    "rocketapi_enabled": True,
    "instagram_private_insights_enabled": False,
    "message": (
        "This service calculates workbook metrics and fetches Instagram details "
        "through RocketAPI using your API key. It does not rely on logged-out "
        "Instagram page scraping."
    ),
    "provider_fields": [
        "top_5_locations_percent",
        "female_gender_ratio_percent",
        "male_gender_ratio_percent",
        "18_24_age_ratio_percent",
        "25_34_age_ratio_percent",
        "35_45_age_ratio_percent",
        "45_plus_age_ratio_percent",
        "engagement_rate_per_reach_percent",
        "followers_summary",
        "avg_video_reach_last_10",
        "avg_video_views_last_10",
    ],
    "private_insight_requirements": [
        "RocketAPI account and API key",
        "RocketAPI endpoints enabled for profile and media data",
        "Any private insight permissions required by your RocketAPI plan",
    ],
}

FETCH_DETAILS_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RocketAPI Instagram Insights Fetcher</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f6f7fb; color: #172033; }
    main { max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }
    .hero { background: linear-gradient(135deg, #512bd4, #d62976); color: white; border-radius: 24px; padding: 32px; box-shadow: 0 20px 50px rgba(35, 31, 82, .18); }
    .hero h1 { margin: 0 0 8px; font-size: clamp(2rem, 4vw, 3.4rem); line-height: 1; }
    .hero p { max-width: 760px; margin: 0; color: rgba(255,255,255,.86); font-size: 1.05rem; }
    .controls { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; margin-top: 24px; }
    input { border: 0; border-radius: 14px; padding: 14px 16px; font: inherit; box-shadow: inset 0 0 0 1px rgba(23, 32, 51, .12); }
    button { border: 0; border-radius: 14px; padding: 14px 20px; background: #111827; color: white; cursor: pointer; font-weight: 700; font: inherit; }
    button:disabled { cursor: wait; opacity: .68; }
    .notice { margin-top: 18px; padding: 14px 16px; border-radius: 14px; background: #fff7ed; color: #9a3412; }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-top: 24px; }
    .card { background: white; border-radius: 18px; padding: 18px; box-shadow: 0 12px 34px rgba(15, 23, 42, .08); }
    .card h2, .card h3 { margin: 0 0 10px; font-size: .94rem; color: #64748b; text-transform: uppercase; letter-spacing: .08em; }
    .metric { font-size: 2rem; font-weight: 800; color: #0f172a; }
    .wide { grid-column: span 2; }
    .full { grid-column: 1 / -1; }
    table { width: 100%; border-collapse: collapse; font-size: .92rem; }
    th, td { text-align: left; padding: 11px 10px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
    th { color: #64748b; font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; }
    .pill { display: inline-flex; align-items: center; border-radius: 999px; padding: 5px 9px; font-size: .78rem; font-weight: 700; }
    .ok { background: #dcfce7; color: #166534; }
    .missing { background: #fee2e2; color: #991b1b; }
    .muted { color: #64748b; }
    @media (max-width: 860px) { .grid { grid-template-columns: 1fr; } .wide { grid-column: auto; } .controls { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>RocketAPI Instagram insights fetcher</h1>
      <p>Read Instagram links from the workbook and fetch details through RocketAPI. Replace the placeholder key with your RocketAPI key before running the fetch.</p>
      <div class="controls">
        <input id="fileInput" aria-label="Workbook path" placeholder="Workbook path" value="{{ default_workbook }}">
        <button id="fetchButton">Calculate workbook details</button>
        <input id="rocketApiTokenInput" aria-label="RocketAPI key" placeholder="RocketAPI API key" value="{{ rocketapi_token }}">
        <button id="insightsFetchButton" type="button">Fetch RocketAPI details</button>
        <button id="updateDetailsButton" type="button">Update Excel details</button>
      </div>
    </section>

    <div id="notice" class="notice"><strong>Data source:</strong> Workbook + RocketAPI. The bundled key is placeholder text; paste your own RocketAPI key to fetch live details.</div>
    <section id="results" class="grid" aria-live="polite"></section>
  </main>

  <script>
    const button = document.querySelector('#fetchButton');
    const fileInput = document.querySelector('#fileInput');
    const rocketApiTokenInput = document.querySelector('#rocketApiTokenInput');
    const insightsFetchButton = document.querySelector('#insightsFetchButton');
    const updateDetailsButton = document.querySelector('#updateDetailsButton');
    const results = document.querySelector('#results');
    const notice = document.querySelector('#notice');

    const labels = {
      top_5_locations_percent: 'Top 5 locations (%)',
      female_gender_ratio_percent: 'Female gender ratio (%)',
      male_gender_ratio_percent: 'Male gender ratio (%)',
      '18_24_age_ratio_percent': '18-24 age ratio (%)',
      '25_34_age_ratio_percent': '25-34 age ratio (%)',
      '35_45_age_ratio_percent': '35-45 age ratio (%)',
      '45_plus_age_ratio_percent': '45+ age ratio (%)',
      engagement_rate_per_reach_percent: 'Engagement rate per reach',
      followers: 'Followers summary',
      avg_video_reach_last_10: 'Avg. video reach (last 10)',
      avg_video_views_last_10: 'Avg. video views (last 10)'
    };

    function fmt(value) {
      if (value === null || value === undefined || value === '') return 'Unavailable';
      if (typeof value === 'number') return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
      return value;
    }

    function status(key, payload) {
      const missing = payload.metrics.unavailable_fields || {};
      return missing[key] ? '<span class="pill missing">Needs source data</span>' : '<span class="pill ok">Fetched</span>';
    }

    function metricCard(title, value, key, payload) {
      return `<article class="card"><h2>${title}</h2><div class="metric">${fmt(value)}</div><div>${status(key, payload)}</div></article>`;
    }

    function renderLocations(locations, payload) {
      const rows = (locations || []).map(item => `<tr><td>${item.location}</td><td>${item.count}</td><td>${fmt(item.percentage)}%</td></tr>`).join('');
      return `<article class="card wide"><h2>${labels.top_5_locations_percent}</h2>${status('top_5_locations_percent', payload)}<table><thead><tr><th>Location</th><th>Count</th><th>%</th></tr></thead><tbody>${rows || '<tr><td colspan="3" class="muted">No location columns found.</td></tr>'}</tbody></table></article>`;
    }

    function renderFollowers(summary) {
      return `<article class="card wide"><h2>${labels.followers}</h2><table><tbody>
        <tr><th>Total</th><td>${fmt(summary.total)}</td></tr>
        <tr><th>Average</th><td>${fmt(summary.average)}</td></tr>
        <tr><th>Min</th><td>${fmt(summary.min)}</td></tr>
        <tr><th>Max</th><td>${fmt(summary.max)}</td></tr>
      </tbody></table></article>`;
    }


    function renderSourceDisclosure(payload) {
      const requirements = (payload.data_source.private_insight_requirements || []).map(item => `<li>${item}</li>`).join('');
      const fields = (payload.data_source.provider_fields || []).map(item => `<li>${item}</li>`).join('');
      return `<article class="card full"><h2>Data source disclosure</h2><p>${payload.data_source.message}</p><p class="muted">Complete fields requested from RocketAPI:</p><ul>${fields}</ul><p class="muted">RocketAPI setup must include:</p><ul>${requirements}</ul></article>`;
    }

    function renderProviderInsights(payload) {
      if (!payload.provider_insights) return '';
      const rows = (payload.provider_insights.results || []).map(result => {
        const insights = result.insights || {};
        const followers = insights.followers_summary || {};
        return `<tr><td>${fmt(result.username)}</td><td>${fmt(followers.total || followers.average)}</td><td>${fmt(insights.avg_video_views_last_10)}</td><td>${fmt(insights.avg_video_reach_last_10)}</td><td>${fmt(insights.engagement_rate_per_reach_percent)}%</td><td>${result.ok ? 'Complete' : `Missing: ${(result.missing_fields || []).join(', ')}`}</td></tr>`;
      }).join('');
      const provider = payload.provider_insights.provider || {};
      return `<article class="card full"><h2>RocketAPI details fetched (${payload.provider_insights.complete_count}/${payload.provider_insights.count})</h2><p class="muted">Provider: ${provider.name}. Missing fields mean RocketAPI did not return that metric for the profile/plan.</p><table><thead><tr><th>Username</th><th>Followers</th><th>Avg. video views</th><th>Avg. video reach</th><th>Engagement / reach</th><th>Status</th></tr></thead><tbody>${rows || '<tr><td colspan="6" class="muted">No provider insights were returned.</td></tr>'}</tbody></table></article>`;
    }

    function renderWorkbookUpdate(payload) {
      if (!payload.workbook_update) return '';
      const update = payload.workbook_update;
      return `<article class="card full"><h2>Excel updated</h2><p>Updated rows: ${fmt(update.updated_rows)}</p><p class="muted">Workbook: ${fmt(update.workbook)}</p><p class="muted">Columns written: ${(update.written_columns || []).join(', ')}</p></article>`;
    }

    function renderMissing(payload) {
      const entries = Object.entries(payload.metrics.unavailable_fields || {});
      if (!entries.length) return '';
      const rows = entries.map(([key, reason]) => `<tr><td>${labels[key] || key}</td><td>${reason}</td></tr>`).join('');
      return `<article class="card full"><h2>Fields that need an insights export/provider</h2><p class="muted">The app does not invent private Instagram analytics. Add these columns to the workbook or connect a compliant provider feed, then calculate again.</p><table><thead><tr><th>Requested detail</th><th>Why unavailable</th></tr></thead><tbody>${rows}</tbody></table></article>`;
    }

    function renderInfluencers(payload) {
      const rows = payload.influencers.slice(0, 25).map(item => `<tr><td>${fmt(item.full_name)}</td><td>${fmt(item.followers)}</td><td>${fmt(item.gender)}</td><td>${fmt([item.city, item.state].filter(Boolean).join(', '))}</td></tr>`).join('');
      return `<article class="card full"><h2>Influencers loaded (${payload.influencer_count})</h2><table><thead><tr><th>Name</th><th>Followers</th><th>Gender</th><th>Location</th></tr></thead><tbody>${rows}</tbody></table></article>`;
    }

    function workbookParams() {
      const params = new URLSearchParams();
      if (fileInput.value.trim()) params.set('file', fileInput.value.trim());
      if (rocketApiTokenInput.value.trim()) params.set('rocketapi_token', rocketApiTokenInput.value.trim());
      return params;
    }

    async function fetchDetails({ includeInsights = false, updateWorkbook = false } = {}) {
      button.disabled = true;
      insightsFetchButton.disabled = true;
      updateDetailsButton.disabled = true;
      button.textContent = includeInsights ? 'Fetching insights...' : 'Calculating...';
      insightsFetchButton.textContent = includeInsights ? 'Fetching RocketAPI...' : 'Fetch RocketAPI details';
      updateDetailsButton.textContent = updateWorkbook ? 'Updating Excel...' : 'Update Excel details';
      notice.style.display = 'block';
      results.innerHTML = '';
      const params = workbookParams();
      if (includeInsights) params.set('include_rocketapi', '1');
      if (updateWorkbook) params.set('update_workbook', '1');
      try {
        const response = await fetch(`/api/details?${params.toString()}`);
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Unable to fetch details.');
        const m = payload.metrics;
        results.innerHTML = [
          renderSourceDisclosure(payload),
          metricCard('Total influencers', m.total_influencers, 'total_influencers', payload),
          metricCard(labels.female_gender_ratio_percent, `${fmt(m.female_gender_ratio_percent)}%`, 'female_gender_ratio_percent', payload),
          metricCard(labels.male_gender_ratio_percent, `${fmt(m.male_gender_ratio_percent)}%`, 'male_gender_ratio_percent', payload),
          metricCard(labels['18_24_age_ratio_percent'], `${fmt(m['18_24_age_ratio_percent'])}%`, '18_24_age_ratio_percent', payload),
          metricCard(labels['25_34_age_ratio_percent'], `${fmt(m['25_34_age_ratio_percent'])}%`, '25_34_age_ratio_percent', payload),
          metricCard(labels['35_45_age_ratio_percent'], `${fmt(m['35_45_age_ratio_percent'])}%`, '35_45_age_ratio_percent', payload),
          metricCard(labels['45_plus_age_ratio_percent'], `${fmt(m['45_plus_age_ratio_percent'])}%`, '45_plus_age_ratio_percent', payload),
          metricCard(labels.engagement_rate_per_reach_percent, `${fmt(m.engagement_rate_per_reach_percent)}%`, 'engagement_rate_per_reach_percent', payload),
          metricCard(labels.avg_video_reach_last_10, fmt(m.avg_video_reach_last_10), 'avg_video_reach_last_10', payload),
          metricCard(labels.avg_video_views_last_10, fmt(m.avg_video_views_last_10), 'avg_video_views_last_10', payload),
          renderLocations(m.top_5_locations_percent, payload),
          renderFollowers(m.followers),
          renderProviderInsights(payload),
          renderWorkbookUpdate(payload),
          renderMissing(payload),
          renderInfluencers(payload)
        ].join('');
      } catch (error) {
        notice.textContent = error.message;
        notice.style.display = 'block';
      } finally {
        button.disabled = false;
        insightsFetchButton.disabled = false;
        updateDetailsButton.disabled = false;
        button.textContent = 'Calculate workbook details';
        insightsFetchButton.textContent = 'Fetch RocketAPI details';
        updateDetailsButton.textContent = 'Update Excel details';
      }
    }

    button.addEventListener('click', () => fetchDetails());
    insightsFetchButton.addEventListener('click', () => fetchDetails({ includeInsights: true }));
    updateDetailsButton.addEventListener('click', () => fetchDetails({ includeInsights: true, updateWorkbook: true }));
  </script>
</body>
</html>
"""


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return render_template_string(
            FETCH_DETAILS_PAGE,
            default_workbook=str(DEFAULT_WORKBOOK),
            rocketapi_token=DEFAULT_ROCKETAPI_TOKEN,
        )

    @app.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.errorhandler(FileNotFoundError)
    def workbook_not_found(error: FileNotFoundError) -> tuple[Any, int]:
        return jsonify({"error": str(error)}), 404

    @app.errorhandler(ValueError)
    def invalid_workbook(error: ValueError) -> tuple[Any, int]:
        return jsonify({"error": str(error)}), 400

    @app.get("/api/metrics")
    def metrics() -> Any:
        records, workbook = _load_records_from_request()
        payload = build_metrics(records)
        payload["source_file"] = str(workbook)
        payload["data_source"] = DATA_SOURCE_DISCLOSURE
        return jsonify(payload)

    @app.get("/api/details")
    def details() -> Any:
        records, workbook = _load_records_from_request()
        filters = _filters_from_request()
        filtered = filter_records(records, filters)
        include_public = _truthy(request.args.get("include_public_instagram"))
        include_provider = _truthy(request.args.get("include_provider_insights")) or _truthy(request.args.get("include_rocketapi"))
        update_workbook = _truthy(request.args.get("update_workbook"))
        payload = _details_payload(filtered, workbook)
        if include_provider or update_workbook:
            payload["provider_insights"] = _fetch_provider_insights_for_records(filtered)
        if update_workbook:
            payload["workbook_update"] = update_workbook_with_insights(workbook, payload["provider_insights"])
        if include_public:
            payload["public_instagram"] = _fetch_public_instagram_for_records(filtered)
        return jsonify(payload)

    @app.post("/api/update-workbook")
    def update_workbook() -> Any:
        records, workbook = _load_records_from_request()
        filtered = filter_records(records, _filters_from_request())
        payload = _details_payload(filtered, workbook)
        payload["provider_insights"] = _fetch_provider_insights_for_records(filtered)
        payload["workbook_update"] = update_workbook_with_insights(workbook, payload["provider_insights"])
        return jsonify(payload)

    @app.post("/api/fetch-rocketapi")
    def provider_insights() -> Any:
        records, workbook = _load_records_from_request()
        filtered = filter_records(records, _filters_from_request())
        payload = _details_payload(filtered, workbook)
        payload["provider_insights"] = _fetch_provider_insights_for_records(filtered)
        return jsonify(payload)

    @app.post("/api/fetch-public-instagram")
    def public_instagram() -> Any:
        records, workbook = _load_records_from_request()
        filtered = filter_records(records, _filters_from_request())
        payload = _details_payload(filtered, workbook)
        payload["public_instagram"] = _fetch_public_instagram_for_records(filtered)
        return jsonify(payload)

    @app.get("/api/influencers")
    def influencers() -> Any:
        records, workbook = _load_records_from_request()
        filtered = filter_records(records, _filters_from_request())
        return jsonify(
            {
                "source_file": str(workbook),
                "count": len(filtered),
                "results": normalize_records(filtered),
            }
        )

    return app


def _details_payload(records: list[dict[str, Any]], workbook: Path) -> dict[str, Any]:
    return {
        "source_file": str(workbook),
        "data_source": DATA_SOURCE_DISCLOSURE,
        "metrics": build_metrics(records),
        "influencer_count": len(records),
        "influencers": normalize_records(records),
    }


def _fetch_provider_insights_for_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    return fetch_rocketapi_insights_for_records(records, token=request.args.get("rocketapi_token"))


def _fetch_public_instagram_for_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    columns = detect_columns(records)
    if not columns.instagram_link:
        return {"count": 0, "results": [], "errors": ["No Instagram link column was found."]}
    links = [str(row.get(columns.instagram_link, "")).strip() for row in records]
    links = [link for link in links if link]
    results = fetch_public_profiles(links)
    return {
        "count": len(results),
        "results": results,
        "errors": [result["error"] for result in results if not result.get("ok")],
    }


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "on"}


def _filters_from_request() -> dict[str, str]:
    return {
        key: value
        for key in ("name", "city", "state", "gender", "language")
        if (value := request.args.get(key))
    }


def _load_records_from_request() -> tuple[list[dict[str, Any]], Path]:
    workbook = Path(request.args.get("file", DEFAULT_WORKBOOK)).expanduser().resolve()
    if not workbook.exists():
        raise FileNotFoundError(f"Workbook not found: {workbook}")
    return load_first_sheet(workbook), workbook


app = create_app()
