from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import comebacks
from tb_dlp.web.layout import auth, he, page

_ALERT_OK = "flex items-center gap-2 bg-emerald-50 text-emerald-700 border-l-4 border-emerald-500 rounded-r-lg px-4 py-2.5 text-sm mb-4"


async def phrases_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    msg = request.rel_url.query.get("msg", "")
    alert = f"<div class='{_ALERT_OK}'>{he(msg)}</div>" if msg else ""
    rows = ""
    for i, phrase in enumerate(comebacks.COMEBACK_PHRASES):
        rows += (
            f"<tr class='hover:bg-gray-50'><td class='px-4 py-3 border-b border-gray-100 text-sm text-gray-700'>{he(phrase)}</td>"
            f"<td class='px-4 py-3 border-b border-gray-100 whitespace-nowrap'>"
            f"<form method='post' action='/admin/phrases/remove' style='display:inline'>"
            f"<input type='hidden' name='index' value='{i}'>"
            f"<button class='text-red-500 hover:text-red-700 text-xs font-medium'>Remove</button>"
            f"</form></td></tr>"
        )
    if not rows:
        rows = """<tr><td colspan='2' class='px-4 py-12 text-center'>
<svg class="w-10 h-10 text-gray-300 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"/></svg>
<p class="text-gray-400 text-sm">No phrases yet</p></td></tr>"""
    body = f"""
<div class="flex items-center gap-3 mb-6">
  <h1 class="text-2xl font-bold text-gray-900 tracking-tight">Comeback phrases</h1>
  <span class="bg-gray-100 text-gray-600 text-xs font-medium px-2.5 py-1 rounded-full">{len(comebacks.COMEBACK_PHRASES)}</span>
</div>
{alert}
<div class="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden mb-6">
  <table class="w-full text-sm">
    <thead><tr class="bg-gray-50/80"><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Phrase</th><th class="px-4 py-3 w-16"></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<div class="bg-white rounded-xl border border-gray-100 shadow-sm">
  <div class="px-5 py-3.5 border-b border-gray-100 font-medium text-sm text-gray-700">Add phrase</div>
  <div class="p-5">
    <form method="post" action="/admin/phrases/add">
      <div class="mb-3">
        <textarea name="phrase" class="w-full border border-gray-200 rounded-lg px-3.5 py-2.5 text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-400" rows="2" required placeholder="e.g. сиди мовчи, доки дорослі говорять"></textarea>
      </div>
      <button class="bg-indigo-600 text-white px-3.5 py-1.5 text-sm font-medium rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">Add</button>
    </form>
    <p class="text-xs text-gray-400 mt-3">Vocabulary the AI can draw from when clapping back — adapted to context, not used verbatim.</p>
  </div>
</div>"""
    return aio_web.Response(text=page("Phrases", body, active="phrases"), content_type="text/html")


async def phrases_add(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    phrase = form.get("phrase", "").strip()
    if phrase:
        comebacks.COMEBACK_PHRASES.append(phrase)
        comebacks.save_phrases()
        return aio_web.HTTPFound(f"/admin/phrases?msg={urlquote('Phrase added.')}")
    return aio_web.HTTPFound("/admin/phrases")


async def phrases_remove(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    try:
        index = int(form.get("index", ""))
        comebacks.COMEBACK_PHRASES.pop(index)
    except (ValueError, IndexError):
        return aio_web.HTTPFound("/admin/phrases")
    comebacks.save_phrases()
    return aio_web.HTTPFound(f"/admin/phrases?msg={urlquote('Phrase removed.')}")
