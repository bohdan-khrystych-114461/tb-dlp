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
        f'<a href="{url}" class="nav-link px-2 {"text-white fw-bold" if active == key else "text-white-50"}">{label}</a>'
        for label, url, key in links
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{he(title)} — tb-dlp</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
</head>
<body class="bg-light">
<nav class="navbar navbar-dark bg-dark px-3 d-flex justify-content-between">
  <span class="navbar-brand fw-bold mb-0">tb-dlp</span>
  <div class="d-flex">{nav}</div>
</nav>
<div class="container py-4">{body}</div>
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
