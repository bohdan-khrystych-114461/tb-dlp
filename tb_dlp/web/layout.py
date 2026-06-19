from html import escape as he

from aiohttp import web as aio_web

from tb_dlp import config

SESSION_COOKIE = "tbd_admin"


def page(title: str, body: str, active: str = "") -> str:
    links = [
        ("Stats", "/admin", "stats"),
        ("Profiles", "/admin/profiles", "profiles"),
        ("Whitelist", "/admin/whitelist", "whitelist"),
        ("Cache", "/admin/cache", "cache"),
        ("Messages", "/admin/messages", "messages"),
        ("Comebacks", "/admin/comebacks", "comebacks"),
        ("Phrases", "/admin/phrases", "phrases"),
    ]
    nav = "".join(
        f'<a href="{url}" class="px-3 py-2 text-sm {"text-white font-semibold" if active == key else "text-gray-400 hover:text-white"}">{label}</a>'
        for label, url, key in links
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{he(title)} — tb-dlp</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-gray-50 min-h-screen">
<nav class="bg-gray-900 px-4 flex items-center justify-between h-12">
  <span class="text-white font-bold text-lg">tb-dlp</span>
  <div class="flex">{nav}</div>
</nav>
<div class="max-w-6xl mx-auto px-4 py-6">{body}</div>
</body>
</html>"""


def auth(request: aio_web.Request) -> bool:
    return bool(config.ADMIN_TOKEN) and request.cookies.get(SESSION_COOKIE) == config.ADMIN_TOKEN


def set_session_cookie(resp: aio_web.StreamResponse) -> None:
    resp.set_cookie(SESSION_COOKIE, config.ADMIN_TOKEN, httponly=True, secure=True, samesite="Strict", max_age=7 * 24 * 3600)


@aio_web.middleware
async def token_middleware(request: aio_web.Request, handler):
    token = request.rel_url.query.get("token")
    if token and token == config.ADMIN_TOKEN:
        clean = str(request.rel_url.with_query(
            {k: v for k, v in request.rel_url.query.items() if k != "token"}
        ))
        resp = aio_web.HTTPFound(clean or request.path)
        set_session_cookie(resp)
        return resp
    return await handler(request)
