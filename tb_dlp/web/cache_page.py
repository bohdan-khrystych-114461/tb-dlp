from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import stats
from tb_dlp.web.layout import auth, he, page


async def cache_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    msg = request.rel_url.query.get("msg", "")
    alert = f"<div class='alert alert-success py-2'>{he(msg)}</div>" if msg else ""
    rows = ""
    for url, file_id in list(stats.VIDEO_CACHE.items()):
        rows += (
            f"<tr>"
            f"<td><small><a href='{he(url)}' target='_blank' rel='noopener' class='text-break'>{he(url[:80] + ('…' if len(url) > 80 else ''))}</a></small><br>"
            f"<span class='text-muted' style='font-size:0.75rem'>{he(file_id[:24])}…</span></td>"
            f"<td class='text-nowrap'>"
            f"<form method='post' action='/admin/cache/remove' style='display:inline'>"
            f"<input type='hidden' name='url' value='{he(url)}'>"
            f"<button class='btn btn-sm btn-outline-danger'>Remove</button>"
            f"</form></td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='2' class='text-muted py-3 text-center'>Cache is empty.</td></tr>"
    body = f"""
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">Video cache <span class="badge bg-secondary">{len(stats.VIDEO_CACHE)}</span></h4>
  <form method="post" action="/admin/cache/clear" onsubmit="return confirm('Clear all {len(stats.VIDEO_CACHE)} cached entries?')">
    <button class="btn btn-danger btn-sm" {'disabled' if not stats.VIDEO_CACHE else ''}>Clear all</button>
  </form>
</div>
{alert}
<div class="card shadow-sm">
  <table class="table table-hover align-middle mb-0">
    <thead class="table-light"><tr><th>URL / file_id</th><th></th></tr></thead>
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
