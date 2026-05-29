"""Flask app for serving Instagram influencer analytics from an XLSX file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template_string, request

from influencer_service.analytics import build_metrics, detect_columns, filter_records, normalize_records
from influencer_service.instagram_public import fetch_public_profiles
from influencer_service.xlsx_reader import load_first_sheet

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = REPO_ROOT / "influencers.xlsx"
DATA_SOURCE_DISCLOSURE = {
    "mode": "workbook_plus_public_instagram",
    "instagram_public_fetch_enabled": True,
    "instagram_private_insights_enabled": False,
    "message": (
        "This service can fetch public Instagram profile-page metadata such as "
        "followers and recent public video views for links in the workbook. It does "
        "not log in, bypass privacy controls, or fetch private audience Insights."
    ),
    "public_fields": [
        "followers",
        "following",
        "posts",
        "full_name",
        "biography",
        "is_private",
        "is_verified",
        "avg_video_views_last_10",
    ],
    "private_insight_requirements": [
        "Instagram Graph API or approved provider integration",
        "Creator/Business account authorization from each influencer",
        "Private audience demographics, reach, and engagement insight permissions",
    ],
}

FETCH_DETAILS_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Instagram Public Data Fetcher</title>
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
      <h1>Instagram public data fetcher</h1>
      <p>Read the Instagram links in your workbook, calculate sheet metrics, and optionally fetch public profile-page data such as followers and recent public video views. Private audience Insights still require account authorization/API access.</p>
      <div class="controls">
        <input id="fileInput" aria-label="Workbook path" placeholder="Workbook path" value="{{ default_workbook }}">
        <button id="fetchButton">Calculate workbook details</button>
        <button id="publicFetchButton" type="button">Fetch public Instagram data</button>
      </div>
    </section>

    <div id="notice" class="notice"><strong>Data source:</strong> Workbook + public Instagram pages. Fetching public data may fail if Instagram rate-limits or blocks automated requests.</div>
    <section id="results" class="grid" aria-live="polite"></section>
  </main>

  <script>
    const button = document.querySelector('#fetchButton');
    const fileInput = document.querySelector('#fileInput');
    const publicFetchButton = document.querySelector('#publicFetchButton');
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
      const fields = (payload.data_source.public_fields || []).map(item => `<li>${item}</li>`).join('');
      return `<article class="card full"><h2>Data source disclosure</h2><p>${payload.data_source.message}</p><p class="muted">Public fields this fetcher tries to collect:</p><ul>${fields}</ul><p class="muted">For private audience Insights, add:</p><ul>${requirements}</ul></article>`;
    }

    function renderPublicInstagram(payload) {
      if (!payload.public_instagram) return '';
      const rows = (payload.public_instagram.results || []).map(result => {
        const profile = result.profile || {};
        const statusText = result.ok ? 'Fetched' : `Failed: ${result.error}`;
        return `<tr><td>${fmt(profile.username)}</td><td>${fmt(profile.followers)}</td><td>${fmt(profile.posts)}</td><td>${fmt(profile.avg_video_views_last_10)}</td><td>${fmt(profile.videos_found)}</td><td>${statusText}</td></tr>`;
      }).join('');
      return `<article class="card full"><h2>Public Instagram data fetched (${payload.public_instagram.count})</h2><table><thead><tr><th>Username</th><th>Followers</th><th>Posts</th><th>Avg. video views</th><th>Videos found</th><th>Status</th></tr></thead><tbody>${rows || '<tr><td colspan="6" class="muted">No Instagram links were fetched.</td></tr>'}</tbody></table></article>`;
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
      return params;
    }

    async function fetchDetails({ includePublic = false } = {}) {
      button.disabled = true;
      publicFetchButton.disabled = true;
      button.textContent = includePublic ? 'Fetching public data...' : 'Calculating...';
      publicFetchButton.textContent = includePublic ? 'Fetching public data...' : 'Fetch public Instagram data';
      notice.style.display = 'block';
      results.innerHTML = '';
      const params = workbookParams();
      if (includePublic) params.set('include_public_instagram', '1');
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
          renderPublicInstagram(payload),
          renderMissing(payload),
          renderInfluencers(payload)
        ].join('');
      } catch (error) {
        notice.textContent = error.message;
        notice.style.display = 'block';
      } finally {
        button.disabled = false;
        publicFetchButton.disabled = false;
        button.textContent = 'Calculate workbook details';
        publicFetchButton.textContent = 'Fetch public Instagram data';
      }
    }

    button.addEventListener('click', () => fetchDetails());
    publicFetchButton.addEventListener('click', () => fetchDetails({ includePublic: true }));
  </script>
</body>
</html>
"""


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return render_template_string(FETCH_DETAILS_PAGE, default_workbook=str(DEFAULT_WORKBOOK))

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
        payload = _details_payload(filtered, workbook)
        if include_public:
            payload["public_instagram"] = _fetch_public_instagram_for_records(filtered)
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
