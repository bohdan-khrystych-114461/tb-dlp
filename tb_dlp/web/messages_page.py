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
        alert += f"<div class='bg-green-50 text-green-800 border border-green-200 rounded px-4 py-2 mb-3'>{he(msg)}</div>"
    if error:
        alert += f"<div class='bg-red-50 text-red-800 border border-red-200 rounded px-4 py-2 mb-3'>{he(error)}</div>"
    body = f"""
<h4 class="text-xl font-semibold mb-3">Messages</h4>
{alert}
<div class="bg-white rounded-lg shadow mb-4">
  <div class="px-4 py-3 border-b border-gray-200 font-semibold">Delete a message</div>
  <div class="p-4">
    <form method="post" action="/admin/messages/delete">
      <div class="mb-2">
        <label class="block text-sm text-gray-600 mb-1">Telegram message link</label>
        <input type="text" name="link" class="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="https://t.me/c/.../...">
      </div>
      <button class="px-3 py-1 text-sm border border-red-500 text-red-500 rounded hover:bg-red-50" onclick="return confirm('Delete this message?')">Delete</button>
    </form>
    <div class="text-sm text-gray-500 mt-2">Works on any message — the bot is an admin in the group.</div>
  </div>
</div>
<div class="bg-white rounded-lg shadow">
  <div class="px-4 py-3 border-b border-gray-200 font-semibold">Edit a message</div>
  <div class="p-4">
    <form method="post" action="/admin/messages/edit">
      <div class="mb-2">
        <label class="block text-sm text-gray-600 mb-1">Telegram message link</label>
        <input type="text" name="link" class="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="https://t.me/c/.../...">
      </div>
      <div class="mb-2">
        <label class="block text-sm text-gray-600 mb-1">New text</label>
        <textarea name="text" class="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" rows="4"></textarea>
      </div>
      <button class="bg-gray-900 text-white px-3 py-1 text-sm rounded hover:bg-gray-800">Save</button>
    </form>
    <div class="text-sm text-gray-500 mt-2">Telegram only allows editing messages the bot itself sent.</div>
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
