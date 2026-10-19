import json
import logging
import sys
from datetime import UTC, datetime

SAFE_FIELDS = {"event", "stage", "payment_id", "event_id", "attempt", "error_code", "status"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": getattr(record, "event", record.name),
            "stage": getattr(record, "stage", "runtime"),
        }
        for field in SAFE_FIELDS - {"event", "stage"}:
            value = getattr(record, field, None)
            if value is not None:
                data[field] = str(value)
        if record.levelno >= logging.WARNING and "error_code" not in data:
            data["error_code"] = (
                record.exc_info[0].__name__ if record.exc_info else record.name.replace(".", "_")
            )
        return json.dumps(data, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in (
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "faststream",
        "sqlalchemy",
        "aio_pika",
        "aiormq",
    ):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
        logger.setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True


def log_event(event: str, stage: str, *, level: int = logging.INFO, **fields: object) -> None:
    safe = {key: value for key, value in fields.items() if key in SAFE_FIELDS}
    logging.getLogger("payment_service").log(
        level, "", extra={"event": event, "stage": stage, **safe}
    )
