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
            text=page("Login", "<div class='flex items-center gap-2 bg-red-50 text-red-700 border-l-4 border-red-500 rounded-r-lg px-4 py-3 text-sm'>ADMIN_TOKEN secret is not set on Fly.io.</div>"),
            content_type="text/html",
        )
    error = "error" in request.rel_url.query
    body = f"""
<div class="flex items-center justify-center min-h-[70vh]">
  <div class="w-full max-w-sm">
    <div class="text-center mb-6">
      <div class="w-12 h-12 rounded-2xl bg-indigo-500 flex items-center justify-center mx-auto mb-3">
        <svg class="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
      </div>
      <h2 class="text-xl font-semibold text-gray-900">tb-dlp admin</h2>
      <p class="text-sm text-gray-500 mt-1">Enter your token to continue</p>
    </div>
    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      {"<div class='flex items-center gap-2 bg-red-50 text-red-700 border-l-4 border-red-500 rounded-r-lg px-3 py-2.5 text-sm mb-4'>Wrong token.</div>" if error else ""}
      <form method="post">
        <div class="mb-4">
          <input type="password" name="token" class="w-full border border-gray-200 rounded-lg px-3.5 py-2.5 text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent placeholder-gray-400" placeholder="Admin token" autofocus>
        </div>
        <button type="submit" class="w-full bg-indigo-600 text-white rounded-lg py-2.5 text-sm font-medium hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">Sign in</button>
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
            text=page("Login", "<div class='max-w-sm mx-auto mt-20'><div class='flex items-center gap-2 bg-red-50 text-red-700 border-l-4 border-red-500 rounded-r-lg px-4 py-3 text-sm'>Too many failed attempts. Try again in an hour.</div></div>"),
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
