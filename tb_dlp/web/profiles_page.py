import asyncio
from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import profiles
from tb_dlp.web.layout import auth, he, page

_ALERT_OK = "flex items-center gap-2 bg-emerald-50 text-emerald-700 border-l-4 border-emerald-500 rounded-r-lg px-4 py-2.5 text-sm mb-4"


async def profiles_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    saved = request.rel_url.query.get("saved", "")
    alert = f"<div class='{_ALERT_OK}'>{he(saved)} saved.</div>" if saved else ""
    rows = ""
    for uid, data in profiles.USER_PROFILES.items():
        name = he(data.get("name", uid))
        username = f"@{he(data['username'])}" if data.get("username") else "—"
        notes = he(data.get("notes", ""))
        buf = len(profiles.USER_MESSAGE_BUFFERS.get(int(uid), []))
        buf_color = "text-emerald-600 font-medium" if buf >= profiles.PROFILE_UPDATE_THRESHOLD else "text-gray-400"
        rows += f"""<tr class="hover:bg-gray-50">
  <td class="px-4 py-3 border-b border-gray-100"><span class="font-medium text-gray-900">{name}</span><br><span class="text-gray-400 text-xs">{username}</span></td>
  <td class="px-4 py-3 border-b border-gray-100 text-sm text-gray-600 max-w-xs truncate">{notes}</td>
  <td class="px-4 py-3 border-b border-gray-100 text-center"><span class="text-xs {buf_color}">{buf}/{profiles.PROFILE_UPDATE_THRESHOLD}</span></td>
  <td class="px-4 py-3 border-b border-gray-100"><a href="/admin/profiles/{he(uid)}/edit" class="inline-flex items-center px-2.5 py-1 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-md hover:bg-indigo-100">Edit</a></td>
</tr>"""
    if not rows:
        rows = """<tr><td colspan='4' class='px-4 py-12 text-center'>
<svg class="w-10 h-10 text-gray-300 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z"/></svg>
<p class="text-gray-400 text-sm">No profiles yet — need 25+ messages per person</p></td></tr>"""
    body = f"""
<h1 class="text-2xl font-bold text-gray-900 tracking-tight mb-6">Member profiles</h1>
{alert}
<div class="mb-3">
  <input id="profileFilter" type="text" placeholder="Filter profiles…" class="w-full max-w-xs border border-gray-200 rounded-lg px-3.5 py-2 text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-400">
</div>
<div class="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
  <table class="w-full text-sm" id="profileTable">
    <thead><tr class="bg-gray-50/80"><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Member</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Notes</th><th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Buffer</th><th class="px-4 py-3 w-16"></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<script>
document.getElementById('profileFilter').addEventListener('input', function() {{
  var q = this.value.toLowerCase();
  document.querySelectorAll('#profileTable tbody tr').forEach(function(r) {{
    r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}});
</script>"""
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
  <a href="/admin/profiles" class="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-indigo-600 mb-4">
    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg>
    Back to profiles
  </a>
  <div class="flex items-baseline gap-3 mb-1">
    <h1 class="text-2xl font-bold text-gray-900 tracking-tight">{name}</h1>
    <span class="text-gray-400 text-sm">{username}</span>
  </div>
  <p class="text-gray-400 text-xs mb-5">Buffer: {buf}/{profiles.PROFILE_UPDATE_THRESHOLD} messages until next auto-refresh</p>
  <div class="bg-white rounded-xl border border-gray-100 shadow-sm p-6">
    <form method="post">
      <div class="mb-5">
        <label class="block text-sm font-medium text-gray-700 mb-1.5">Real name</label>
        <input name="real_name" class="w-full border border-gray-200 rounded-lg px-3.5 py-2.5 text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-400" value="{real_name}" placeholder="e.g. Ваня Петренко">
        <p class="text-xs text-gray-400 mt-1.5">The person's real name — AI will know who they actually are.</p>
      </div>
      <div class="mb-5">
        <label class="block text-sm font-medium text-gray-700 mb-1.5">Notes</label>
        <textarea name="notes" class="w-full border border-gray-200 rounded-lg px-3.5 py-2.5 text-sm font-mono bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-400" rows="6">{notes}</textarea>
        <p class="text-xs text-gray-400 mt-1.5">This is what the AI uses to tailor replies to this person.</p>
      </div>
      <div class="flex gap-2.5">
        <button type="submit" class="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">Save changes</button>
        <a href="/admin/profiles" class="px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50">Cancel</a>
      </div>
    </form>
    <div class="border-t border-gray-100 mt-5 pt-5">
      <form method="post" action="/admin/profiles/{he(uid)}/refresh">
        <button type="submit" class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100" {'disabled' if buf == 0 else ''}>
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182"/></svg>
          Refresh profile now ({buf} buffered)
        </button>
        {"<p class='text-xs text-amber-500 mt-1.5'>No buffered messages to summarize yet.</p>" if buf == 0 else ""}
      </form>
    </div>
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
