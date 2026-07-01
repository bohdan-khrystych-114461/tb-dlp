import re
from urllib.parse import quote as urlquote

import httpx
from aiohttp import web as aio_web

from tb_dlp import bot_messages, chats, config
from tb_dlp.web.layout import auth, he, page

TELEGRAM_API = f"https://api.telegram.org/bot{config.BOT_TOKEN}"
_MSG_LINK_RE = re.compile(r"t\.me/c/(\d+)/(\d+)")

_ALERT_OK = "flex items-center gap-2 bg-emerald-50 text-emerald-700 border-l-4 border-emerald-500 rounded-r-lg px-4 py-2.5 text-sm mb-4"
_ALERT_ERR = "flex items-center gap-2 bg-red-50 text-red-700 border-l-4 border-red-500 rounded-r-lg px-4 py-2.5 text-sm mb-4"


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
        alert += f"<div class='{_ALERT_OK}'>{he(msg)}</div>"
    if error:
        alert += f"<div class='{_ALERT_ERR}'>{he(error)}</div>"
    chat_options = "".join(
        f"<option value='{cid}'>{he(chats.chat_name(cid))}</option>"
        for cid in sorted(chats.ALLOWED_CHAT_IDS)
    )
    body = f"""
<h1 class="text-2xl font-bold text-gray-900 tracking-tight mb-6">Messages</h1>
{alert}
<div class="bg-white rounded-xl border border-gray-100 shadow-sm mb-5">
  <div class="px-5 py-3.5 border-b border-gray-100 flex items-center gap-2">
    <svg class="w-4 h-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"/></svg>
    <span class="font-medium text-sm text-gray-700">Send a message</span>
  </div>
  <div class="p-5">
    <form method="post" action="/admin/messages/send" enctype="multipart/form-data">
      <div class="mb-3">
        <label class="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Chat</label>
        <select name="chat_id" class="w-full border border-gray-200 rounded-lg px-3.5 py-2.5 text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500">{chat_options}</select>
      </div>
      <div class="mb-3">
        <label class="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Text <span class="normal-case font-normal text-gray-400">(optional if image provided)</span></label>
        <textarea name="text" rows="3" class="w-full border border-gray-200 rounded-lg px-3.5 py-2.5 text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 placeholder-gray-400" placeholder="Message text..."></textarea>
      </div>
      <div class="mb-4">
        <label class="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Image <span class="normal-case font-normal text-gray-400">(optional — upload or paste)</span></label>
        <div id="paste-zone" class="border-2 border-dashed border-gray-200 rounded-lg p-4 text-center text-sm text-gray-400 cursor-pointer hover:border-indigo-300 hover:bg-indigo-50 transition-colors" onclick="document.getElementById('photo-input').click()">
          <div id="paste-hint">Click to choose or paste an image (Ctrl+V)</div>
          <img id="paste-preview" class="hidden mx-auto max-h-40 rounded mt-2">
        </div>
        <input id="photo-input" type="file" name="photo" accept="image/*" class="hidden" onchange="showPreview(this.files[0])">
      </div>
      <button class="bg-indigo-600 text-white px-3.5 py-1.5 text-sm font-medium rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">Send</button>
    </form>
    <script>
    function showPreview(file) {{
      if (!file) return;
      var img = document.getElementById('paste-preview');
      var hint = document.getElementById('paste-hint');
      img.src = URL.createObjectURL(file);
      img.classList.remove('hidden');
      hint.textContent = file.name || 'Pasted image';
    }}
    document.addEventListener('paste', function(e) {{
      var items = (e.clipboardData || e.originalEvent.clipboardData).items;
      for (var i = 0; i < items.length; i++) {{
        if (items[i].type.indexOf('image') !== -1) {{
          var blob = items[i].getAsFile();
          var dt = new DataTransfer();
          dt.items.add(new File([blob], 'pasted.png', {{type: blob.type}}));
          var input = document.getElementById('photo-input');
          input.files = dt.files;
          showPreview(dt.files[0]);
          break;
        }}
      }}
    }});
    </script>
  </div>
</div>
<div class="grid grid-cols-1 md:grid-cols-2 gap-5">
  <div class="bg-white rounded-xl border border-gray-100 shadow-sm">
    <div class="px-5 py-3.5 border-b border-gray-100 flex items-center gap-2">
      <svg class="w-4 h-4 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>
      <span class="font-medium text-sm text-gray-700">Delete a message</span>
    </div>
    <div class="p-5">
      <form method="post" action="/admin/messages/delete">
        <div class="mb-3">
          <label class="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Message link</label>
          <input type="text" name="link" class="w-full border border-gray-200 rounded-lg px-3.5 py-2.5 text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-400" placeholder="https://t.me/c/.../...">
        </div>
        <button class="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-sm font-medium rounded-lg border border-red-200 text-red-600 bg-red-50 hover:bg-red-100" onclick="return confirm('Delete this message?')">Delete</button>
      </form>
      <p class="text-xs text-gray-400 mt-3">Works on any message — the bot is an admin in the group.</p>
    </div>
  </div>
  <div class="bg-white rounded-xl border border-gray-100 shadow-sm">
    <div class="px-5 py-3.5 border-b border-gray-100 flex items-center gap-2">
      <svg class="w-4 h-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"/></svg>
      <span class="font-medium text-sm text-gray-700">Edit a message</span>
    </div>
    <div class="p-5">
      <form method="post" action="/admin/messages/edit">
        <div class="mb-3">
          <label class="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Message link</label>
          <input type="text" name="link" class="w-full border border-gray-200 rounded-lg px-3.5 py-2.5 text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-400" placeholder="https://t.me/c/.../...">
        </div>
        <div class="mb-3">
          <label class="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">New text</label>
          <textarea name="text" class="w-full border border-gray-200 rounded-lg px-3.5 py-2.5 text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-400" rows="4"></textarea>
        </div>
        <button class="bg-indigo-600 text-white px-3.5 py-1.5 text-sm font-medium rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">Save</button>
      </form>
      <p class="text-xs text-gray-400 mt-3">Only works on messages the bot itself sent.</p>
    </div>
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


async def messages_send(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    reader = await request.multipart()
    chat_id = None
    text = ""
    photo_bytes = None
    photo_name = "photo.jpg"
    async for field in reader:
        if field.name == "chat_id":
            chat_id = int(await field.read(decode=True))
        elif field.name == "text":
            text = (await field.read(decode=True)).strip()
        elif field.name == "photo" and field.filename:
            photo_bytes = await field.read()
            photo_name = field.filename or "photo.jpg"
    if not chat_id:
        return aio_web.HTTPFound(f"/admin/messages?error={urlquote('No chat selected.')}")
    if not text and not photo_bytes:
        return aio_web.HTTPFound(f"/admin/messages?error={urlquote('Provide text or an image.')}")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if photo_bytes:
                resp = await client.post(
                    f"{TELEGRAM_API}/sendPhoto",
                    data={"chat_id": chat_id, "caption": text},
                    files={"photo": (photo_name, photo_bytes)},
                )
            else:
                resp = await client.post(
                    f"{TELEGRAM_API}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description", "unknown error"))
    except Exception as exc:
        return aio_web.HTTPFound(f"/admin/messages?error={urlquote(f'Send failed: {exc}')}")
    return aio_web.HTTPFound(f"/admin/messages?msg={urlquote('Message sent.')}")
