"""FastAPI application entry point."""

from fastapi import FastAPI

from tracebackai import __version__

app = FastAPI(title="Traceback", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}
