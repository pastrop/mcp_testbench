"""Main FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import router
from app.core.config import settings

# Create FastAPI app
app = FastAPI(
    title="UI Renderer Backend",
    description="AI-powered dynamic UI generation for financial contracts",
    version=__version__,
    debug=settings.app_debug,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1", tags=["contracts"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "UI Renderer Backend",
        "version": __version__,
        "status": "running",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
