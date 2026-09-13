# ============================================
# CloudOps AI Helper — Dockerfile (多阶段构建)
# ============================================

# --- Stage 1: 构建阶段 ---
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装构建依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Stage 2: 运行阶段 ---
FROM python:3.11-slim AS runtime

WORKDIR /app

# 创建非root用户
RUN groupadd -r cloudops && useradd -r -g cloudops cloudops

# 从构建阶段复制已安装的包
COPY --from=builder /root/.local /home/cloudops/.local

# 复制项目代码
COPY --chown=cloudops:cloudops . .

# 创建数据目录
RUN mkdir -p /app/data /app/logs && chown -R cloudops:cloudops /app/data /app/logs

# 设置环境变量
ENV PATH=/home/cloudops/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 切换非root用户
USER cloudops

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
