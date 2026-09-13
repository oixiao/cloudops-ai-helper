"""
CloudOps AI Helper — API 路由定义
RESTful 接口：命令生成、日志分析、脚本生成、多Agent协作
"""
import logging
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.core.cmd_generator import CmdGenerator
from src.core.log_analyzer import LogAnalyzer
from src.core.script_generator import ScriptGenerator
from src.core.orchestrator import Orchestrator, get_orchestrator
from src.utils.ark_client import get_ark_client

logger = logging.getLogger("cloudops")

router = APIRouter()

# ========== 单例服务 ==========
_cmd_gen: CmdGenerator = None
_log_analyzer: LogAnalyzer = None
_script_gen: ScriptGenerator = None


def get_cmd_generator() -> CmdGenerator:
    global _cmd_gen
    if _cmd_gen is None:
        client = get_ark_client()
        _cmd_gen = CmdGenerator(use_ai=client.is_available, ark_client=client)
    return _cmd_gen


def get_log_analyzer() -> LogAnalyzer:
    global _log_analyzer
    if _log_analyzer is None:
        client = get_ark_client()
        _log_analyzer = LogAnalyzer(use_ai=client.is_available, ark_client=client)
    return _log_analyzer


def get_script_generator() -> ScriptGenerator:
    global _script_gen
    if _script_gen is None:
        client = get_ark_client()
        _script_gen = ScriptGenerator(use_ai=client.is_available, ark_client=client)
    return _script_gen


# ========== 通用响应模型 ==========
class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: dict | list | str | None = None
    model: str = "local"


# ========== 请求模型 ==========
class CmdGenerateRequest(BaseModel):
    input: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="运维需求描述（自然语言）",
        examples=["查看磁盘使用情况", "查找大于100MB的文件"],
    )


class LogAnalyzeRequest(BaseModel):
    input: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="日志文本内容",
        examples=["2024-06-01 ERROR Database connection timeout"],
    )


class ScriptGenerateRequest(BaseModel):
    input: str = Field(
        ...,
        min_length=1,
        max_length=3000,
        description="运维脚本需求描述",
        examples=["备份MySQL数据库并压缩", "监控CPU使用率超过80%时发送告警"],
    )


class OrchestrateRequest(BaseModel):
    input: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="运维问题完整描述（可包含日志+需求）",
        examples=["服务器CPU持续90%，dmesg日志显示OOM Killer杀掉了Java进程，帮我排查"],
    )


# ========== 健康检查 ==========
@router.get("/api/health")
async def health_check():
    """服务健康检查"""
    client = get_ark_client()
    return ApiResponse(
        data={
            "status": "healthy",
            "version": "2.0.0",
            "ai_available": client.is_available,
            "ai_models": client.available_models,
        },
        model="system",
    )


# ========== 命令生成 ==========
@router.post("/api/cmd/generate")
async def cmd_generate(request: CmdGenerateRequest):
    """
    运维命令生成接口

    根据自然语言描述生成对应的 Linux/运维命令。
    返回命令文本、参数解释、安全等级。
    """
    gen = get_cmd_generator()
    result = gen.generate(request.input)

    return ApiResponse(
        data={
            "command": result.command,
            "explanation": result.explanation,
            "safety_level": result.safety_level,
        },
        model="ai" if gen.use_ai else "local",
    )


# ========== 日志分析 ==========
@router.post("/api/log/analyze")
async def log_analyze(request: LogAnalyzeRequest):
    """
    日志智能分析接口

    分析日志内容，自动识别异常等级、错误类型，
    并给出分步排查建议。
    """
    analyzer = get_log_analyzer()
    result = analyzer.analyze(request.input)

    return ApiResponse(
        data={
            "level": result.level,
            "error_type": result.error_type,
            "summary": result.summary,
            "steps": result.steps,
            "confidence": result.confidence,
        },
        model="ai" if analyzer.use_ai else "local",
    )


# ========== 脚本生成 ==========
@router.post("/api/script/generate")
async def script_generate(request: ScriptGenerateRequest):
    """
    运维脚本生成接口

    根据运维场景描述生成可运行的Shell/Python脚本，
    包含使用说明和注意事项。
    """
    gen = get_script_generator()
    result = gen.generate(request.input)

    return ApiResponse(
        data={
            "script": result.script,
            "language": result.language,
            "description": result.description,
            "warnings": result.warnings,
        },
        model="ai" if gen.use_ai else "local",
    )


# ========== 多Agent协作（核心亮点接口） ==========
@router.post("/api/orchestrate")
async def orchestrate(request: OrchestrateRequest):
    """
    多Agent协作编排接口 🔥

    由Orchestrator总指挥自动分析用户问题，
    拆解为子任务，并行调度三个Agent协同工作，
    最后聚合结果生成诊断报告。
    """
    orch = get_orchestrator()
    result = await orch.execute(request.input)

    return ApiResponse(
        data={
            "plan": [
                {
                    "agent": t.agent,
                    "task": t.task,
                    "status": t.status,
                    "result": t.result,
                }
                for t in result.plan
            ],
            "log_entries": result.log_entries,
            "summary": result.summary,
        },
        model="orchestrator",
    )
