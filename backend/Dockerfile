FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY app/ app/

RUN pip install --no-cache-dir .

# Download CJK fonts for PDF export (Chinese text rendering)
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    bash app/export/fonts/download_fonts.sh && \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

ARG BUILD_TAG=dev
ARG BUILD_TIME=""
ENV BUILD_TAG=${BUILD_TAG}
ENV BUILD_TIME=${BUILD_TIME}

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
