from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import ai, chats
from tb_dlp.web.layout import auth, he, page


async def whitelist_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    msg = request.rel_url.query.get("msg", "")
    alert = f"<div class='bg-green-50 text-green-800 border border-green-200 rounded px-4 py-2 mb-3'>{he(msg)}</div>" if msg else ""
    rows = ""
    for chat_id in sorted(chats.ALLOWED_CHAT_IDS):
        name = he(chats.chat_name(chat_id))
        ai_on = chat_id not in ai.AI_DISABLED_CHATS
        ai_btn_class = "border-green-500 text-green-500 hover:bg-green-50" if ai_on else "border-gray-300 text-gray-500 hover:bg-gray-100"
        ai_label = "AI: ON" if ai_on else "AI: OFF"
        rows += (
            f"<tr><td class='px-4 py-3 border-b border-gray-100'>{name}</td><td class='px-4 py-3 border-b border-gray-100'><code class='text-sm bg-gray-100 px-1 rounded'>{chat_id}</code></td><td class='px-4 py-3 border-b border-gray-100'>"
            f"<form method='post' action='/admin/whitelist/ai-toggle' style='display:inline'>"
            f"<input type='hidden' name='chat_id' value='{chat_id}'>"
            f"<button class='px-3 py-1 text-sm border rounded {ai_btn_class}'>{ai_label}</button>"
            f"</form></td><td class='px-4 py-3 border-b border-gray-100'>"
            f"<form method='post' action='/admin/whitelist/remove' style='display:inline'>"
            f"<input type='hidden' name='chat_id' value='{chat_id}'>"
            f"<button class='text-red-600 hover:text-red-800 text-sm' onclick=\"return confirm('Remove {name}?')\">Remove</button>"
            f"</form></td></tr>"
        )
    unseen = {cid: n for cid, n in chats.CHAT_NAMES.items() if cid not in chats.ALLOWED_CHAT_IDS}
    known_options = "".join(
        f"<option value='{cid}'>{he(n)} ({cid})</option>"
        for cid, n in sorted(unseen.items(), key=lambda kv: kv[1])
    )
    body = f"""
<h4 class="text-xl font-semibold mb-3">Whitelist</h4>
{alert}
<div class="bg-white rounded-lg shadow overflow-hidden mb-4">
  <table class="w-full text-sm">
    <thead class="bg-gray-50"><tr><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Chat name</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Chat ID</th><th class="px-4 py-3"></th><th class="px-4 py-3"></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<div class="bg-white rounded-lg shadow">
  <div class="px-4 py-3 border-b border-gray-200 font-semibold">Add chat</div>
  <div class="p-4">
    <form method="post" action="/admin/whitelist/add" class="grid grid-cols-1 md:grid-cols-[2fr_auto_2fr_auto] gap-3 items-end">
      <div>
        <label class="block text-sm text-gray-600 mb-1">Known chats (seen but not whitelisted)</label>
        <select name="known_id" class="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option value="">— pick one —</option>
          {known_options}
        </select>
      </div>
      <div class="text-gray-500 text-sm pt-3">or</div>
      <div>
        <label class="block text-sm text-gray-600 mb-1">Enter chat ID manually</label>
        <input type="number" name="manual_id" class="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="-100...">
      </div>
      <div>
        <button type="submit" class="w-full bg-gray-900 text-white px-4 py-2 rounded text-sm hover:bg-gray-800">Add</button>
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
