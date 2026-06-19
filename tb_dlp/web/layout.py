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
    nav_links = "".join(
        f'<a href="{url}" class="px-3 py-2 rounded-md text-sm transition-colors {"text-white bg-white/10 font-medium" if active == key else "text-gray-400 hover:text-white hover:bg-white/5"}">{label}</a>'
        for label, url, key in links
    )
    mobile_links = "".join(
        f'<a href="{url}" class="block px-3 py-2 rounded-md text-sm transition-colors {"text-white bg-white/10 font-medium" if active == key else "text-gray-400 hover:text-white hover:bg-white/5"}">{label}</a>'
        for label, url, key in links
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{he(title)} — tb-dlp</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
  tailwind.config = {{
    theme: {{
      extend: {{
        fontFamily: {{ sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'] }},
      }}
    }}
  }}
  </script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    * {{ transition-property: color, background-color, border-color, box-shadow, opacity; transition-duration: 150ms; transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1); }}
    button:disabled {{ opacity: 0.4; cursor: not-allowed; }}
  </style>
</head>
<body class="bg-gray-50 min-h-screen font-sans text-gray-900 antialiased">
<nav class="bg-gray-900 border-b border-gray-800 sticky top-0 z-50">
  <div class="max-w-6xl mx-auto px-4">
    <div class="flex items-center justify-between h-14">
      <div class="flex items-center gap-2">
        <div class="w-7 h-7 rounded-lg bg-indigo-500 flex items-center justify-center">
          <svg class="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
        </div>
        <span class="text-white font-semibold text-base tracking-tight">tb-dlp</span>
      </div>
      <div class="hidden md:flex items-center gap-1">{nav_links}</div>
      <button onclick="document.getElementById('mobile-menu').classList.toggle('hidden')" class="md:hidden text-gray-400 hover:text-white p-1">
        <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16"/></svg>
      </button>
    </div>
  </div>
  <div id="mobile-menu" class="hidden md:hidden border-t border-gray-800 px-4 py-2 space-y-1">{mobile_links}</div>
</nav>
<main class="max-w-6xl mx-auto px-4 py-8">{body}</main>
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
