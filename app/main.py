from fastapi import FastAPI

from app.api.health import router

app = FastAPI(title="Asanbar Pricing Service")
app.include_router(router)
