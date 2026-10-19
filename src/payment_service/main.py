from payment_service.api.app import create_app


def run() -> None:
    import uvicorn

    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=8000,
        access_log=False,
        log_config=None,
        log_level="warning",
    )


if __name__ == "__main__":
    run()
