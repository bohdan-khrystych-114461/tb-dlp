import json

from aiohttp import web as aio_web

from tb_dlp import ai, profiles, stats
from tb_dlp.web.layout import auth, he, page

AI_TRIGGER_COLORS = {
    "mention": "#6366f1",
    "reply": "#8b5cf6",
    "unprompted": "#06b6d4",
    "rate_limited": "#ef4444",
}
AI_TRIGGER_LABELS = {
    "mention": "Mentions",
    "reply": "Replies to bot",
    "unprompted": "Unprompted",
    "rate_limited": "Rate-limited",
}

STAT_CARD_STYLES = [
    ("border-indigo-500", "text-indigo-600", "bg-indigo-50"),
    ("border-emerald-500", "text-emerald-600", "bg-emerald-50"),
    ("border-amber-500", "text-amber-600", "bg-amber-50"),
    ("border-violet-500", "text-violet-600", "bg-violet-50"),
]

AI_CARD_STYLES = [
    ("border-indigo-400", "text-indigo-600"),
    ("border-purple-400", "text-purple-600"),
    ("border-cyan-400", "text-cyan-600"),
    ("border-red-400", "text-red-600"),
]


def _stat_card(value, label: str, idx: int, styles=STAT_CARD_STYLES) -> str:
    border, text, _ = styles[idx % len(styles)]
    return f'<div class="bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow-md p-5 text-center border-t-2 {border}"><div class="text-3xl font-bold {text} tracking-tight">{value}</div><div class="text-gray-500 text-xs font-medium uppercase tracking-wide mt-1">{label}</div></div>'


def _ai_stat_card(value, label: str, idx: int) -> str:
    border, text = AI_CARD_STYLES[idx % len(AI_CARD_STYLES)]
    return f'<div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5 text-center border-t-2 {border}"><div class="text-3xl font-bold {text} tracking-tight">{value}</div><div class="text-gray-500 text-xs font-medium uppercase tracking-wide mt-1">{label}</div></div>'


