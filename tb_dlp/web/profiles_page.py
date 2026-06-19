import asyncio
from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import profiles
from tb_dlp.web.layout import auth, he, page


async def profiles_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    saved = request.rel_url.query.get("saved", "")
    alert = f"<div class='bg-green-50 text-green-800 border border-green-200 rounded px-4 py-2 mb-3'>{he(saved)} saved.</div>" if saved else ""
    rows = ""
    for uid, data in profiles.USER_PROFILES.items():
        name = he(data.get("name", uid))
        username = f"@{he(data['username'])}" if data.get("username") else "—"
        notes = he(data.get("notes", ""))
        buf = len(profiles.USER_MESSAGE_BUFFERS.get(int(uid), []))
        rows += f"""<tr>
  <td class="px-4 py-3 border-b border-gray-100">{name}<br><span class="text-gray-500 text-sm">{username}</span></td>
  <td class="px-4 py-3 border-b border-gray-100"><span class="text-sm">{notes}</span></td>
  <td class="px-4 py-3 border-b border-gray-100 text-center"><span class="text-sm {'text-green-600' if buf >= profiles.PROFILE_UPDATE_THRESHOLD else ''}">{buf}/{profiles.PROFILE_UPDATE_THRESHOLD}</span></td>
  <td class="px-4 py-3 border-b border-gray-100"><a href="/admin/profiles/{he(uid)}/edit" class="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-100">Edit</a></td>
</tr>"""
    if not rows:
        rows = "<tr><td colspan='4' class='px-4 py-6 text-center text-gray-500'>No profiles yet — need 25+ messages per person.</td></tr>"
    body = f"""
<h4 class="text-xl font-semibold mb-3">Member profiles</h4>
{alert}
<div class="bg-white rounded-lg shadow overflow-hidden">
  <table class="w-full text-sm">
    <thead class="bg-gray-50"><tr><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Member</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Notes</th><th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Buffer</th><th class="px-4 py-3"></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
    return aio_web.Response(text=page("Profiles", body, active="profiles"), content_type="text/html")


async def edit_get(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    uid = request.match_info["user_id"]
    data = profiles.USER_PROFILES.get(uid)
    if not data:
        return aio_web.HTTPFound("/admin/profiles")
    name = he(data.get("name", uid))
    username = f"@{he(data['username'])}" if data.get("username") else ""
    real_name = he(data.get("real_name", ""))
    notes = he(data.get("notes", ""))
    buf = len(profiles.USER_MESSAGE_BUFFERS.get(int(uid), []))
    body = f"""
<div class="max-w-2xl mx-auto">
  <a href="/admin/profiles" class="text-gray-500 hover:text-gray-700">&larr; Back to profiles</a>
  <h4 class="text-xl font-semibold mt-3">{name} <span class="text-gray-500 text-sm">{username}</span></h4>
  <p class="text-gray-500 text-sm mb-3">Buffer: {buf}/{profiles.PROFILE_UPDATE_THRESHOLD} messages until next auto-refresh</p>
  <div class="bg-white rounded-lg shadow p-6">
    <form method="post">
      <div class="mb-4">
        <label class="block font-semibold mb-1">Real name</label>
        <input name="real_name" class="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" value="{real_name}" placeholder="e.g. Ваня Петренко">
        <div class="text-sm text-gray-500 mt-1">The person's real name — AI will know who they actually are.</div>
      </div>
      <div class="mb-4">
        <label class="block font-semibold mb-1">Notes</label>
        <textarea name="notes" class="w-full border border-gray-300 rounded px-3 py-2 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500" rows="6">{notes}</textarea>
        <div class="text-sm text-gray-500 mt-1">This is what the AI uses to tailor replies to this person.</div>
      </div>
      <div class="flex gap-2 flex-wrap">
        <button type="submit" class="bg-gray-900 text-white px-4 py-2 rounded hover:bg-gray-800">Save</button>
        <a href="/admin/profiles" class="px-4 py-2 border border-gray-300 rounded hover:bg-gray-100">Cancel</a>
      </div>
    </form>
    <hr class="my-4 border-gray-200">
    <form method="post" action="/admin/profiles/{he(uid)}/refresh">
      <button type="submit" class="px-3 py-1 text-sm border border-blue-500 text-blue-500 rounded hover:bg-blue-50" {'disabled' if buf == 0 else ''}>
        Refresh profile now ({buf} buffered messages)
      </button>
      {"<div class='text-sm text-yellow-600 mt-1'>No buffered messages to summarize yet.</div>" if buf == 0 else ""}
    </form>
  </div>
</div>"""
    return aio_web.Response(text=page(f"Edit — {data.get('name', uid)}", body, active="profiles"), content_type="text/html")


async def edit_post(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    uid = request.match_info["user_id"]
    data = profiles.USER_PROFILES.get(uid)
    if not data:
        return aio_web.HTTPFound("/admin/profiles")
    form = await request.post()
    new_notes = form.get("notes", "").strip()
    new_real_name = form.get("real_name", "").strip()
    data["real_name"] = new_real_name
    if new_notes:
        data["notes"] = new_notes
    profiles.USER_PROFILES[uid] = data
    profiles.save_profiles()
    return aio_web.HTTPFound(f"/admin/profiles?saved={urlquote(data.get('name', uid))}")


async def refresh_profile(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    uid = request.match_info["user_id"]
    data = profiles.USER_PROFILES.get(uid)
    if not data:
        return aio_web.HTTPFound("/admin/profiles")
    buf = profiles.USER_MESSAGE_BUFFERS.get(int(uid), [])
    if not buf:
        return aio_web.HTTPFound(f"/admin/profiles/{uid}/edit")
    asyncio.create_task(profiles.update_profile(int(uid), data["name"], data.get("username"), force=True))
    return aio_web.HTTPFound(f"/admin/profiles?saved={urlquote(data.get('name', uid))}")
