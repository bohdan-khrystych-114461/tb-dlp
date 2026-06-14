import json

from aiohttp import web as aio_web

from tb_dlp import ai, profiles, stats
from tb_dlp.web.layout import auth, he, page

# Color per AI activity trigger, used for the stacked bar chart segments.
AI_TRIGGER_COLORS = {
    "mention": "#0d6efd",
    "reply": "#6f42c1",
    "unprompted": "#20c997",
    "rate_limited": "#dc3545",
}
AI_TRIGGER_LABELS = {
    "mention": "Mentions",
    "reply": "Replies to bot",
    "unprompted": "Unprompted",
    "rate_limited": "Rate-limited",
}


async def stats_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    total = stats.STATS.get("total", 0)
    cache_hits = stats.STATS.get("cache_hits", 0)
    by_platform = stats.STATS.get("by_platform", {})
    by_chat = stats.STATS.get("by_chat", {})

    platform_rows = "".join(
        f"<tr><td>{he(p)}</td><td>{c}</td></tr>"
        for p, c in sorted(by_platform.items(), key=lambda kv: -kv[1])
    ) or "<tr><td colspan='2' class='text-muted'>No data yet.</td></tr>"

    chat_rows = "".join(
        f"<tr><td>{he(str(d.get('title') or cid))}</td><td>{d.get('total', 0)}</td><td>{d.get('cache_hits', 0)}</td></tr>"
        for cid, d in sorted(by_chat.items(), key=lambda kv: -kv[1].get("total", 0))
    ) or "<tr><td colspan='3' class='text-muted'>No data yet.</td></tr>"

    ai_stats = stats.AI_STATS
    ai_status = "ON" if ai.AI_ENABLED else "OFF"
    ai_btn_class = "btn-outline-danger" if ai.AI_ENABLED else "btn-outline-success"
    ai_action = "off" if ai.AI_ENABLED else "on"

    ai_by_chat = sorted(
        ai_stats.get("by_chat", {}).items(),
        key=lambda kv: -sum(kv[1].get(k, 0) for k in stats.AI_STAT_TRIGGERS),
    )
    ai_chart_data = {
        "labels": [d.get("title") or cid for cid, d in ai_by_chat],
        "datasets": [
            {
                "label": AI_TRIGGER_LABELS[trigger],
                "data": [d.get(trigger, 0) for _, d in ai_by_chat],
                "backgroundColor": AI_TRIGGER_COLORS[trigger],
            }
            for trigger in stats.AI_STAT_TRIGGERS
        ],
    }
    # Escape "</" so a chat title containing "</script>" can't break out of
    # the inline <script> block this gets embedded in.
    ai_chart_json = json.dumps(ai_chart_data).replace("</", "<\\/")
    ai_totals = {k: sum(d.get(k, 0) for _, d in ai_by_chat) for k in stats.AI_STAT_TRIGGERS}
    ai_chart_section = (
        f"""<div class="card shadow-sm mb-4">
  <div class="card-header fw-semibold">AI activity by chat</div>
  <div class="card-body"><canvas id="aiChart"></canvas></div>
</div>
<script>
new Chart(document.getElementById('aiChart'), {{
  type: 'bar',
  data: {ai_chart_json},
  options: {{
    responsive: true,
    scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, beginAtZero: true, ticks: {{ precision: 0 }} }} }}
  }}
}});
</script>"""
        if ai_by_chat else
        """<div class="card shadow-sm mb-4"><div class="card-body text-muted">No AI activity yet.</div></div>"""
    )
    body = f"""
<div class="d-flex justify-content-between align-items-center mb-4">
  <h4 class="mb-0">Stats</h4>
  <form method="post" action="/admin/ai-toggle">
    <button class="btn btn-sm {ai_btn_class}">AI bot: {ai_status} (turn {ai_action})</button>
  </form>
</div>
<div class="row g-3 mb-4">
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{total}</div><div class="text-muted small">Videos sent</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{cache_hits}</div><div class="text-muted small">From cache</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{len(stats.VIDEO_CACHE)}</div><div class="text-muted small">Cached links</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{len(profiles.USER_PROFILES)}</div><div class="text-muted small">Profiles</div></div></div></div>
</div>
<h5 class="mb-3">AI chat activity</h5>
<div class="row g-3 mb-4">
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{ai_totals['mention']}</div><div class="text-muted small">Mentions answered</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{ai_totals['reply']}</div><div class="text-muted small">Replies to bot</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{ai_totals['unprompted']}</div><div class="text-muted small">Unprompted chime-ins</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{ai_totals['rate_limited']}</div><div class="text-muted small">Rate-limited</div></div></div></div>
</div>
{ai_chart_section}
<p class="text-muted small mb-4">Profile summaries generated: {ai_stats.get('profile_update', 0)} (global, not tied to a single chat)</p>
<div class="row g-3">
  <div class="col-md-5">
    <div class="card shadow-sm">
      <div class="card-header fw-semibold">By platform</div>
      <table class="table table-sm mb-0">
        <thead><tr><th>Platform</th><th>Count</th></tr></thead>
        <tbody>{platform_rows}</tbody>
      </table>
    </div>
  </div>
  <div class="col-md-7">
    <div class="card shadow-sm">
      <div class="card-header fw-semibold">By chat</div>
      <table class="table table-sm mb-0">
        <thead><tr><th>Chat</th><th>Videos</th><th>Cache hits</th></tr></thead>
        <tbody>{chat_rows}</tbody>
      </table>
    </div>
  </div>
</div>"""
    return aio_web.Response(text=page("Stats", body, active="stats"), content_type="text/html")


async def ai_toggle(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    ai.toggle_ai_enabled()
    return aio_web.HTTPFound("/admin")
