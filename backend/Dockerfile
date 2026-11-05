# SteamMate 백엔드 운영 이미지 (9단계). 실행: 저장소 루트에서 docker compose -f compose.prod.yml up --build
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations

# 루트가 아닌 사용자로 실행
RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
# 워커 1개: 차트 수집기·메모리 캐시·GPU 직렬화 잠금이 한 프로세스를 전제로 한다.
# --proxy-headers: 앞단(Next 프록시)이 보낸 X-Forwarded-* 를 신뢰한다(컨테이너 내부망에서만 접근).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
