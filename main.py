"""Main module for the Carbon API and web server."""

import os
# pyrefly: ignore [missing-import]
import logging

# pyrefly: ignore [missing-import]
from contextlib import asynccontextmanager

# pyrefly: ignore [missing-import]
from fastapi import FastAPI, HTTPException, Body

# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles

# pyrefly: ignore [missing-import]
from fastapi.responses import FileResponse

# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field

# pyrefly: ignore [missing-import]
from typing import Literal, Optional

# pyrefly: ignore [missing-import]
import config

# pyrefly: ignore [missing-import]
from carbon_utils import calculate_footprint, app_carbon_tracker

# pyrefly: ignore [missing-import]
import firebase_service

# pyrefly: ignore [missing-import]
import ai_service

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("carbon_main")


# Setup Lifespan to handle CodeCarbon initialization
@asynccontextmanager
async def lifespan(app: FastAPI):  # pylint: disable=unused-argument
    """Manages the startup and shutdown lifecycle events."""
    # Startup: Initialize CodeCarbon tracker
    logger.info("Initializing CodeCarbon emissions tracker...")
    app_carbon_tracker.start()
    yield
    # Shutdown: Stop CodeCarbon tracker if running
    if app_carbon_tracker.initialized and app_carbon_tracker.tracker:
        try:
            app_carbon_tracker.tracker.stop()
            logger.info("CodeCarbon emissions tracker stopped.")
        except Exception as e:
            logger.warning(f"Error stopping CodeCarbon tracker: {e}")


app = FastAPI(
    title="Carbon - Interactive Footprint Tracker & AI Advisor",
    description="Python/FastAPI backend using Firebase and Google Gemini AI.",
    version="1.0.0",
    lifespan=lifespan,
)


# HTTP Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self';"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    return response


# Input schemas for validation
class TransportInput(BaseModel):
    """Input schema for transportation emissions."""
    car_km: float = Field(default=0.0, ge=0.0, le=100000.0)
    bus_km: float = Field(default=0.0, ge=0.0, le=100000.0)
    flight_km: float = Field(default=0.0, ge=0.0, le=100000.0)


class EnergyInput(BaseModel):
    """Input schema for energy emissions."""
    grid_kwh: float = Field(default=0.0, ge=0.0, le=100000.0)
    green_kwh: float = Field(default=0.0, ge=0.0, le=100000.0)


class WasteInput(BaseModel):
    """Input schema for waste emissions."""
    landfill_kg: float = Field(default=0.0, ge=0.0, le=100000.0)
    recycled_kg: float = Field(default=0.0, ge=0.0, le=100000.0)


class CalculationRequest(BaseModel):
    """Schema for a complete emission calculation request."""
    transport: TransportInput
    energy: EnergyInput
    diet: Literal["balanced", "meat_heavy", "vegetarian", "vegan"] = "balanced"
    waste: WasteInput


class CalculationBreakdown(BaseModel):
    """Schema for the breakdown of calculated emissions."""
    transport: float = Field(..., ge=0.0)
    energy: float = Field(..., ge=0.0)
    diet: float = Field(..., ge=0.0)
    waste: float = Field(..., ge=0.0)


class CalculationResult(BaseModel):
    """Schema for the final calculated footprint result."""
    breakdown: CalculationBreakdown
    total: float = Field(..., ge=0.0)
    trees_needed: float = Field(..., ge=0.0)
    inputs: CalculationRequest


class CoachRequest(BaseModel):
    """Input schema for asking the AI Coach a question."""
    message: str = Field(..., min_length=1, max_length=1000)
    last_calculation: Optional[CalculationResult] = None


# API Routes
@app.post("/api/calculate")
async def api_calculate(request: CalculationRequest):
    """Calculate the user's carbon footprint and save it."""
    try:
        # Perform calculation
        calc_result = calculate_footprint(request.model_dump())
        # Save to database (Firebase/Local Fallback)
        saved_calc = firebase_service.save_calculation(calc_result)
        return saved_calc
    except Exception as e:
        logger.exception("Error calculating footprint")
        raise HTTPException(
            status_code=500, detail="Internal server error occurred during calculation."
        ) from e


@app.get("/api/history")
async def api_get_history():
    """Get the user's carbon footprint calculation history."""
    try:
        history = firebase_service.get_history()
        return history
    except Exception as e:
        logger.exception("Error fetching history")
        raise HTTPException(
            status_code=500,
            detail="Internal server error occurred while retrieving history.",
        ) from e


@app.get("/api/goals")
async def api_get_goals():
    """Get the user's active goals."""
    try:
        goals = firebase_service.get_goals()
        return goals
    except Exception as e:
        logger.exception("Error fetching goals")
        raise HTTPException(
            status_code=500,
            detail="Internal server error occurred while retrieving goals.",
        ) from e


@app.post("/api/goals/{goal_id}/toggle")
async def api_toggle_goal(goal_id: str, completed: bool = Body(..., embed=True)):
    """Toggle a goal's completion status."""
    try:
        updated_goals = firebase_service.toggle_goal(goal_id, completed)
        return updated_goals
    except Exception as e:
        logger.exception("Error toggling goal %s", goal_id)
        raise HTTPException(
            status_code=500,
            detail="Internal server error occurred while updating goal.",
        ) from e


@app.get("/api/badges")
async def api_get_badges():
    """Get the user's earned badges."""
    try:
        badges = firebase_service.get_badges()
        return badges
    except Exception as e:
        logger.exception("Error fetching badges")
        raise HTTPException(
            status_code=500,
            detail="Internal server error occurred while retrieving achievements.",
        ) from e


@app.post("/api/coach")
async def api_coach(request: CoachRequest):
    """Interact with the AI Coach."""
    try:
        reply = await ai_service.get_coaching_response(
            request.message,
            request.last_calculation.model_dump() if request.last_calculation else None,
        )
        return {"response": reply}
    except Exception as e:
        logger.exception("Error querying AI Coach")
        raise HTTPException(
            status_code=500,
            detail="Internal server error occurred while contacting the AI coach.",
        ) from e


@app.get("/api/metrics")
async def api_get_metrics():
    """Get server carbon emission metrics."""
    try:
        metrics = app_carbon_tracker.get_metrics()
        return metrics
    except Exception as e:
        logger.exception("Error fetching carbon metrics")
        raise HTTPException(
            status_code=500,
            detail="Internal server error occurred while loading server metrics.",
        ) from e


# Setup Static Files serving
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)


# Register routes for static asset serving or default redirect
@app.get("/")
async def root():
    """Serve the root index HTML file."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "message": "Carbon app running! Create index.html in the static directory to view the web dashboard."
    }


# Mount static files directory for css/js/images
app.mount("/static", StaticFiles(directory=static_dir), name="static")

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn

    # Check environment configuration and start uvicorn
    print(f"Starting Carbon Server at http://{config.HOST}:{config.PORT}...")
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=config.DEBUG)
