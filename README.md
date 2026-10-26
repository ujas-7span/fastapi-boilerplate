# FasTicket FastAPI Backend

FastAPI service providing Auth and Users CRUD, backed by PostgreSQL, Redis (arq jobs), and S3-compatible storage.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL
- Redis

## Setup

```bash
cp .env.example .env   # fill in DB, Redis, SMTP, S3 credentials
uv sync
uv run alembic upgrade head
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

Run the background worker (needed for queued emails, e.g. password reset, and push notifications) in a separate process:

```bash
uv run arq app.worker.WorkerSettings
```

## Notifications

In-app notifications are stored in the `notifications` table. `title` and `description` hold translation keys, and `data` holds the values filled into them. The API translates both into the request's `locale` header (`en`/`ar`) when it returns a notification. Each user can register one OneSignal device (`user_devices`). When `NOTIFICATION_ENABLED=true`, every new notification is also sent to that device as a push.

All endpoints require a bearer token and are under `/api/v1`:

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/notifications` | The current user's notifications, newest first. Supports the usual `page`/`per_page`/`cursor`, `sort`, `filter[type]=`, `include=sender`, plus `is_read=true\|false` |
| GET  | `/notifications/unread-count` | `{"unread_count": n}` |
| POST | `/notifications/read` | Body `{"ids": [1, 2]}` marks those notifications read; omit `ids` (or the body) to mark all of them read |
| POST | `/notifications/unread` | Same as `/notifications/read`, but marks them unread |
| POST | `/onesignal-player-id` | Body `{"onesignal_player_id", "device_id"?, "device_type"?: "android"\|"ios"\|"web"}`. Saves the user's device, replacing any earlier one |

- **Auto-read:** any authenticated request with `?notify_id=<id>` marks that notification read. This works on the users, categories, media and notifications routes and on `/auth/me`. IDs that belong to another user are ignored.
- **Logout:** `POST /auth/logout` accepts an optional `onesignal_player_id`, which removes that device so it stops receiving push.

Sending a notification from a service:

```python
from app.services import notification_service

await notification_service.notify(
    db,
    user_id=user.id,
    type="order_shipped",
    title_key="notification.order_shipped.title",          # add to app/lang/en + app/lang/ar
    description_key="notification.order_shipped.description",
    data={"order_number": order.number},                   # flat dict of {placeholder} values
    notifiable_type="order",
    notifiable_id=order.id,
)
```

`notify()` stores the row and, when push is enabled, queues the `send_push_notification` worker job. The job sends `headings`/`contents` in every supported language, and OneSignal picks the one matching each device's language. If the user has no device, the job skips the push. New users get a `welcome` notification when they register.

The worker also deletes notifications older than `NOTIFICATION_RETENTION_DAYS` (default 90) every night at 03:30.

Settings (`.env`): `NOTIFICATION_ENABLED`, `ONESIGNAL_APP_ID`, `ONESIGNAL_API_KEY` (the App API key), `ONESIGNAL_API_URL`, `NOTIFICATION_RETENTION_DAYS`.

## Docker

Runs the API, the arq worker, PostgreSQL, Redis and Mailpit (catches outgoing email):

```bash
cp .env.example .env   # set JWT_SECRET_KEY (and S3 credentials if needed)
docker compose up --build
```

| Service  | Host port | URL / connection                                   |
|----------|-----------|----------------------------------------------------|
| API      | 8000      | http://localhost:8000 (Swagger at `/docs`)         |
| Postgres | 5432      | `postgresql://postgres:postgres@localhost:5432/fasticket_fastapi` |
| Redis    | 6379      | `redis://localhost:6379/0`                         |
| Mailpit  | 8025      | http://localhost:8025                              |

Migrations run automatically (`migrate` service) before the API and worker start.

Stop with `docker compose down` (add `-v` to also delete the database and Redis data).

Inside the containers, `DATABASE_URL`, `REDIS_URL` and the SMTP settings are pointed at the Compose services, so the values in `.env` for those are only used when running locally without Docker. The Postgres container uses `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` from `.env`.

Code changes need a rebuild (`docker compose up --build`). Create new migrations locally with `uv run alembic revision --autogenerate -m "..."`; they are applied on the next start.

## Tests

```bash
uv run pytest
```