async def stats_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    total = stats.STATS.get("total", 0)
    cache_hits = stats.STATS.get("cache_hits", 0)
    by_platform = stats.STATS.get("by_platform", {})
    by_chat = stats.STATS.get("by_chat", {})

    platform_rows = "".join(
        f"<tr class='hover:bg-gray-50'><td class='px-4 py-2.5 border-b border-gray-100 text-sm text-gray-700'>{he(p)}</td><td class='px-4 py-2.5 border-b border-gray-100 text-sm font-medium text-gray-900'>{c}</td></tr>"
        for p, c in sorted(by_platform.items(), key=lambda kv: -kv[1])
    ) or "<tr><td colspan='2' class='px-4 py-10 text-center text-gray-400 text-sm'>No data yet</td></tr>"

    chat_rows = "".join(
        f"<tr class='hover:bg-gray-50'><td class='px-4 py-2.5 border-b border-gray-100 text-sm text-gray-700'>{he(str(d.get('title') or cid))}</td><td class='px-4 py-2.5 border-b border-gray-100 text-sm font-medium text-gray-900'>{d.get('total', 0)}</td><td class='px-4 py-2.5 border-b border-gray-100 text-sm text-gray-500'>{d.get('cache_hits', 0)}</td></tr>"
        for cid, d in sorted(by_chat.items(), key=lambda kv: -kv[1].get("total", 0))
    ) or "<tr><td colspan='3' class='px-4 py-10 text-center text-gray-400 text-sm'>No data yet</td></tr>"

    ai_stats = stats.AI_STATS
    ai_status = "ON" if ai.AI_ENABLED else "OFF"
    ai_action = "off" if ai.AI_ENABLED else "on"
    if ai.AI_ENABLED:
        ai_btn = f"<button class='inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg border border-red-200 text-red-600 bg-red-50 hover:bg-red-100'><span class='w-1.5 h-1.5 rounded-full bg-green-500'></span>AI: {ai_status} (turn {ai_action})</button>"
    else:
        ai_btn = f"<button class='inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg border border-gray-200 text-gray-600 bg-gray-50 hover:bg-gray-100'><span class='w-1.5 h-1.5 rounded-full bg-gray-400'></span>AI: {ai_status} (turn {ai_action})</button>"

    ai_by_chat = sorted(
        ai_stats.get("by_chat", {}).items(),
        key=lambda kv: -sum(kv[1].get(k, 0) for k in stats.AI_STAT_TRIGGERS),
    )
    def _trunc(s: str, n: int = 25) -> str:
        return s if len(s) <= n else s[:n] + "…"

    ai_chart_data = {
        "labels": [_trunc(str(d.get("title") or cid)) for cid, d in ai_by_chat],
        "datasets": [
            {
                "label": AI_TRIGGER_LABELS[trigger],
                "data": [d.get(trigger, 0) for _, d in ai_by_chat],
                "backgroundColor": AI_TRIGGER_COLORS[trigger],
                "borderRadius": 4,
                "barThickness": 28,
            }
            for trigger in stats.AI_STAT_TRIGGERS
        ],
    }
    ai_chart_height = max(200, len(ai_by_chat) * 48 + 80)
    # Escape "</" so a chat title containing "</script>" can't break out of
    # the inline <script> block this gets embedded in.
    ai_chart_json = json.dumps(ai_chart_data).replace("</", "<\\/")
    ai_totals = {k: sum(d.get(k, 0) for _, d in ai_by_chat) for k in stats.AI_STAT_TRIGGERS}
    ai_chart_section = (
        f"""<div class="bg-white rounded-xl border border-gray-100 shadow-sm mb-6">
  <div class="px-5 py-3.5 border-b border-gray-100 font-medium text-sm text-gray-700">AI activity by chat</div>
  <div class="p-5"><div style="height:{ai_chart_height}px"><canvas id="aiChart"></canvas></div></div>
</div>
<script>
Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
new Chart(document.getElementById('aiChart'), {{
  type: 'bar',
  data: {ai_chart_json},
  options: {{
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'bottom', labels: {{ usePointStyle: true, padding: 16, font: {{ size: 12 }} }} }} }},
    scales: {{
      x: {{ stacked: true, beginAtZero: true, ticks: {{ precision: 0 }}, grid: {{ color: '#f3f4f6' }} }},
      y: {{ stacked: true, grid: {{ display: false }}, ticks: {{ font: {{ size: 12 }} }} }}
    }}
  }}
}});
</script>"""
        if ai_by_chat else
        """<div class="bg-white rounded-xl border border-gray-100 shadow-sm mb-6"><div class="p-10 text-center text-gray-400 text-sm">No AI activity yet</div></div>"""
    )
    body = f"""
<div class="flex justify-between items-center mb-6">
  <h1 class="text-2xl font-bold text-gray-900 tracking-tight">Dashboard</h1>
  <form method="post" action="/admin/ai-toggle">{ai_btn}</form>
</div>
<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
  {_stat_card(total, "Videos sent", 0)}
  {_stat_card(cache_hits, "From cache", 1)}
  {_stat_card(len(stats.VIDEO_CACHE), "Cached links", 2)}
  {_stat_card(len(profiles.USER_PROFILES), "Profiles", 3)}
</div>
<div class="flex items-center gap-3 mb-4">
  <h2 class="text-lg font-semibold text-gray-900">AI activity</h2>
  <div class="h-px flex-1 bg-gray-200"></div>
</div>
<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
  {_ai_stat_card(ai_totals['mention'], "Mentions", 0)}
  {_ai_stat_card(ai_totals['reply'], "Replies to bot", 1)}
  {_ai_stat_card(ai_totals['unprompted'], "Unprompted", 2)}
  {_ai_stat_card(ai_totals['rate_limited'], "Rate-limited", 3)}
</div>
{ai_chart_section}
<p class="text-gray-400 text-xs mb-8">Profile summaries generated: {ai_stats.get('profile_update', 0)} (global)</p>
<div class="grid grid-cols-1 md:grid-cols-2 gap-5">
  <div class="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
    <div class="px-5 py-3.5 border-b border-gray-100 font-medium text-sm text-gray-700">By platform</div>
    <table class="w-full text-sm">
      <thead><tr class="bg-gray-50/80"><th class="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Platform</th><th class="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Count</th></tr></thead>
      <tbody>{platform_rows}</tbody>
    </table>
  </div>
  <div class="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
    <div class="px-5 py-3.5 border-b border-gray-100 font-medium text-sm text-gray-700">By chat</div>
    <table class="w-full text-sm">
      <thead><tr class="bg-gray-50/80"><th class="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Chat</th><th class="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Videos</th><th class="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Cache</th></tr></thead>
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
