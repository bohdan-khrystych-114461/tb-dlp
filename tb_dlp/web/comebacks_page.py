from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import comebacks
from tb_dlp.web.layout import auth, he, page


async def comebacks_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    msg = request.rel_url.query.get("msg", "")
    alert = f"<div class='alert alert-success py-2'>{he(msg)}</div>" if msg else ""
    rows = ""
    for i, ex in enumerate(comebacks.COMEBACK_EXAMPLES):
        rows += (
            f"<tr><td><small>{he(ex['trigger'])}</small></td>"
            f"<td><small>{he(ex['reply'])}</small></td>"
            f"<td class='text-nowrap'>"
            f"<form method='post' action='/admin/comebacks/remove' style='display:inline'>"
            f"<input type='hidden' name='index' value='{i}'>"
            f"<button class='btn btn-sm btn-outline-danger'>Remove</button>"
            f"</form></td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='3' class='text-muted py-3 text-center'>No examples yet.</td></tr>"
    body = f"""
<h4 class="mb-3">Comeback examples <span class="badge bg-secondary">{len(comebacks.COMEBACK_EXAMPLES)}</span></h4>
{alert}
<div class="card shadow-sm mb-4">
  <table class="table table-hover align-middle mb-0">
    <thead class="table-light"><tr><th>Their message</th><th>Bot's reply</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<div class="card shadow-sm">
  <div class="card-header fw-semibold">Add example</div>
  <div class="card-body">
    <form method="post" action="/admin/comebacks/add">
      <div class="mb-2">
        <label class="form-label small">Their message (the troll/insult)</label>
        <textarea name="trigger" class="form-control form-control-sm" rows="2" required></textarea>
      </div>
      <div class="mb-2">
        <label class="form-label small">Ideal comeback</label>
        <textarea name="reply" class="form-control form-control-sm" rows="2" required></textarea>
      </div>
      <button class="btn btn-sm btn-dark">Add</button>
    </form>
    <div class="form-text">A few of these are shown to the AI as style examples whenever someone trolls/insults the bot.</div>
  </div>
</div>"""
    return aio_web.Response(text=page("Comebacks", body, active="comebacks"), content_type="text/html")


async def comebacks_add(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    trigger = form.get("trigger", "").strip()
    reply = form.get("reply", "").strip()
    if trigger and reply:
        comebacks.COMEBACK_EXAMPLES.append({"trigger": trigger, "reply": reply})
        comebacks.save_examples()
        return aio_web.HTTPFound(f"/admin/comebacks?msg={urlquote('Example added.')}")
    return aio_web.HTTPFound("/admin/comebacks")


async def comebacks_remove(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    try:
        index = int(form.get("index", ""))
        comebacks.COMEBACK_EXAMPLES.pop(index)
    except (ValueError, IndexError):
        return aio_web.HTTPFound("/admin/comebacks")
    comebacks.save_examples()
    return aio_web.HTTPFound(f"/admin/comebacks?msg={urlquote('Example removed.')}")
