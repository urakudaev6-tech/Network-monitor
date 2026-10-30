# Network Monitor

[![CI](https://github.com/USERNAME/network-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/USERNAME/network-monitor/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![React](https://img.shields.io/badge/react-18-61dafb)
![Tests](https://img.shields.io/badge/tests-152%20passed-brightgreen)

TCP / ICMP мониторинг с веб-панелью, REST API, PostgreSQL и миграциями.

## Стек

- **Backend:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL (SQLite для dev), pydantic-settings
- **Frontend:** React 18, TypeScript, Vite, TanStack Query, Recharts, Tailwind
- **Тесты:** pytest — 152 passed, TestClient

## Архитектура

```
FastAPI routes
   -> MonitorService (координация)
       -> MonitorEngine  (TCP/ICMP проверки, in-memory история)
       -> Repository     (SQLAlchemy -> PostgreSQL)
```

MonitorEngine не знает про БД. Repository не знает про сеть. MonitorService связывает их.

## Быстрый старт (Docker, всё в одном)

```bash
cp .env.example .env
docker compose up --build -d
```

**Фронтенд собирается внутри Docker-образа** (multi-stage: node -> build -> nginx).
Предварительный `npm run build` на хосте **не нужен**.

- UI:  http://localhost
- API: http://localhost:8000/docs
- API через nginx: http://localhost/api/health

Проверка:

```bash
curl.exe http://localhost:8000/health     # {"status":"ok"}
curl.exe http://localhost/api/health      # {"status":"ok"}  (nginx proxy)
```

## Локальная разработка (SQLite, без Docker)

Backend:

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend (отдельный терминал):

```bash
cd frontend
npm install
npm run dev
```

API: http://127.0.0.1:8000/docs
UI:  http://localhost:5173

## Планировщик

`SCHEDULER_INTERVAL` (env, секунды, дефолт 60, `0` = выключен).

- Запускается через `asyncio.create_task` в `lifespan`.
- `asyncio.sleep(interval)` — **после** завершения проверки. Интервал отсчитывается от **конца** предыдущего запуска, поэтому **наложения циклов нет**.
- При остановке приложения (`Ctrl+C`, `docker compose down`) — `task.cancel()`, корректное завершение.

Проверка:

```powershell
$env:SCHEDULER_INTERVAL="30"
uvicorn app.main:app --reload
# target 8.8.8.8 -> через 30 сек статус UP сам (без кнопки)
```

## API

| Метод  | Путь                            | Назначение                    |
|--------|---------------------------------|-------------------------------|
| GET    | /health                         | healthcheck                   |
| GET    | /targets                        | список устройств              |
| POST   | /targets                        | добавить                      |
| DELETE | /targets/{id}                   | удалить                       |
| GET    | /targets/{id}                   | одно устройство               |
| GET    | /targets/{id}/history?limit=    | история (1..1000)             |
| POST   | /monitor/run                    | запустить проверку            |
| GET    | /monitor/results                | последние результаты          |

## Тесты

```bash
pytest -q                       # 152 passed
cd frontend && npm run build    # production build (для CI)
```

## CI

`.github/workflows/ci.yml` — 3 job'а на push/PR в `main`:
- `backend` — pytest на SQLite in-memory
- `frontend` — npm ci + build
- `docker` — build обоих образов

## Скриншоты

| Dashboard | Детали устройства |
|-----------|-------------------|
| ![](docs/dashboard.png) | ![](docs/details.png) |

## Лицензия

MIT
