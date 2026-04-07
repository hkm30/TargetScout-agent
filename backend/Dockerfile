FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY app/ app/

RUN pip install --no-cache-dir .

ARG BUILD_TAG=dev
ARG BUILD_TIME=""
ENV BUILD_TAG=${BUILD_TAG}
ENV BUILD_TIME=${BUILD_TIME}

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
