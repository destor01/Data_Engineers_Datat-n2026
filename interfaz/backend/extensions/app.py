"""Aplicación de prueba aislada; producción local registra los mismos routers en main.py."""
from fastapi import FastAPI
from .api import router
from .improvement import router as improvement_router

app = FastAPI(title='Quality Audit extensions')
app.include_router(router)
app.include_router(improvement_router)
