# src/api/main.py
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

app = FastAPI()

# --- CORS so you can embed on it-storm.fr later ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Serve your public assets under /client-chat ---
PUBLIC_DIR = Path(__file__).resolve().parents[2] / "public"
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)  # ensure folder exists
app.mount("/client-chat", StaticFiles(directory=str(PUBLIC_DIR)), name="client-chat")

# --- Optional: a tiny home page to check things quickly ---
@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>StormCopilot Dev</title></head>
<body>
  <h1>StormCopilot API running</h1>
  <p>Embed JS: <code>/client-chat/embed.js</code></p>
</body>
</html>
"""

# --- Favicon route (fixes your 404) ---
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = PUBLIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return JSONResponse({"detail": "favicon not found"}, status_code=404)

# --- Chat endpoint (simple echo to wire the UI; replace with your RAG call) ---
from pydantic import BaseModel

class ChatIn(BaseModel):
    message: str
    session_id: str | None = None

@app.post("/api/chat")
def api_chat(body: ChatIn):
    # Plug your pipeline here:
    # from src.rag.chain import get_answer
    # answer, sources = get_answer(body.message)
    # return {"answer": answer, "sources": sources}

    return {"answer": f"Vous avez dit: {body.message}", "sources": []}
