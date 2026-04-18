from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()
TONAPI_KEY = os.getenv("TONAPI_KEY")

app = FastAPI()

# Разрешаем WebApp доступ
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Позже можно заменить на конкретный адрес твоего GitHub
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session = None

@app.on_event("startup")
async def startup():
    global session
    session = aiohttp.ClientSession(headers={"Authorization": f"Bearer {TONAPI_KEY}"})

@app.on_event("shutdown")
async def shutdown():
    await session.close()

# Кеш на 20 секунд
cache = {}

async def tonapi_get_collection(addr: str):
    from time import time
    now = time()

    if addr in cache and now - cache[addr]["ts"] < 20:
        return cache[addr]["data"]

    url = f"https://tonapi.io/v2/nfts/collections/{addr}"
    async with session.get(url) as r:
        data = await r.json()
        cache[addr] = {"ts": now, "data": data}
        return data
    
@app.get("/api/collection")
async def get_collection(addr: str = Query(...)):
    data = await tonapi_get_collection(addr)
    return data
    
# Запуск: uvicorn api:app --host 0.0.0.0 --port 8000
# uvicorn api:app --host 0.0.0.0 --port 8000 --reload