from aiohttp import web as aio_web

from tb_dlp import ai, profiles, stats
from tb_dlp.web.layout import auth, he, page


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
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{ai_stats.get('mention', 0)}</div><div class="text-muted small">Mentions answered</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{ai_stats.get('reply', 0)}</div><div class="text-muted small">Replies to bot</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{ai_stats.get('unprompted', 0)}</div><div class="text-muted small">Unprompted chime-ins</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{ai_stats.get('profile_update', 0)}</div><div class="text-muted small">Profile updates</div></div></div></div>
  <div class="col-6 col-md-3"><div class="card text-center shadow-sm"><div class="card-body"><div class="fs-2 fw-bold">{ai_stats.get('rate_limited', 0)}</div><div class="text-muted small">Rate-limited</div></div></div></div>
</div>
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
