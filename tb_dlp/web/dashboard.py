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
        f"<tr><td class='px-4 py-2 border-b border-gray-100'>{he(p)}</td><td class='px-4 py-2 border-b border-gray-100'>{c}</td></tr>"
        for p, c in sorted(by_platform.items(), key=lambda kv: -kv[1])
    ) or "<tr><td colspan='2' class='px-4 py-6 text-center text-gray-500'>No data yet.</td></tr>"

    chat_rows = "".join(
        f"<tr><td class='px-4 py-2 border-b border-gray-100'>{he(str(d.get('title') or cid))}</td><td class='px-4 py-2 border-b border-gray-100'>{d.get('total', 0)}</td><td class='px-4 py-2 border-b border-gray-100'>{d.get('cache_hits', 0)}</td></tr>"
        for cid, d in sorted(by_chat.items(), key=lambda kv: -kv[1].get("total", 0))
    ) or "<tr><td colspan='3' class='px-4 py-6 text-center text-gray-500'>No data yet.</td></tr>"

    ai_stats = stats.AI_STATS
    ai_status = "ON" if ai.AI_ENABLED else "OFF"
    ai_btn_class = "border-red-500 text-red-500 hover:bg-red-50" if ai.AI_ENABLED else "border-green-500 text-green-500 hover:bg-green-50"
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
        f"""<div class="bg-white rounded-lg shadow mb-4">
  <div class="px-4 py-3 border-b border-gray-200 font-semibold">AI activity by chat</div>
  <div class="p-4"><canvas id="aiChart"></canvas></div>
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
        """<div class="bg-white rounded-lg shadow mb-4"><div class="p-4 text-gray-500">No AI activity yet.</div></div>"""
    )
    body = f"""
<div class="flex justify-between items-center mb-4">
  <h4 class="text-xl font-semibold">Stats</h4>
  <form method="post" action="/admin/ai-toggle">
    <button class="px-3 py-1 text-sm rounded border {ai_btn_class}">AI bot: {ai_status} (turn {ai_action})</button>
  </form>
</div>
<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
  <div class="bg-white rounded-lg shadow p-4 text-center"><div class="text-3xl font-bold">{total}</div><div class="text-gray-500 text-sm">Videos sent</div></div>
  <div class="bg-white rounded-lg shadow p-4 text-center"><div class="text-3xl font-bold">{cache_hits}</div><div class="text-gray-500 text-sm">From cache</div></div>
  <div class="bg-white rounded-lg shadow p-4 text-center"><div class="text-3xl font-bold">{len(stats.VIDEO_CACHE)}</div><div class="text-gray-500 text-sm">Cached links</div></div>
  <div class="bg-white rounded-lg shadow p-4 text-center"><div class="text-3xl font-bold">{len(profiles.USER_PROFILES)}</div><div class="text-gray-500 text-sm">Profiles</div></div>
</div>
<h5 class="text-lg font-semibold mb-3">AI chat activity</h5>
<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
  <div class="bg-white rounded-lg shadow p-4 text-center"><div class="text-3xl font-bold">{ai_totals['mention']}</div><div class="text-gray-500 text-sm">Mentions answered</div></div>
  <div class="bg-white rounded-lg shadow p-4 text-center"><div class="text-3xl font-bold">{ai_totals['reply']}</div><div class="text-gray-500 text-sm">Replies to bot</div></div>
  <div class="bg-white rounded-lg shadow p-4 text-center"><div class="text-3xl font-bold">{ai_totals['unprompted']}</div><div class="text-gray-500 text-sm">Unprompted chime-ins</div></div>
  <div class="bg-white rounded-lg shadow p-4 text-center"><div class="text-3xl font-bold">{ai_totals['rate_limited']}</div><div class="text-gray-500 text-sm">Rate-limited</div></div>
</div>
{ai_chart_section}
<p class="text-gray-500 text-sm mb-4">Profile summaries generated: {ai_stats.get('profile_update', 0)} (global, not tied to a single chat)</p>
<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
  <div class="bg-white rounded-lg shadow overflow-hidden">
    <div class="px-4 py-3 border-b border-gray-200 font-semibold">By platform</div>
    <table class="w-full text-sm">
      <thead class="bg-gray-50"><tr><th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Platform</th><th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Count</th></tr></thead>
      <tbody>{platform_rows}</tbody>
    </table>
  </div>
  <div class="bg-white rounded-lg shadow overflow-hidden">
    <div class="px-4 py-3 border-b border-gray-200 font-semibold">By chat</div>
    <table class="w-full text-sm">
      <thead class="bg-gray-50"><tr><th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Chat</th><th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Videos</th><th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Cache hits</th></tr></thead>
      <tbody>{chat_rows}</tbody>
    </table>
  </div>
</div>"""
    return aio_web.Response(text=page("Stats", body, active="stats"), content_type="text/html")


async def ai_toggle(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    ai.toggle_ai_enabled()
    return aio_web.HTTPFound("/admin")

