# PingBoard

Uptime monitoring service. Add a URL, and PingBoard checks it on a schedule,
opens an incident when it goes down, emails you, and shows uptime stats
and a public status page.

## Features
- JWT authentication (register, login, refresh)
- Monitors with 1 to 60 minute intervals, per-user limits and duplicate protection
- Background checks with Celery workers and a Celery Beat scheduler
- Incident tracking: opens after 2 consecutive failures, closes on recovery
- Email alerts on DOWN and UP
- Stats API: uptime % and response-time buckets (24h / 7d / 30d)
- Public status page that never exposes your URLs
- SSRF protection: private and internal addresses are blocked
- Rate limiting on login, register and public endpoints

## Tech stack
Django 5, Django REST Framework, PostgreSQL, Celery, Redis, Docker Compose, pytest

## Run it
    cp .env.example .env
    docker compose up --build

API runs at http://127.0.0.1:8000/api/

## API
| Method | Endpoint | Description |
|---|---|---|
| POST | /api/auth/register/ | Create account |
| POST | /api/auth/token/ | Login |
| GET/POST | /api/monitors/ | List / create monitors |
| POST | /api/monitors/{id}/check_now/ | Run a check now |
| GET | /api/monitors/{id}/stats/?range=24h | Uptime and response stats |
| GET | /api/monitors/{id}/incidents/ | Incident history |
| PUT | /api/status-page/ | Configure your status page |
| GET | /api/public/status/{slug}/ | Public status page |

## Design decisions
- Two schedulers cannot double-check a monitor: due monitors are claimed with
  `SELECT ... FOR UPDATE SKIP LOCKED`.
- A database constraint allows only one open incident per monitor.
- Redirects are followed manually and every hop is validated against SSRF.

## Tests
    pytest