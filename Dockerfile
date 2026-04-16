FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y \
    ffmpeg git \
    build-essential libffi-dev python3-dev \
    && echo "FFmpeg installed successfully. Version:" \
    && ffmpeg -version \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "bot.py"]