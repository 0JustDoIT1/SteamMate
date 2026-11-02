import logging
import re

# httpx 등은 요청 URL을 로그로 남기므로 Steam API 키(?key=...)가 노출될 수 있다.
_KEY_PARAM = re.compile(r"(?i)\b(key|api_key|apikey|access_token)=([^&\s\"']+)")


def mask_secrets(text: str, secrets: tuple[str, ...] = ()) -> str:
    text = _KEY_PARAM.sub(r"\1=***", text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


class SecretMaskingFilter(logging.Filter):
    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._secrets = secrets

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = mask_secrets(message, self._secrets)
        if masked != message:
            record.msg = masked
            record.args = None
        return True


def configure_logging(secrets: tuple[str, ...] = ()) -> None:
    """루트 로거의 모든 핸들러에 마스킹 필터를 단다."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
    masking = SecretMaskingFilter(secrets)
    for handler in root.handlers:
        if not any(isinstance(f, SecretMaskingFilter) for f in handler.filters):
            handler.addFilter(masking)
