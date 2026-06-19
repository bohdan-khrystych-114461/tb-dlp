from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import comebacks
from tb_dlp.web.layout import auth, he, page


async def phrases_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    msg = request.rel_url.query.get("msg", "")
    alert = f"<div class='bg-green-50 text-green-800 border border-green-200 rounded px-4 py-2 mb-3'>{he(msg)}</div>" if msg else ""
    rows = ""
    for i, phrase in enumerate(comebacks.COMEBACK_PHRASES):
        rows += (
            f"<tr><td class='px-4 py-3 border-b border-gray-100'><span class='text-sm'>{he(phrase)}</span></td>"
            f"<td class='px-4 py-3 border-b border-gray-100 whitespace-nowrap'>"
            f"<form method='post' action='/admin/phrases/remove' style='display:inline'>"
            f"<input type='hidden' name='index' value='{i}'>"
            f"<button class='text-red-600 hover:text-red-800 text-sm'>Remove</button>"
            f"</form></td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='2' class='px-4 py-6 text-center text-gray-500'>No phrases yet.</td></tr>"
    body = f"""
<h4 class="text-xl font-semibold mb-3">Comeback phrases <span class="bg-gray-500 text-white text-xs px-2 py-0.5 rounded-full ml-2">{len(comebacks.COMEBACK_PHRASES)}</span></h4>
{alert}
<div class="bg-white rounded-lg shadow overflow-hidden mb-4">
  <table class="w-full text-sm">
    <thead class="bg-gray-50"><tr><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Phrase</th><th class="px-4 py-3"></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<div class="bg-white rounded-lg shadow">
  <div class="px-4 py-3 border-b border-gray-200 font-semibold">Add phrase</div>
  <div class="p-4">
    <form method="post" action="/admin/phrases/add">
      <div class="mb-2">
        <textarea name="phrase" class="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" rows="2" required placeholder="e.g. сиди мовчи, доки дорослі говорять"></textarea>
      </div>
      <button class="bg-gray-900 text-white px-3 py-1 text-sm rounded hover:bg-gray-800">Add</button>
    </form>
    <div class="text-sm text-gray-500 mt-2">A few of these are shown to the AI as vocabulary it can draw from when clapping back at trolls/insults — adapted to context, not used verbatim every time.</div>
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
