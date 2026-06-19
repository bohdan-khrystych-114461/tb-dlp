import time

from aiohttp import web as aio_web

from tb_dlp import config
from tb_dlp.web.layout import page, set_session_cookie

_login_failures: dict[str, list[float]] = {}  # ip -> list of failure timestamps
_LOGIN_MAX_ATTEMPTS = 10
_LOGIN_LOCKOUT_SECONDS = 3600


async def login_get(request: aio_web.Request) -> aio_web.Response:
    if not config.ADMIN_TOKEN:
        return aio_web.Response(
            text=page("Login", "<div class='bg-red-50 text-red-800 border border-red-200 rounded px-4 py-2'>ADMIN_TOKEN secret is not set on Fly.io.</div>"),
            content_type="text/html",
        )
    error = "error" in request.rel_url.query
    body = f"""
<div class="flex items-center justify-center min-h-[60vh]">
  <div class="w-full max-w-sm">
    <div class="bg-white rounded-lg shadow p-6">
      <h5 class="font-semibold text-lg mb-3">Admin login</h5>
      {"<div class='bg-red-50 text-red-800 border border-red-200 rounded px-4 py-2 mb-3'>Wrong token.</div>" if error else ""}
      <form method="post">
        <div class="mb-3">
          <input type="password" name="token" class="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Admin token" autofocus>
        </div>
        <button type="submit" class="w-full bg-gray-900 text-white rounded py-2 hover:bg-gray-800">Login</button>
      </form>
    </div>
  </div>
</div>"""
    return aio_web.Response(text=page("Login", body), content_type="text/html")


async def login_post(request: aio_web.Request) -> aio_web.Response:
    ip = request.remote or "unknown"
    now = time.time()
    failures = [t for t in _login_failures.get(ip, []) if now - t < _LOGIN_LOCKOUT_SECONDS]
    if len(failures) >= _LOGIN_MAX_ATTEMPTS:
        return aio_web.Response(
            text=page("Login", "<div class='bg-red-50 text-red-800 border border-red-200 rounded px-4 py-2'>Too many failed attempts. Try again in an hour.</div>"),
            content_type="text/html",
            status=429,
        )
    data = await request.post()
    if data.get("token") == config.ADMIN_TOKEN:
        _login_failures.pop(ip, None)
        resp = aio_web.HTTPFound("/admin")
        set_session_cookie(resp)
        return resp
    failures.append(now)
    _login_failures[ip] = failures
    return aio_web.HTTPFound("/login?error")
