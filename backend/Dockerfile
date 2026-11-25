# ---- build stage: install dependencies into an isolated prefix ----
FROM python:3.12-slim AS builder
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# ---- runtime stage: only what is needed to run ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL=sqlite:////data/app.db PORT=8000
RUN useradd --create-home app && mkdir /data && chown app:app /data
COPY --from=builder /install /usr/local
WORKDIR /srv
COPY app ./app
USER app
VOLUME /data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
