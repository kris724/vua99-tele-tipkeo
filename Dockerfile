FROM python:3.11-slim
RUN apt-get update && apt-get install -y \
    wget \
    procps \
    libnss3 \
    libnspr4 \
    libcups2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgdk-pixbuf-2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    libxcomposite1 \
    libxrandr2 \
    libxrender1 \
    libxtst6 \
    libfontconfig1 \
    libexpat1 \
    libdbus-1-3 \
    libdrm2 \
    libglib2.0-0 \
    libgnutls30 \
    libjpeg62-turbo \
    liblcms2-2 \
    libsecret-1-0 \
    libvulkan1 \
    libwebp-dev \
    libx11-6 \
    libxdmcp6 \
    libxext6 \
    libxkbcommon0 \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
    

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
COPY . .
CMD ["python", "main.py"]
