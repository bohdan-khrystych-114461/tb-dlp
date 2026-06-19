from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import ai, chats
from tb_dlp.web.layout import auth, he, page

_ALERT_OK = "flex items-center gap-2 bg-emerald-50 text-emerald-700 border-l-4 border-emerald-500 rounded-r-lg px-4 py-2.5 text-sm mb-4"


async def whitelist_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    msg = request.rel_url.query.get("msg", "")
    alert = f"<div class='{_ALERT_OK}'>{he(msg)}</div>" if msg else ""
    rows = ""
    for chat_id in sorted(chats.ALLOWED_CHAT_IDS):
        name = he(chats.chat_name(chat_id))
        ai_on = chat_id not in ai.AI_DISABLED_CHATS
        if ai_on:
            ai_btn = f"<button class='inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md border border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100'><span class='w-1.5 h-1.5 rounded-full bg-emerald-500'></span>AI ON</button>"
        else:
            ai_btn = f"<button class='inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md border border-gray-200 text-gray-500 bg-gray-50 hover:bg-gray-100'><span class='w-1.5 h-1.5 rounded-full bg-gray-400'></span>AI OFF</button>"
        rows += (
            f"<tr class='hover:bg-gray-50'><td class='px-4 py-3 border-b border-gray-100 font-medium text-gray-900'>{name}</td><td class='px-4 py-3 border-b border-gray-100'><code class='text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded'>{chat_id}</code></td><td class='px-4 py-3 border-b border-gray-100'>"
            f"<form method='post' action='/admin/whitelist/ai-toggle' style='display:inline'>"
            f"<input type='hidden' name='chat_id' value='{chat_id}'>"
            f"{ai_btn}"
            f"</form></td><td class='px-4 py-3 border-b border-gray-100'>"
            f"<form method='post' action='/admin/whitelist/remove' style='display:inline'>"
            f"<input type='hidden' name='chat_id' value='{chat_id}'>"
            f"<button class='text-red-500 hover:text-red-700 text-xs font-medium' onclick=\"return confirm('Remove {name}?')\">Remove</button>"
            f"</form></td></tr>"
        )
    unseen = {cid: n for cid, n in chats.CHAT_NAMES.items() if cid not in chats.ALLOWED_CHAT_IDS}
    known_options = "".join(
        f"<option value='{cid}'>{he(n)} ({cid})</option>"
        for cid, n in sorted(unseen.items(), key=lambda kv: kv[1])
    )
    body = f"""
<h1 class="text-2xl font-bold text-gray-900 tracking-tight mb-6">Whitelist</h1>
{alert}
<div class="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden mb-6">
  <table class="w-full text-sm">
    <thead><tr class="bg-gray-50/80"><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Chat name</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Chat ID</th><th class="px-4 py-3"></th><th class="px-4 py-3 w-16"></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<div class="bg-white rounded-xl border border-gray-100 shadow-sm">
  <div class="px-5 py-3.5 border-b border-gray-100 font-medium text-sm text-gray-700">Add chat</div>
  <div class="p-5">
    <form method="post" action="/admin/whitelist/add" class="grid grid-cols-1 md:grid-cols-[2fr_auto_2fr_auto] gap-4 items-end">
      <div>
        <label class="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Known chats</label>
        <select name="known_id" class="w-full border border-gray-200 rounded-lg px-3.5 py-2.5 text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent">
          <option value="">— pick one —</option>
          {known_options}
        </select>
      </div>
      <div class="text-gray-400 text-xs font-medium pt-4">or</div>
      <div>
        <label class="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Chat ID</label>
        <input type="number" name="manual_id" class="w-full border border-gray-200 rounded-lg px-3.5 py-2.5 text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-400" placeholder="-100...">
      </div>
      <div>
        <button type="submit" class="w-full bg-indigo-600 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">Add</button>
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
