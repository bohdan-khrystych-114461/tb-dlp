import re
from urllib.parse import quote as urlquote

import httpx
from aiohttp import web as aio_web

from tb_dlp import bot_messages, config
from tb_dlp.web.layout import auth, he, page

TELEGRAM_API = f"https://api.telegram.org/bot{config.BOT_TOKEN}"
_MSG_LINK_RE = re.compile(r"t\.me/c/(\d+)/(\d+)")


def _parse_message_link(link: str) -> tuple[int, int] | None:
    m = _MSG_LINK_RE.search(link.strip())
    if not m:
        return None
    internal_id, message_id = m.groups()
    return int(f"-100{internal_id}"), int(message_id)


async def _tg_call(method: str, **params) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{TELEGRAM_API}/{method}", json=params)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "unknown error"))


async def messages_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    msg = request.rel_url.query.get("msg", "")
    error = request.rel_url.query.get("error", "")
    alert = ""
    if msg:
        alert += f"<div class='alert alert-success py-2'>{he(msg)}</div>"
    if error:
        alert += f"<div class='alert alert-danger py-2'>{he(error)}</div>"
    body = f"""
<h4 class="mb-3">Messages</h4>
{alert}
<div class="card shadow-sm mb-4">
  <div class="card-header fw-semibold">Delete a message</div>
  <div class="card-body">
    <form method="post" action="/admin/messages/delete">
      <div class="mb-2">
        <label class="form-label small">Telegram message link</label>
        <input type="text" name="link" class="form-control form-control-sm" placeholder="https://t.me/c/.../...">
      </div>
      <button class="btn btn-sm btn-outline-danger" onclick="return confirm('Delete this message?')">Delete</button>
    </form>
    <div class="form-text">Works on any message — the bot is an admin in the group.</div>
  </div>
</div>
<div class="card shadow-sm">
  <div class="card-header fw-semibold">Edit a message</div>
  <div class="card-body">
    <form method="post" action="/admin/messages/edit">
      <div class="mb-2">
        <label class="form-label small">Telegram message link</label>
        <input type="text" name="link" class="form-control form-control-sm" placeholder="https://t.me/c/.../...">
      </div>
      <div class="mb-2">
        <label class="form-label small">New text</label>
        <textarea name="text" class="form-control form-control-sm" rows="4"></textarea>
      </div>
      <button class="btn btn-sm btn-dark">Save</button>
    </form>
    <div class="form-text">Telegram only allows editing messages the bot itself sent.</div>
  </div>
</div>"""
    return aio_web.Response(text=page("Messages", body, active="messages"), content_type="text/html")


async def messages_delete(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    parsed = _parse_message_link(form.get("link", ""))
    if not parsed:
        return aio_web.HTTPFound(f"/admin/messages?error={urlquote('Invalid message link.')}")
    chat_id, message_id = parsed
    try:
        await _tg_call("deleteMessage", chat_id=chat_id, message_id=message_id)
    except Exception as exc:
        return aio_web.HTTPFound(f"/admin/messages?error={urlquote(f'Delete failed: {exc}')}")
    bot_messages.BOT_MESSAGE_IDS.discard((chat_id, message_id))
    bot_messages.save()
    return aio_web.HTTPFound(f"/admin/messages?msg={urlquote(f'Deleted message {message_id}.')}")


async def messages_edit(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    form = await request.post()
    parsed = _parse_message_link(form.get("link", ""))
    text = form.get("text", "").strip()
    if not parsed:
        return aio_web.HTTPFound(f"/admin/messages?error={urlquote('Invalid message link.')}")
    if not text:
        return aio_web.HTTPFound(f"/admin/messages?error={urlquote('New text cannot be empty.')}")
    chat_id, message_id = parsed
    try:
        await _tg_call("editMessageText", chat_id=chat_id, message_id=message_id, text=text)
    except Exception as exc:
        return aio_web.HTTPFound(f"/admin/messages?error={urlquote(f'Edit failed: {exc}')}")
    return aio_web.HTTPFound(f"/admin/messages?msg={urlquote(f'Edited message {message_id}.')}")
