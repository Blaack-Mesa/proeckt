"""Единый формат ошибок API."""


class ApiError(Exception):
    """Прикладная ошибка: HTTP-статус, машинный код и сообщение для клиента."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        """Тело ответа: {"error": {"code": ..., "message": ...}}."""
        return {"error": {"code": self.code, "message": self.message}}
