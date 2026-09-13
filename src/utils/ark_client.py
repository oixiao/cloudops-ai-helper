"""
大模型API调用客户端 — 多模型路由 + 自动降级 + 重试机制
支持：豆包大模型（主） → DeepSeek（备） → OpenAI（备） → Ollama（本地离线）
"""
import os
import json
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)

# ========== 加载 .env 配置文件 ==========
# 说明：本项目使用 python-dotenv 读取 .env 中的模型密钥。
# 由于 .env 位于项目根目录，而本模块可能在任意工作目录下被导入，
# 这里从当前文件位置向上逐级查找 .env，确保无论从哪里启动都能正确加载。
#
# 注意：在 pytest 环境下**跳过加载**。单元测试必须与外部网络隔离，
# 否则一旦配置了真实密钥，测试会真的请求大模型 API —— 既拖慢执行速度
# （实测 84 个用例从 3 秒劣化到 40 秒），又产生费用，还会因网络波动而失败。
# 测试环境中未配置密钥时，模块会自动走本地规则匹配，保证离线可跑。
import sys as _sys

_running_under_pytest = "pytest" in _sys.modules or bool(os.getenv("PYTEST_CURRENT_TEST"))

if not _running_under_pytest:
    try:
        from dotenv import load_dotenv

        _here = os.path.dirname(os.path.abspath(__file__))
        for _ in range(4):  # 最多向上查找 4 层：src/utils → src → 项目根
            _candidate = os.path.join(_here, ".env")
            if os.path.isfile(_candidate):
                load_dotenv(_candidate, override=False)
                break
            _parent = os.path.dirname(_here)
            if _parent == _here:  # 已到磁盘根目录，停止
                break
            _here = _parent
    except ImportError:  # 未安装 python-dotenv 时静默跳过，不影响系统环境变量方式
        pass

logger = logging.getLogger(__name__)


