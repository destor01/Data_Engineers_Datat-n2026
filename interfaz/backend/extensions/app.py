"""Aplicación de prueba aislada; la API unificada (plataforma/app.py) registra los mismos routers."""
from fastapi import FastAPI
from .api import router
from .improvement import router as improvement_router

app = FastAPI(title='Quality Audit extensions')
app.include_router(router)
app.include_router(improvement_router)
