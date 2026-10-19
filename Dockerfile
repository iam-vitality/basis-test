FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /app/
COPY src /app/src
COPY alembic.ini /app/
COPY alembic /app/alembic
RUN pip install --no-cache-dir -e '.[dev]'
COPY tests /app/tests
CMD ["python", "-m", "payment_service.main"]
