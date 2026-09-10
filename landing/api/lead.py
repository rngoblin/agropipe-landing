"""POST /api/lead — приём заявок с лендинга agropipeline.ru (раздел 7 ТЗ).

GET / и GET /privacy рендерят те же шаблоны, что видит форма: успех и ошибка
отрисовываются сервером в form_state, поэтому страница работает и без JS —
обычный POST возвращает ту же разметку с заполненным состоянием.

После переноса landing/ в репозиторий agropipe этот router монтируется в
bot.py: `from api.lead import router as lead_router; app.include_router(lead_router)`.
Тогда заявки падают туда же, где кейсы конвейера (см. README), а уведомление
владельцу идёт тем же каналом, что уведомления о падении бота — через
intake.MaxAPI (см. notify_failure.py в agropipe).
"""
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

LANDING_DIR = Path(__file__).resolve().parent.parent
CONTENT_PATH = LANDING_DIR / "content.yaml"
LEADS_DIR = Path(os.environ.get("LEADS_DIR", "cases/_leads"))
RATE_LIMIT_PER_HOUR = 5
MIN_FILL_SECONDS = 3

router = APIRouter()
templates = Jinja2Templates(directory=str(LANDING_DIR / "templates"))
log = logging.getLogger("landing.lead")

# заявки на один процесс — тот же объём, что у остального конвейера (~20/мес),
# отдельное хранилище лимитов не нужно (см. AGROPIPE_OVERVIEW.md, "файлы
# против базы")
_rate_limit: dict[str, list[float]] = {}


def load_content() -> dict[str, Any]:
    with CONTENT_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (
        request.client.host if request.client else "unknown"
    )


def wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def render_index(
    request: Request, form_state: dict | None = None, status_code: int = 200
) -> HTMLResponse:
    if form_state is not None:
        # шаблон всегда читает form_state.errors.<field> и form_state.submitted.<field> —
        # заполняем оба ключа, даже когда вызывающий код передал только "success"
        form_state = {"errors": {}, "submitted": {}, **form_state}
    return templates.TemplateResponse(
        request,
        "index.html.j2",
        {
            "content": load_content(),
            "form_state": form_state,
            "form_rendered_at": str(time.time()),
        },
        status_code=status_code,
    )


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return render_index(request)


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "privacy.html.j2", {"content": load_content()})


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    else:
        return None
    return "+" + digits


def validate(data: dict[str, Any]) -> tuple[str | None, dict[str, str]]:
    """Возвращает (имя первого невалидного поля или None, нормализованные поля)."""
    name = (data.get("name") or "").strip()
    company = (data.get("company") or "").strip()
    phone = normalize_phone(str(data.get("phone") or ""))
    consent = data.get("consent") in (True, "true", "on", "1")

    if not (2 <= len(name) <= 60):
        return "name", {}
    if phone is None:
        return "phone", {}
    if not (2 <= len(company) <= 120):
        return "company", {}
    if not consent:
        return "consent", {}
    return None, {"name": name, "phone": phone, "company": company}


async def parse_payload(request: Request) -> dict[str, Any]:
    if "application/json" in request.headers.get("content-type", ""):
        return await request.json()
    form = await request.form()
    return {k: form.get(k) for k in ("name", "phone", "company", "hp", "consent", "rendered_at")}


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    window = [t for t in _rate_limit.get(ip, []) if now - t < 3600]
    _rate_limit[ip] = window
    return len(window) >= RATE_LIMIT_PER_HOUR


def record_attempt(ip: str) -> None:
    _rate_limit.setdefault(ip, []).append(time.time())


def save_lead(fields: dict[str, str], ip: str) -> None:
    LEADS_DIR.mkdir(parents=True, exist_ok=True)
    lead_id = f"{time.strftime('%Y-%m-%dT%H-%M-%S')}_{uuid.uuid4().hex[:8]}"
    record = {
        "id": lead_id,
        "status": "new",
        "created_at": time.time(),
        "ip": ip,
        **fields,
    }
    tmp_path = LEADS_DIR / f".{lead_id}.tmp"
    tmp_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(LEADS_DIR / f"{lead_id}.json")


async def notify_owner(fields: dict[str, str]) -> None:
    try:
        import intake  # доступен только внутри репозитория agropipe после переноса
    except ImportError:
        log.info("новая заявка (локальный запуск, MAX не настроен): %s", fields)
        return

    owner_id = intake.OWNER_USER_ID
    token = os.environ.get("MAX_BOT_TOKEN")
    if not owner_id or not token:
        log.warning("OWNER_USER_ID/MAX_BOT_TOKEN не заданы, уведомление не отправлено")
        return

    api = intake.MaxAPI(token)
    try:
        await api.send_text(
            int(owner_id),
            "Новая заявка с лендинга:\n"
            f"Имя: {fields['name']}\nТелефон: {fields['phone']}\n"
            f"Компания: {fields['company']}\nВремя: {time.strftime('%Y-%m-%d %H:%M')}",
        )
    finally:
        await api.aclose()


@router.post("/api/lead")
async def submit_lead(request: Request):
    payload = await parse_payload(request)
    ip = client_ip(request)
    as_json = wants_json(request)

    hp = (payload.get("hp") or "").strip()
    try:
        rendered_at = float(payload.get("rendered_at") or 0)
    except (TypeError, ValueError):
        rendered_at = 0.0
    too_fast = (time.time() - rendered_at) < MIN_FILL_SECONDS

    # honeypot, слишком быстрая отправка и превышение лимита частоты —
    # тихо отбрасываем и показываем тот же успех, что настоящему клиенту
    # (раздел 7, пункты 3–5 ТЗ)
    if hp or too_fast or is_rate_limited(ip):
        if as_json:
            return JSONResponse({"ok": True})
        return render_index(request, form_state={"success": True})

    field, fields = validate(payload)
    if field:
        content = load_content()
        message = content["form"][f"error_{field}"]
        if as_json:
            return JSONResponse({"ok": False, "field": field}, status_code=422)
        values = {k: (payload.get(k) or "") for k in ("name", "phone", "company")}
        return render_index(
            request,
            form_state={"success": False, "errors": {field: message}, "submitted": values},
            status_code=422,
        )

    record_attempt(ip)
    try:
        save_lead(fields, ip)
        await notify_owner(fields)
    except Exception:
        log.exception("не удалось сохранить заявку или уведомить владельца")
        content = load_content()
        message = content["form"]["error_generic"].format(phone=content["meta"]["phone_display"])
        if as_json:
            return JSONResponse({"ok": False, "field": "server"}, status_code=502)
        return render_index(
            request,
            form_state={"success": False, "errors": {"server": message}, "submitted": fields},
            status_code=502,
        )

    if as_json:
        return JSONResponse({"ok": True})
    return render_index(request, form_state={"success": True})
