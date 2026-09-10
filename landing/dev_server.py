"""Локальный запуск лендинга отдельно от остального проекта agropipe.

    cd landing
    python3 dev_server.py

Открывает http://127.0.0.1:8080. Заявки в этом режиме падают в
./cases/_leads/ рядом с этим файлом, уведомление владельцу не отправляется
(intake.py недоступен вне репозитория agropipe) — пишется в консоль.

На проде этот файл не используется: там router из api/lead.py и static/
монтируются в bot.py агропайплайна (см. README.md, раздел «Деплой»).
"""
import logging
from pathlib import Path

import uvicorn

logging.basicConfig(level=logging.INFO)
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.lead import router

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080)
