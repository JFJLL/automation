class AppError(Exception):
    """系统基础业务异常"""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code

class AuthenticationError(AppError):
    def __init__(self, message: str = "未登录或登录凭据无效"):
        super().__init__(message, code="AUTHENTICATION_FAILED", status_code=401)

class AuthorizationError(AppError):
    def __init__(self, message: str = "权限不足，需要管理员权限"):
        super().__init__(message, code="PERMISSION_DENIED", status_code=403)

class InvalidDateRangeError(AppError):
    def __init__(self, message: str):
        super().__init__(message, code="INVALID_DATE_RANGE", status_code=400)

class TaskNotFoundError(AppError):
    def __init__(self, message: str = "任务不存在"):
        super().__init__(message, code="TASK_NOT_FOUND", status_code=404)

class TaskAlreadyRunningError(AppError):
    def __init__(self, message: str = "任务正在运行中，请勿重复执行"):
        super().__init__(message, code="TASK_ALREADY_RUNNING", status_code=409)

class DataValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message, code="DATA_VALIDATION_ERROR", status_code=400)

class FeishuError(AppError):
    def __init__(self, message: str, code: str = "FEISHU_ERROR"):
        super().__init__(message, code=code, status_code=502)

class FeishuWriteError(FeishuError):
    def __init__(self, message: str):
        super().__init__(message, code="FEISHU_WRITE_ERROR")

class ProviderError(AppError):
    def __init__(self, message: str, code: str = "PROVIDER_ERROR"):
        super().__init__(message, code=code, status_code=502)

class ProviderAuthError(ProviderError):
    def __init__(self, message: str):
        super().__init__(message, code="PROVIDER_AUTH_EXPIRED")

class ProviderTimeoutError(ProviderError):
    def __init__(self, message: str):
        super().__init__(message, code="PROVIDER_TIMEOUT")

class ProviderUpstreamError(ProviderError):
    def __init__(self, message: str):
        super().__init__(message, code="PROVIDER_UPSTREAM_ERROR")

class KeywordError(AppError):
    def __init__(self, message: str, code: str = "KEYWORD_ERROR"):
        super().__init__(message, code=code, status_code=502)

class KeywordAuthExpiredError(KeywordError):
    def __init__(self, message: str = "小红书聚光登录凭据已过期"):
        super().__init__(message, code="KEYWORD_AUTH_EXPIRED")

class KeywordUpstreamError(KeywordError):
    def __init__(self, message: str):
        super().__init__(message, code="KEYWORD_UPSTREAM_ERROR")

class KeywordTimeoutError(KeywordError):
    def __init__(self, message: str = "小红书聚光接口请求超时"):
        super().__init__(message, code="KEYWORD_TIMEOUT")

class KeywordInvalidResponseError(KeywordError):
    def __init__(self, message: str):
        super().__init__(message, code="KEYWORD_INVALID_RESPONSE")
