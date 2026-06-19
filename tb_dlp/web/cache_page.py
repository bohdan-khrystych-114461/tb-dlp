from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import stats
from tb_dlp.web.layout import auth, he, page

_ALERT_OK = "flex items-center gap-2 bg-emerald-50 text-emerald-700 border-l-4 border-emerald-500 rounded-r-lg px-4 py-2.5 text-sm mb-4"


async def cache_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    msg = request.rel_url.query.get("msg", "")
    alert = f"<div class='{_ALERT_OK}'>{he(msg)}</div>" if msg else ""
    rows = ""
    for url, file_id in list(stats.VIDEO_CACHE.items()):
        rows += (
            f"<tr class='hover:bg-gray-50'>"
            f"<td class='px-4 py-3 border-b border-gray-100 w-8'><input type='checkbox' name='urls' value='{he(url)}' class='cache-cb rounded border-gray-300 text-indigo-600 focus:ring-indigo-500'></td>"
            f"<td class='px-4 py-3 border-b border-gray-100'><a href='{he(url)}' target='_blank' rel='noopener' class='text-indigo-600 hover:text-indigo-800 text-sm break-all'>{he(url[:80] + ('…' if len(url) > 80 else ''))}</a><br>"
            f"<span class='text-gray-400 text-xs font-mono'>{he(file_id[:24])}…</span></td>"
            f"<td class='px-4 py-3 border-b border-gray-100 whitespace-nowrap'>"
            f"<form method='post' action='/admin/cache/remove' style='display:inline'>"
            f"<input type='hidden' name='url' value='{he(url)}'>"
            f"<button class='text-red-500 hover:text-red-700 text-xs font-medium'>Remove</button>"
            f"</form></td></tr>"
        )
    if not rows:
        rows = """<tr><td colspan='3' class='px-4 py-12 text-center'>
<svg class="w-10 h-10 text-gray-300 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m6 4.125l2.25 2.25m0 0l2.25 2.25M12 13.875l2.25-2.25M12 13.875l-2.25 2.25M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z"/></svg>
<p class="text-gray-400 text-sm">Cache is empty</p></td></tr>"""
    body = f"""
<div class="flex justify-between items-center mb-6">
  <div class="flex items-center gap-3">
    <h1 class="text-2xl font-bold text-gray-900 tracking-tight">Video cache</h1>
    <span class="bg-gray-100 text-gray-600 text-xs font-medium px-2.5 py-1 rounded-full">{len(stats.VIDEO_CACHE)}</span>
  </div>
  <form method="post" action="/admin/cache/clear" onsubmit="return confirm('Clear all {len(stats.VIDEO_CACHE)} cached entries?')">
    <button class="inline-flex items-center gap-1.5 bg-red-600 text-white px-3.5 py-1.5 rounded-lg text-sm font-medium hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500" {'disabled' if not stats.VIDEO_CACHE else ''}>
      <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
      Clear all
    </button>
  </form>
</div>
{alert}
<div class="flex items-center gap-3 mb-3">
  <input id="cacheFilter" type="text" placeholder="Filter URLs…" class="w-full max-w-xs border border-gray-200 rounded-lg px-3.5 py-2 text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-400">
  <button type="button" id="bulkRemoveBtn" onclick="document.getElementById('bulkForm').submit()" class="hidden inline-flex items-center gap-1.5 bg-red-600 text-white px-3 py-2 rounded-lg text-xs font-medium hover:bg-red-700">Remove selected (<span id="selCount">0</span>)</button>
</div>
<form id="bulkForm" method="post" action="/admin/cache/bulk-remove">
<div class="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
  <table class="w-full text-sm" id="cacheTable">
    <thead><tr class="bg-gray-50/80"><th class="px-4 py-3 w-8"><input type="checkbox" id="selectAll" class="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"></th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">URL / file_id</th><th class="px-4 py-3 w-16"></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
</form>
<script>
document.getElementById('cacheFilter').addEventListener('input', function() {{
  var q = this.value.toLowerCase();
  document.querySelectorAll('#cacheTable tbody tr').forEach(function(r) {{
    r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}});
(function() {{
  var sa = document.getElementById('selectAll');
  var btn = document.getElementById('bulkRemoveBtn');
  var cnt = document.getElementById('selCount');
  function upd() {{
    var n = document.querySelectorAll('.cache-cb:checked').length;
    cnt.textContent = n;
    btn.classList.toggle('hidden', n === 0);
  }}
  if (sa) {{
    sa.addEventListener('change', function() {{
      document.querySelectorAll('.cache-cb').forEach(function(c) {{ c.checked = sa.checked; }});
      upd();
    }});
  }}
  document.querySelectorAll('.cache-cb').forEach(function(c) {{ c.addEventListener('change', upd); }});
}})();
</script>"""
    return aio_web.Response(text=page("Cache", body, active="cache"), content_type="text/html")


async def cache_remove(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    url = form.get("url", "").strip()
    if url and url in stats.VIDEO_CACHE:
        stats.VIDEO_CACHE.pop(url)
        stats.save_video_cache()
        return aio_web.HTTPFound(f"/admin/cache?msg={urlquote('Removed: ' + url[:60])}")
    return aio_web.HTTPFound("/admin/cache")


async def cache_bulk_remove(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    urls = form.getall("urls", [])
    removed = 0
    for url in urls:
        if url in stats.VIDEO_CACHE:
            stats.VIDEO_CACHE.pop(url)
            removed += 1
    if removed:
        stats.save_video_cache()
    return aio_web.HTTPFound(f"/admin/cache?msg={urlquote(f'Removed {removed} entries.')}")


async def cache_clear(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    count = len(stats.VIDEO_CACHE)
    stats.VIDEO_CACHE.clear()
    stats.save_video_cache()
    return aio_web.HTTPFound(f"/admin/cache?msg={urlquote(f'Cleared {count} entries.')}")
