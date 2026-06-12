FROM python:3.12-slim

# ffmpeg is required by yt-dlp to merge video+audio streams
# deno is required by yt-dlp to solve YouTube's "n" signature challenge when cookies are in use
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl unzip \
    && curl -fsSL https://deno.land/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.deno/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .
COPY tb_dlp ./tb_dlp

CMD pip install -q --upgrade yt-dlp && python bot.py
