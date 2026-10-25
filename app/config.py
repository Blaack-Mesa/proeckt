"""Конфигурация приложения ProjectFlow (параметры берутся из переменных окружения)."""
import os


class Config:
    """Базовая конфигурация. Для тестов переопределяется в create_app()."""

    SECRET_KEY = os.environ.get("PF_SECRET_KEY", "dev-secret-change-me")
    DATABASE = os.environ.get("PF_DATABASE", "projectflow.db")
    JWT_EXPIRES_MIN = 60          # срок жизни access-токена, минут
    RESET_EXPIRES_MIN = 15        # срок жизни токена восстановления пароля, минут
    MIN_PASSWORD_LEN = 8          # минимальная длина пароля
    # В боевой среде токен восстановления отправляется по e-mail, а не в ответе API.
    EXPOSE_RESET_TOKEN = os.environ.get("PF_EXPOSE_RESET_TOKEN", "0") == "1"
    JSON_AS_ASCII = False
