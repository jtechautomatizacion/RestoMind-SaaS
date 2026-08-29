from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.config import settings
from backend.database import init_db

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title="RestoMind API",
    description="Sistema de comandas y control para restaurantes",
    version="0.1.0",
    debug=settings.debug
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (frontend)
app.mount("/static", StaticFiles(directory="frontend"), name="static")


# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


# Root endpoint
@app.get("/")
async def root():
    return {"message": "RestoMind API", "docs": "/docs"}


# TODO: Include routers
# from backend.routes import platos, comandas, compras, mesas
# app.include_router(platos.router, prefix="/api", tags=["Platos"])
# app.include_router(comandas.router, prefix="/api", tags=["Comandas"])
# app.include_router(compras.router, prefix="/api", tags=["Compras"])
# app.include_router(mesas.router, prefix="/api", tags=["Mesas"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
    )
