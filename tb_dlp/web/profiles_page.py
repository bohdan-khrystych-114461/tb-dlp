import asyncio
from urllib.parse import quote as urlquote

from aiohttp import web as aio_web

from tb_dlp import profiles
from tb_dlp.web.layout import auth, he, page


async def profiles_page(request: aio_web.Request) -> aio_web.Response:
    if not auth(request):
        return aio_web.HTTPFound("/login")
    saved = request.rel_url.query.get("saved", "")
    alert = f"<div class='alert alert-success py-2'>Saved changes for {he(saved)}.</div>" if saved else ""
    rows = ""
    for uid, data in profiles.USER_PROFILES.items():
        name = he(data.get("name", uid))
        username = f"@{he(data['username'])}" if data.get("username") else "—"
        notes = he(data.get("notes", ""))
        buf = len(profiles.USER_MESSAGE_BUFFERS.get(int(uid), []))
        rows += f"""<tr>
  <td>{name}<br><small class="text-muted">{username}</small></td>
  <td><small>{notes}</small></td>
  <td class="text-center"><small class="{'text-success' if buf >= profiles.PROFILE_UPDATE_THRESHOLD else ''}">{buf}/{profiles.PROFILE_UPDATE_THRESHOLD}</small></td>
  <td><a href="/admin/profiles/{he(uid)}/edit" class="btn btn-sm btn-outline-secondary">Edit</a></td>
</tr>"""
    if not rows:
        rows = "<tr><td colspan='4' class='text-muted py-3 text-center'>No profiles yet — need 25+ messages per person.</td></tr>"
    body = f"""
<h4 class="mb-3">Member profiles</h4>
{alert}
<div class="card shadow-sm">
  <table class="table table-hover align-middle mb-0">
    <thead class="table-light"><tr><th>Member</th><th>Notes</th><th class="text-center">Buffer</th><th></th></tr></thead>
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
    notes = he(data.get("notes", ""))
    buf = len(profiles.USER_MESSAGE_BUFFERS.get(int(uid), []))
    body = f"""
<div class="row justify-content-center">
  <div class="col-lg-7">
    <a href="/admin/profiles" class="text-decoration-none text-muted">&larr; Back to profiles</a>
    <h4 class="mt-3">{name} <small class="text-muted fs-6">{username}</small></h4>
    <p class="text-muted small">Buffer: {buf}/{profiles.PROFILE_UPDATE_THRESHOLD} messages until next auto-refresh</p>
    <div class="card shadow-sm">
      <div class="card-body">
        <form method="post">
          <div class="mb-3">
            <label class="form-label fw-semibold">Notes</label>
            <textarea name="notes" class="form-control font-monospace" rows="6">{notes}</textarea>
            <div class="form-text">This is what the AI uses to tailor replies to this person.</div>
          </div>
          <div class="d-flex gap-2 flex-wrap">
            <button type="submit" class="btn btn-dark">Save</button>
            <a href="/admin/profiles" class="btn btn-outline-secondary">Cancel</a>
          </div>
        </form>
        <hr>
        <form method="post" action="/admin/profiles/{he(uid)}/refresh">
          <button type="submit" class="btn btn-outline-primary btn-sm" {'disabled' if buf == 0 else ''}>
            Refresh profile now ({buf} buffered messages)
          </button>
          {"<div class='form-text text-warning'>No buffered messages to summarize yet.</div>" if buf == 0 else ""}
        </form>
      </div>
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
