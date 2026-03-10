from fastapi import FastAPI, Request, HTTPException, Header, Depends, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from typing import Dict, Any
import json
import logging
from datetime import datetime
from maac_middleware import MAACMiddleware

# Keep LINE imports separate to avoid failing if not configured properly yet
try:
    from line_handler import handler as line_handler
    from linebot.v3.exceptions import InvalidSignatureError
except ImportError:
    line_handler = None
    InvalidSignatureError = Exception

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MAAC-Web-Middleware")

app = FastAPI(
    title="Nong Unjai - MAAC Web Middleware",
    description="Middleware for real-time webhooks and orchestration between MAAC (Crescendo Lab) and Nong Unjai.",
    version="1.0.0"
)

# Initialize MAAC Middleware
maac = MAACMiddleware()

# Mount directory for storing and serving video clips
import os
os.makedirs("static/clips", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Import and include the video editor router
from video_router import router as video_router
app.include_router(video_router)

# ─────────────────────────────────────────────────────────────────────────
# Security Dependency: HMAC Verification
# ─────────────────────────────────────────────────────────────────────────
async def verify_signature(request: Request, cresclab_signature: str = Header(None)):
    """
    Dependency to verify CrescLab-Signature for all incoming webhooks.
    """
    if not cresclab_signature:
        logger.warning("Missing CrescLab-Signature header")
        raise HTTPException(status_code=401, detail="Missing Signature")
    
    # We need the raw body for HMAC verification
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    
    if not maac.verify_webhook_signature(body_str, cresclab_signature):
        logger.error(f"Invalid signature detected: {cresclab_signature}")
        raise HTTPException(status_code=401, detail="Invalid Signature")
        
    return body_bytes

# ─────────────────────────────────────────────────────────────────────────
# Root Redirect
# ─────────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "message": "Nong Unjai MAAC Middleware is running",
        "admin_ui": "/admin",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/api/tags")
async def get_all_tags():
    """
    Returns all available tags.
    """
    try:
        return maac.db.get_all_tags()
    except Exception as e:
        logger.error(f"Error fetching tags: {str(e)}")
        raise HTTPException(status_code=500, detail="Database Error")

# ─────────────────────────────────────────────────────────────────────────
# Webhook and Main
# ─────────────────────────────────────────────────────────────────────────
@app.post("/webhook")
async def receive_webhook(payload: bytes = Depends(verify_signature)):
    """
    Verified endpoint to receive real-time updates from MAAC.
    """
    try:
        data = json.loads(payload)
        maac.handle_webhook(data)
        return {"status": "success", "message": "Webhook processed"}
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal processing error")

@app.post("/line/webhook")
async def line_webhook(request: Request, x_line_signature: str = Header(None)):
    """
    Verified endpoint to receive webhook events from LINE Messaging API.
    """
    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature header")
        
    body = await request.body()
    body_str = body.decode("utf-8")
    
    if line_handler is None:
        logger.error("LINE Messaging API is not configured or failed to initialize.")
        raise HTTPException(status_code=500, detail="LINE Integration not available")
        
    try:
        line_handler.handle(body_str, x_line_signature)
    except InvalidSignatureError:
        logger.error(f"Invalid LINE signature. Signature: {x_line_signature}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Error handling LINE webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
        
    return "OK"

# ─────────────────────────────────────────────────────────────────────────
# Orchestration Endpoints (Internal)
# ─────────────────────────────────────────────────────────────────────────
@app.post("/sync/contacts")
async def trigger_full_sync(background_tasks: BackgroundTasks):
    """
    Triggers a full sync (contacts and events) in the background.
    """
    def do_sync():
        maac.sync_all_tags()
        maac.sync_all_contacts()
        maac.sync_all_events()
        
    background_tasks.add_task(do_sync)
    return {"status": "accepted", "message": "Full sync started in background"}

@app.post("/sync/performance/{event_id}")
async def trigger_performance_sync(event_id: int, start_date: str = None, end_date: str = None):
    """
    Synchronously triggers a performance sync for a specific event.
    """
    try:
        maac.sync_performance(event_id, start_date, end_date)
        return {"status": "success", "message": f"Performance for event {event_id} synced"}
    except Exception as e:
        logger.error(f"Error syncing performance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """
    Health check for monitoring.
    """
    return {"status": "ok", "timestamp": str(datetime.now())}

# ─────────────────────────────────────────────────────────────────────────
# Admin Dashboard Endpoints
# ─────────────────────────────────────────────────────────────────────────
@app.get("/api/contacts")
async def get_dashboard_contacts(limit: int = 50, offset: int = 0, status: str = None, tag: str = None, search: str = None):
    """
    Returns paginated and filtered contacts for the dashboard.
    """
    try:
        return maac.db.get_all_contacts(limit=limit, offset=offset, status=status, tag=tag, search=search)
    except Exception as e:
        logger.error(f"Error fetching contacts: {str(e)}")
        raise HTTPException(status_code=500, detail="Database Error")

@app.get("/api/performance")
async def get_dashboard_performance():
    """
    Returns performance summary for the dashboard.
    """
    try:
        return maac.db.get_performance_summary()
    except Exception as e:
        logger.error(f"Error fetching performance: {str(e)}")
        raise HTTPException(status_code=500, detail="Database Error")

@app.get("/api/settings")
async def get_settings():
    """
    Returns all system settings.
    """
    try:
        return maac.db.get_all_settings()
    except Exception as e:
        logger.error(f"Error fetching settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Database Error")

@app.post("/api/settings")
async def update_settings(settings: Dict[str, str]):
    """
    Updates system settings and refreshes MAAC middleware config.
    """
    try:
        for key, value in settings.items():
            maac.db.update_setting(key, value)
        
        # Refresh the middleware configuration in memory
        maac.refresh_config()
        
        return {"status": "success", "message": "Settings updated and middleware refreshed"}
    except Exception as e:
        logger.error(f"Error updating settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Database Error")

@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/", response_class=HTMLResponse, include_in_schema=False)
async def admin_dashboard():
    """
    Serves the modern Admin Dashboard UI.
    """
    try:
        with open("admin_dashboard.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Admin Dashboard Template Not Found</h1><p>Please check if admin_dashboard.html exists.</p>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