def _get_env_key(name: str) -> str:
    """读取环境变量中的密钥，并过滤掉 .env.example 里的占位符

    .env.example 中的示例值（如 your_ark_api_key_here）是非空字符串，
    若不过滤会被误判为"已配置"，导致请求先打到无效模型上白白重试。

    Args:
        name: 环境变量名

    Returns:
        str: 真实密钥；未配置或仍是占位符时返回空字符串
    """
    value = (os.getenv(name) or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    # 常见占位符特征：your_ 前缀、_here 后缀、xxxx 填充
    if lowered.startswith("your_") or lowered.endswith("_here") or "xxxx" in lowered:
        logger.warning(f"{name} 仍是占位符，已忽略该项配置")
        return ""
    return value


def _is_retryable_error(exc: BaseException) -> bool:
    """判断异常是否值得重试

    运维原则：区分**瞬时故障**与**永久故障**。
    - 值得重试：超时、连接失败、5xx 服务端错误、429 限流
    - 不该重试：401 密钥无效、403 无权限、404 地址错误（重试多少次都是同样结果，
      只会白白拖慢请求）

    Args:
        exc: 捕获到的异常

    Returns:
        bool: True 表示可以重试
    """
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status >= 500 or status == 429
    return False


class ModelProvider(Enum):
    ARK = "ark"           # 豆包大模型（火山引擎）
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    OLLAMA = "ollama"


@dataclass
class ModelConfig:
    """模型配置"""
    provider: ModelProvider
    api_key: str
    base_url: str
    model_id: str
    timeout: int = 60
    max_retries: int = 3


@dataclass
class ChatResponse:
    """统一聊天响应"""
    content: str
    model: str
    provider: str
    tokens_used: int = 0
    finish_reason: str = "stop"


class ArkClient:
    """多模型大语言模型调用客户端

    特性：
    - 多模型路由：豆包(主) → DeepSeek → OpenAI → Ollama
    - 自动降级：主模型失败时自动切换备选
    - 指数退避重试
    - 统一响应格式，屏蔽不同厂商API差异
    """

    # 各模型的 API 路径
    CHAT_PATH = {
        ModelProvider.ARK: "/chat/completions",
        ModelProvider.DEEPSEEK: "/chat/completions",
        ModelProvider.OPENAI: "/chat/completions",
        ModelProvider.OLLAMA: "/api/chat",
    }

    def __init__(self):
        self._models: List[ModelConfig] = []
        self._init_models()

    def _init_models(self):
        """初始化模型配置（按优先级排序）"""
        # 1. 豆包大模型（主模型）
        ark_key = _get_env_key("ARK_API_KEY")
        if ark_key:
            self._models.append(ModelConfig(
                provider=ModelProvider.ARK,
                api_key=ark_key,
                base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
                model_id=os.getenv("ARK_MODEL_ID", "ep-20240601000000-xxxxx"),
                timeout=60,
            ))

        # 2. DeepSeek（备选）
        ds_key = _get_env_key("DEEPSEEK_API_KEY")
        if ds_key:
            self._models.append(ModelConfig(
                provider=ModelProvider.DEEPSEEK,
                api_key=ds_key,
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
                model_id=os.getenv("DEEPSEEK_MODEL_ID", "deepseek-chat"),
                timeout=60,
            ))

        # 3. OpenAI（备选）
        oa_key = _get_env_key("OPENAI_API_KEY")
        if oa_key:
            self._models.append(ModelConfig(
                provider=ModelProvider.OPENAI,
                api_key=oa_key,
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                model_id=os.getenv("OPENAI_MODEL_ID", "gpt-4o-mini"),
                timeout=60,
            ))

        # 4. Ollama（本地离线兜底）
        ollama_url = _get_env_key("OLLAMA_BASE_URL")
        if ollama_url:
            self._models.append(ModelConfig(
                provider=ModelProvider.OLLAMA,
                api_key="",
                base_url=ollama_url,
                model_id=os.getenv("OLLAMA_MODEL_ID", "qwen2:7b"),
                timeout=120,
            ))

    @property
    def available_models(self) -> List[str]:
        """返回所有已配置的模型"""
        return [f"{m.provider.value}:{m.model_id}" for m in self._models]

    @property
    def is_available(self) -> bool:
        """是否有可用模型"""
        return len(self._models) > 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(_is_retryable_error),
        reraise=True,
    )
    async def _call_openai_compatible(
        self, config: ModelConfig, messages: List[Dict], temperature: float = 0.3
    ) -> ChatResponse:
        """调用兼容OpenAI格式的API（豆包、DeepSeek、OpenAI）"""
        url = f"{config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": config.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=config.timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        return ChatResponse(
            content=choice["message"]["content"],
            model=data.get("model", config.model_id),
            provider=config.provider.value,
            tokens_used=data.get("usage", {}).get("total_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def _call_ollama(
        self, config: ModelConfig, messages: List[Dict], temperature: float = 0.3
    ) -> ChatResponse:
        """调用Ollama API（格式不同于OpenAI）"""
        url = f"{config.base_url.rstrip('/')}/api/chat"
        body = {
            "model": config.model_id,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }

        async with httpx.AsyncClient(timeout=config.timeout) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()

        return ChatResponse(
            content=data["message"]["content"],
            model=data.get("model", config.model_id),
            provider=config.provider.value,
            tokens_used=data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
            finish_reason=data.get("done_reason", "stop"),
        )

    async def chat(
        self,
        user_message: str,
        system_prompt: str = "",
        temperature: float = 0.3,
    ) -> str:
        """发送聊天请求，自动选择可用模型并降级

        Args:
            user_message: 用户消息
            system_prompt: 系统提示词（可选）
            temperature: 温度参数（0-2）

        Returns:
            str: 模型回复的文本内容

        Raises:
            RuntimeError: 所有模型均不可用时抛出
        """
        if not self._models:
            raise RuntimeError("没有配置任何大模型！请设置 ARK_API_KEY 等环境变量。")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        last_error = None

        for config in self._models:
            try:
                logger.info(f"尝试调用 {config.provider.value}:{config.model_id} ...")

                if config.provider == ModelProvider.OLLAMA:
                    resp = await self._call_ollama(config, messages, temperature)
                else:
                    resp = await self._call_openai_compatible(config, messages, temperature)

                logger.info(
                    f"{config.provider.value}:{config.model_id} 调用成功 "
                    f"(tokens: {resp.tokens_used})"
                )
                return resp.content

            except Exception as e:
                logger.warning(
                    f"{config.provider.value}:{config.model_id} 调用失败: {e}，"
                    f"尝试下一个模型..."
                )
                last_error = e
                continue

        # 全部失败
        raise RuntimeError(
            f"所有模型调用均失败（共 {len(self._models)} 个）。"
            f"最后一个错误: {last_error}"
        )

    async def chat_structured(
        self,
        user_message: str,
        system_prompt: str = "",
        temperature: float = 0.3,
    ) -> dict:
        """发送聊天请求并解析为JSON

        Args:
            user_message: 用户消息
            system_prompt: 系统提示词
            temperature: 温度参数

        Returns:
            dict: 解析后的JSON对象
        """
        raw = await self.chat(user_message, system_prompt, temperature)
        # 清洗：去除markdown代码块包裹
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:]) if len(lines) > 1 else raw
            if raw.endswith("```"):
                raw = raw[:-3]
        return json.loads(raw)


# 全局单例
_ark_client: Optional[ArkClient] = None


def get_ark_client() -> ArkClient:
    """获取ArkClient全局单例"""
    global _ark_client
    if _ark_client is None:
        _ark_client = ArkClient()
    return _ark_client
