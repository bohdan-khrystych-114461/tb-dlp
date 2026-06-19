from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import stats
from tb_dlp.web.layout import auth, he, page


async def cache_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    msg = request.rel_url.query.get("msg", "")
    alert = f"<div class='bg-green-50 text-green-800 border border-green-200 rounded px-4 py-2 mb-3'>{he(msg)}</div>" if msg else ""
    rows = ""
    for url, file_id in list(stats.VIDEO_CACHE.items()):
        rows += (
            f"<tr>"
            f"<td class='px-4 py-3 border-b border-gray-100'><a href='{he(url)}' target='_blank' rel='noopener' class='text-blue-600 hover:underline text-sm break-all'>{he(url[:80] + ('…' if len(url) > 80 else ''))}</a><br>"
            f"<span class='text-gray-400 text-xs'>{he(file_id[:24])}…</span></td>"
            f"<td class='px-4 py-3 border-b border-gray-100 whitespace-nowrap'>"
            f"<form method='post' action='/admin/cache/remove' style='display:inline'>"
            f"<input type='hidden' name='url' value='{he(url)}'>"
            f"<button class='text-red-600 hover:text-red-800 text-sm'>Remove</button>"
            f"</form></td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='2' class='px-4 py-6 text-center text-gray-500'>Cache is empty.</td></tr>"
    body = f"""
<div class="flex justify-between items-center mb-3">
  <h4 class="text-xl font-semibold">Video cache <span class="bg-gray-500 text-white text-xs px-2 py-0.5 rounded-full ml-2">{len(stats.VIDEO_CACHE)}</span></h4>
  <form method="post" action="/admin/cache/clear" onsubmit="return confirm('Clear all {len(stats.VIDEO_CACHE)} cached entries?')">
    <button class="bg-red-600 text-white px-3 py-1 rounded text-sm hover:bg-red-700" {'disabled' if not stats.VIDEO_CACHE else ''}>Clear all</button>
  </form>
</div>
{alert}
<div class="bg-white rounded-lg shadow overflow-hidden">
  <table class="w-full text-sm">
    <thead class="bg-gray-50"><tr><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">URL / file_id</th><th class="px-4 py-3"></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
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


async def cache_clear(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    count = len(stats.VIDEO_CACHE)
    stats.VIDEO_CACHE.clear()
    stats.save_video_cache()
    return aio_web.HTTPFound(f"/admin/cache?msg={urlquote(f'Cleared {count} entries.')}")
