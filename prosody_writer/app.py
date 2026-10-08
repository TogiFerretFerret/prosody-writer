from collections import OrderedDict
from pathlib import Path
from threading import Lock
from uuid import UUID
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .engine import Scanner

app = FastAPI(title="Prosody Writer")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
sessions = OrderedDict()
parse_lock = Lock()


class ScanRequest(BaseModel):
    session: UUID
    revision: int = Field(ge=0)
    text: str = Field(max_length=12000)


@app.get("/")
@app.get("/index.html")
def editor():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "engine": "prosodic", "version": "3.10.0", "parser": "incremental-dp"}


@app.post("/api/scan")
def scan(request: ScanRequest):
    # Prosodic's shared caches are not assumed thread-safe. Refuse overload
    # rather than allowing stale typing requests to pile up indefinitely.
    if not parse_lock.acquire(blocking=False):
        raise HTTPException(429, "Scanner busy; retry the latest revision.")
    try:
        if request.text.count("\n") > 199:
            raise HTTPException(422, "The editor supports up to 200 lines.")
        scanner = sessions.pop(request.session, None) or Scanner()
        sessions[request.session] = scanner
        while len(sessions) > 16:
            sessions.popitem(last=False)
        return {"revision": request.revision, **scanner.update(request.text)}
    finally:
        parse_lock.release()
