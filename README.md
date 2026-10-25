# ProjectFlow

Информационная система управления проектами. Учебный проект производственной практики ПП.02.
Три модуля в одном приложении (Flask), единая БД (SQLite) и единая JWT-аутентификация.

| Модуль | Пакет | Назначение |
|---|---|---|
| AuthModule | `app/auth` | регистрация, вход, восстановление пароля, роли admin / manager / executor |
| TaskModule | `app/tasks` | проекты, задачи, назначение исполнителей, сроки, статусы (конечный автомат) |
| ReportModule | `app/reports` | отчёты по исполнителю / проекту / периоду, экспорт в XLSX и PDF |

## Запуск

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export PF_SECRET_KEY="длинная-случайная-строка"        # Windows: set PF_SECRET_KEY=...
flask --app app create-admin admin@example.com "Администратор"
flask --app app run
```

## Тесты и контроль качества

```bash
pytest -v          # 70+ тестов: unit, API, интеграционные, переходы состояний
flake8 app tests
pylint app
```

## API (кратко)

Все эндпоинты, кроме `register`, `login`, `password-reset/*`, `health`, требуют заголовок
`Authorization: Bearer <JWT>`. Ошибки: `{"error": {"code": "...", "message": "..."}}`.

| Метод и путь | Роли | Описание |
|---|---|---|
| POST `/api/auth/register` | все | регистрация (роль executor) |
| POST `/api/auth/login` | все | выдача JWT |
| POST `/api/auth/password-reset/request`, `/confirm` | все | восстановление пароля |
| GET `/api/auth/me` | любая | профиль |
| GET `/api/auth/users`, PATCH `/api/auth/users/<id>/role` | admin | пользователи и роли |
| POST/GET `/api/projects`, GET `/api/projects/<id>` | создание: admin, manager | проекты |
| POST/GET `/api/tasks`, GET/PATCH/DELETE `/api/tasks/<id>` | запись: admin, manager | задачи |
| POST `/api/tasks/<id>/status` | по правилам автомата | смена статуса |
| GET `/api/tasks/transitions` | любая | матрица переходов |
| GET `/api/reports/<assignee\|project\|period>?format=json\|xlsx\|pdf` | manager, admin; executor — только по себе | отчёт |
| GET `/api/reports` | admin, manager | история отчётов |

## Статусы задачи

`new → in_progress → review → done`; `review → rejected | in_progress`; `new → rejected`;
`rejected → new`. Статус `done` конечный. Диаграмма: `docs/diagrams.puml`.

## События (шина `app/events.py`)

`user.registered`, `user.logged_in`, `user.password_reset_requested`, `user.password_changed`,
`user.role_changed`, `task.created`, `task.updated`, `task.status_changed`, `task.deleted`,
`report.generated`.

## Ветвление

`main` — стабильная версия, `develop` — интеграция, `feature/*` — отдельные функции.
