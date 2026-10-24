from fastapi import FastAPI

from app.routers.health import router

app = FastAPI()

app.include_router(router)
