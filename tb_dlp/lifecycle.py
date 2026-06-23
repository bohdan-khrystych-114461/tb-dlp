import asyncio
import os
import subprocess
import sys

from tb_dlp import config
from tb_dlp.web import start_web_server


async def daily_update(_) -> None:
    while True:
        await asyncio.sleep(24 * 60 * 60)
        config.log.info("Running daily yt-dlp update...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "yt-dlp"])
        config.log.info("yt-dlp updated, restarting bot process...")
        os.execv(sys.executable, [sys.executable] + sys.argv)


async def on_startup(application) -> None:
    asyncio.create_task(daily_update(application))
    await start_web_server()
