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


<!-- NETWORK_MONITOR_PORTFOLIO_RELEASE_1 -->
## Network Monitor 4.1 — portfolio release notes

Network Monitor is a local network monitoring application built with **Python / FastAPI**, **React / TypeScript**, and a database-backed monitoring history. It supports manual and scheduled network scans, a device registry, history of changes, and an alert center with configurable rules, acknowledgement, filtering, grouping and charts. The email agent is optional.

### Local development

Prerequisites: Python 3.12, Node.js and npm. On Windows, from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm --prefix frontend ci
python -m pytest -q
npm --prefix frontend run build
```

Copy `.env.example` to `.env` and `frontend/.env.example` to `frontend/.env` **only after reviewing their contents** and setting appropriate local values. Environment options and database setup may vary with the selected deployment mode; see the original project instructions above. To run the API locally, use `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`. Run the frontend development server with `npm --prefix frontend run dev`.

### Security and configuration

- **Never commit** `.env`, `.security10.json`, private keys, real credentials, local databases, scan results, `data/`, or `backups/`.
- `.env.example` files are templates, not secure production defaults. Replace any example passwords before deployment.
- Use the scanner **only on networks you are authorized to inspect**. Confirm the subnet and scan interval before enabling scheduled scans.
- ICMP non-response does **not** prove a host is offline. Validate probe accuracy and operational assumptions in your environment.
- The local authentication and email-agent configurations are environment-specific. Do not publish real API keys or mail credentials.
- This repository is a portfolio demonstration, **not a security-certified monitoring product**.

### Validation

The developer's Windows environment reported **166 passing pytest tests** and a successful frontend build for version 4.1 on 2026-11-06. Re-run the commands above on your own installation; these results are not a guarantee for other environments.

### Screenshots and demonstration

Existing screenshots are in `docs/`. Before adding new screenshots, remove or blur real IP addresses, device names, usernames, and other internal network information. A demo dataset is preferable to publishing workplace scans.

### Release checklist

- [ ] Review tracked and staged files for secrets and internal data.
- [ ] Confirm the example environment files contain no real credentials.
- [ ] Run `python -m pytest -q` and `npm --prefix frontend run build`.
- [ ] Review the scanner's ICMP success criteria and results.
- [ ] Restore or validate GitHub Actions CI before pushing.
- [ ] Choose a license deliberately; no license is added automatically.
