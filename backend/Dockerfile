FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Seoul

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        # 산출물 PDF(weasyprint) 런타임 의존성. weasyprint 53+ 는 cairo/gdk-pixbuf
        # 없이 Pango 만 있으면 된다. libharfbuzz-subset0 은 폰트 서브셋용이다.
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz-subset0 \
        # PDF 안의 한글 폰트. 없으면 한글이 네모(□)로 나온다.
        fonts-nanum \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY ./app ./app
COPY alembic.ini .
COPY ./migrations ./migrations
# 파인튜닝 LoRA 어댑터(각 27MB). 베이스 모델은 여기 없다 — 첫 실행 때 HF 에서
# 받아 캐시된다. 자세한 내용은 adapters/README.md 참고.
COPY ./adapters ./adapters

RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
