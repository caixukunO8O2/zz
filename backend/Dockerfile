FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

RUN groupadd --gid 10001 xianzhi \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin xianzhi \
    && install -d -o 10001 -g 10001 /app/.data/uploads

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

USER 10001:10001

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
