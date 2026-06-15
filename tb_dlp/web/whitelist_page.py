from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import ai, chats
from tb_dlp.web.layout import auth, he, page


async def whitelist_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    msg = request.rel_url.query.get("msg", "")
    alert = f"<div class='alert alert-success py-2'>{he(msg)}</div>" if msg else ""
    rows = ""
    for chat_id in sorted(chats.ALLOWED_CHAT_IDS):
        name = he(chats.chat_name(chat_id))
        ai_on = chat_id not in ai.AI_DISABLED_CHATS
        ai_btn_class = "btn-outline-success" if ai_on else "btn-outline-secondary"
        ai_label = "AI: ON" if ai_on else "AI: OFF"
        rows += (
            f"<tr><td>{name}</td><td><code>{chat_id}</code></td><td>"
            f"<form method='post' action='/admin/whitelist/ai-toggle' style='display:inline'>"
            f"<input type='hidden' name='chat_id' value='{chat_id}'>"
            f"<button class='btn btn-sm {ai_btn_class}'>{ai_label}</button>"
            f"</form></td><td>"
            f"<form method='post' action='/admin/whitelist/remove' style='display:inline'>"
            f"<input type='hidden' name='chat_id' value='{chat_id}'>"
            f"<button class='btn btn-sm btn-outline-danger' onclick=\"return confirm('Remove {name}?')\">Remove</button>"
            f"</form></td></tr>"
        )
    unseen = {cid: n for cid, n in chats.CHAT_NAMES.items() if cid not in chats.ALLOWED_CHAT_IDS}
    known_options = "".join(
        f"<option value='{cid}'>{he(n)} ({cid})</option>"
        for cid, n in sorted(unseen.items(), key=lambda kv: kv[1])
    )
    body = f"""
<h4 class="mb-3">Whitelist</h4>
{alert}
<div class="card shadow-sm mb-4">
  <table class="table table-hover align-middle mb-0">
    <thead class="table-light"><tr><th>Chat name</th><th>Chat ID</th><th></th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<div class="card shadow-sm">
  <div class="card-header fw-semibold">Add chat</div>
  <div class="card-body">
    <form method="post" action="/admin/whitelist/add" class="row g-2 align-items-end">
      <div class="col-md-5">
        <label class="form-label small">Known chats (seen but not whitelisted)</label>
        <select name="known_id" class="form-select form-select-sm">
          <option value="">— pick one —</option>
          {known_options}
        </select>
      </div>
      <div class="col-auto pt-3 text-muted small">or</div>
      <div class="col-md-4">
        <label class="form-label small">Enter chat ID manually</label>
        <input type="number" name="manual_id" class="form-control form-control-sm" placeholder="-100...">
      </div>
      <div class="col-md-2">
        <button type="submit" class="btn btn-dark btn-sm w-100">Add</button>
      </div>
    </form>
  </div>
</div>"""
    return aio_web.Response(text=page("Whitelist", body, active="whitelist"), content_type="text/html")


async def whitelist_add(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    raw = (form.get("known_id") or form.get("manual_id", "")).strip()
    try:
        chat_id = int(raw)
    except (ValueError, TypeError):
        return aio_web.HTTPFound("/admin/whitelist?msg=Invalid+chat+ID")
    chats.ALLOWED_CHAT_IDS.add(chat_id)
    chats.save_whitelist()
    name = chats.chat_name(chat_id)
    return aio_web.HTTPFound(f"/admin/whitelist?msg={urlquote(f'Added: {name}')}")


async def ai_toggle_chat(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    try:
        chat_id = int(form.get("chat_id", ""))
    except (ValueError, TypeError):
        return aio_web.HTTPFound("/admin/whitelist")
    ai.toggle_ai_enabled_for_chat(chat_id)
    return aio_web.HTTPFound("/admin/whitelist")


async def whitelist_remove(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    try:
        chat_id = int(form.get("chat_id", ""))
    except (ValueError, TypeError):
        return aio_web.HTTPFound("/admin/whitelist")
    chats.ALLOWED_CHAT_IDS.discard(chat_id)
    chats.save_whitelist()
    name = chats.chat_name(chat_id)
    return aio_web.HTTPFound(f"/admin/whitelist?msg={urlquote(f'Removed: {name}')}")
