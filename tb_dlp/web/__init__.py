from aiohttp import web as aio_web

from tb_dlp import config
from tb_dlp.web import cache_page, comebacks_page, dashboard, login, messages_page, phrases_page, profiles_page, whitelist_page
from tb_dlp.web.layout import token_middleware

_WEB_PORT = 8080


async def start_web_server() -> None:
    web_app = aio_web.Application(middlewares=[token_middleware])
    web_app.router.add_get("/", lambda _r: aio_web.HTTPFound("/admin"))
    web_app.router.add_get("/login", login.login_get)
    web_app.router.add_post("/login", login.login_post)
    web_app.router.add_get("/admin", dashboard.stats_page)
    web_app.router.add_post("/admin/ai-toggle", dashboard.ai_toggle)
    web_app.router.add_post("/admin/personality", dashboard.personality_set)
    web_app.router.add_get("/admin/profiles", profiles_page.profiles_page)
    web_app.router.add_get("/admin/profiles/{user_id}/edit", profiles_page.edit_get)
    web_app.router.add_post("/admin/profiles/{user_id}/edit", profiles_page.edit_post)
    web_app.router.add_post("/admin/profiles/{user_id}/refresh", profiles_page.refresh_profile)
    web_app.router.add_get("/admin/whitelist", whitelist_page.whitelist_page)
    web_app.router.add_post("/admin/whitelist/add", whitelist_page.whitelist_add)
    web_app.router.add_post("/admin/whitelist/remove", whitelist_page.whitelist_remove)
    web_app.router.add_post("/admin/whitelist/ai-toggle", whitelist_page.ai_toggle_chat)
    web_app.router.add_get("/admin/cache", cache_page.cache_page)
    web_app.router.add_post("/admin/cache/remove", cache_page.cache_remove)
    web_app.router.add_post("/admin/cache/bulk-remove", cache_page.cache_bulk_remove)
    web_app.router.add_post("/admin/cache/clear", cache_page.cache_clear)
    web_app.router.add_get("/admin/messages", messages_page.messages_page)
    web_app.router.add_post("/admin/messages/send", messages_page.messages_send)
    web_app.router.add_post("/admin/messages/delete", messages_page.messages_delete)
    web_app.router.add_post("/admin/messages/edit", messages_page.messages_edit)
    web_app.router.add_get("/admin/comebacks", comebacks_page.comebacks_page)
    web_app.router.add_post("/admin/comebacks/add", comebacks_page.comebacks_add)
    web_app.router.add_post("/admin/comebacks/remove", comebacks_page.comebacks_remove)
    web_app.router.add_get("/admin/phrases", phrases_page.phrases_page)
    web_app.router.add_post("/admin/phrases/add", phrases_page.phrases_add)
    web_app.router.add_post("/admin/phrases/remove", phrases_page.phrases_remove)
    runner = aio_web.AppRunner(web_app)
    await runner.setup()
    await aio_web.TCPSite(runner, "0.0.0.0", _WEB_PORT).start()
    config.log.info("Admin web server listening on port %d", _WEB_PORT)
