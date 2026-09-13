"""
CloudOps AI Helper — FastAPI 主入口
统一响应格式、全局异常处理、中间件、CORS配置
"""
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse

from src.api.routes import router
from src.utils.ark_client import get_ark_client

# ========== 日志配置 ==========
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cloudops")


# ========== 应用生命周期 ==========
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的资源管理"""
    logger.info("=" * 50)
    logger.info("CloudOps AI Helper 启动中...")

    # 初始化大模型客户端
    client = get_ark_client()
    if client.is_available:
        logger.info(f"可用模型: {client.available_models}")
    else:
        logger.warning("未配置任何大模型！将使用本地规则匹配模式。")
        logger.warning("设置 ARK_API_KEY 环境变量以启用AI能力。")

    logger.info("=" * 50)
    yield
    logger.info("CloudOps AI Helper 关闭。")


# ========== 创建FastAPI应用 ==========
app = FastAPI(
    title="CloudOps AI Helper",
    description="多Agent协作的智能运维助手 — 命令生成、日志分析、脚本生成",
    version="2.0.0",
    lifespan=lifespan,
)

# ========== CORS 配置 ==========
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== 请求日志中间件 ==========
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录每个请求的输入、耗时、状态码"""
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    logger.info(
        f"{request.method} {request.url.path} "
        f"→ {response.status_code} "
        f"({duration:.3f}s)"
    )
    response.headers["X-Process-Time"] = str(round(duration, 4))
    return response


# ========== 全局异常处理 ==========
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """参数校验异常"""
    return JSONResponse(
        status_code=400,
        content={
            "code": 400,
            "message": str(exc),
            "data": None,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """未知异常兜底"""
    logger.error(f"未捕获的异常: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": f"服务器内部错误: {type(exc).__name__}",
            "data": None,
        },
    )


# ========== 注册路由 ==========
app.include_router(router)


# ========== 根路径重定向到前端 ==========
@app.get("/")
async def root():
    """重定向到前端主页面"""
    return RedirectResponse(url="/static/index.html")

# ========== 静态文件（前端页面） ==========
import os
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")
    logger.info(f"静态文件目录已挂载: {static_dir}")


# ========== 直接运行入口 ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
