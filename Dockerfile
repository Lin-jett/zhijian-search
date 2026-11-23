FROM python:3.11-slim

WORKDIR /app

# 先装依赖（利用缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码
COPY backend ./backend
COPY data ./data
COPY evaluate.py ./evaluate.py

# 密钥一律运行时注入（docker run -e / compose environment），不打进镜像
ENV ZHIJIAN_DATA_MODE=offline \
    ZHIJIAN_LLM_MODE=mock \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    APP_WORKERS=2

EXPOSE 8000

# 容器内 0.0.0.0，由 compose/反代对外；--workers 多进程
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-access-log"]
