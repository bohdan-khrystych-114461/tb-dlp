from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import comebacks
from tb_dlp.web.layout import auth, he, page


async def phrases_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    msg = request.rel_url.query.get("msg", "")
    alert = f"<div class='alert alert-success py-2'>{he(msg)}</div>" if msg else ""
    rows = ""
    for i, phrase in enumerate(comebacks.COMEBACK_PHRASES):
        rows += (
            f"<tr><td><small>{he(phrase)}</small></td>"
            f"<td class='text-nowrap'>"
            f"<form method='post' action='/admin/phrases/remove' style='display:inline'>"
            f"<input type='hidden' name='index' value='{i}'>"
            f"<button class='btn btn-sm btn-outline-danger'>Remove</button>"
            f"</form></td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='2' class='text-muted py-3 text-center'>No phrases yet.</td></tr>"
    body = f"""
<h4 class="mb-3">Comeback phrases <span class="badge bg-secondary">{len(comebacks.COMEBACK_PHRASES)}</span></h4>
{alert}
<div class="card shadow-sm mb-4">
  <table class="table table-hover align-middle mb-0">
    <thead class="table-light"><tr><th>Phrase</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<div class="card shadow-sm">
  <div class="card-header fw-semibold">Add phrase</div>
  <div class="card-body">
    <form method="post" action="/admin/phrases/add">
      <div class="mb-2">
        <textarea name="phrase" class="form-control form-control-sm" rows="2" required placeholder="e.g. сиди мовчи, доки дорослі говорять"></textarea>
      </div>
      <button class="btn btn-sm btn-dark">Add</button>
    </form>
    <div class="form-text">A few of these are shown to the AI as vocabulary it can draw from when clapping back at trolls/insults — adapted to context, not used verbatim every time.</div>
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
