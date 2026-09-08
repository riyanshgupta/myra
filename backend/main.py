from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup

    yield
    # shutdown
    


app = FastAPI(
    title="FastAPI Wideorbit Analyse Agent",
    description="API for the Wideorbit Analyse Agent",
    version="1.0.0",
    contact={"name": "Riyansh Gupta", "email": "riyanshgupta750@gmail.com"},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(f"/health")
def health_check():
    return JSONResponse(content={"status": "healthy"}, status_code=200)

