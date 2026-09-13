"""
多Agent协作编排器 — Orchestrator
意图分析 → 任务拆解 → 并行调度 → 结果聚合
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from src.core.cmd_generator import CmdGenerator
from src.core.log_analyzer import LogAnalyzer
from src.core.script_generator import ScriptGenerator
from src.utils.ark_client import ArkClient, get_ark_client

logger = logging.getLogger("cloudops.orchestrator")


@dataclass
class AgentTask:
    """子任务定义"""
    agent: str          # "log_analyzer" | "cmd_generator" | "script_generator"
    task: str           # 该 Agent 要执行的具体内容
    status: str = "pending"   # pending | running | done | failed
    result: Any = None
    start_time: str = ""
    end_time: str = ""


@dataclass
class OrchestrateResult:
    """编排结果"""
    plan: List[AgentTask] = field(default_factory=list)
    log_entries: List[Dict[str, str]] = field(default_factory=list)
    summary: str = ""


class Orchestrator:
    """多 Agent 协作编排器

    核心流程：
    1. 意图分析 → 用大模型分析用户问题，拆解为子任务
    2. 并行调度 → asyncio.gather 并行执行子 Agent
    3. 结果聚合 → 整合所有 Agent 结果，生成诊断报告
    """

    INTENT_PROMPT = """你是一个任务调度专家。用户描述了一个运维问题，请分析并拆解为子任务。

你需要从以下三个 Agent 中选择合适的来处理（可以用一个或多个）：

- log_analyzer: 分析日志内容，识别异常等级和错误类型
- cmd_generator: 根据需求生成 Linux / Docker 运维命令
- script_generator: 生成可运行的 Shell/Python 修复脚本

返回格式（纯JSON，不要其他内容）：
{
  "tasks": [
    {"agent": "log_analyzer", "task": "分析这段日志中的异常..."},
    {"agent": "cmd_generator", "task": "生成排查CPU高的命令..."}
  ]
}

如果用户输入中包含日志内容，优先分配给 log_analyzer。
如果涉及具体操作需求，分配给 cmd_generator。
如果需要自动化修复，分配给 script_generator。
"""

    SUMMARY_PROMPT = """你是一个运维专家。以下是多个分析结果，请整合成一份简洁的诊断报告。

格式要求：
1. 先给出一句话诊断结论（📋 开头）
2. 按优先级排序列出建议操作（每条一行，数字编号）
3. 如果问题严重，首先给出止血措施
4. 使用通俗易懂的语言

各Agent分析结果：
{agent_results}
"""

    def __init__(self):
        self.cmd_gen = CmdGenerator()
        self.log_analyzer = LogAnalyzer()
        self.script_gen = ScriptGenerator()
        self.ark: Optional[ArkClient] = None
        self._init_ark()

    def _init_ark(self):
        """尝试初始化大模型客户端"""
        try:
            self.ark = get_ark_client()
            if self.ark.is_available:
                self.cmd_gen.use_ai = True
                self.cmd_gen.ark_client = self.ark
                self.log_analyzer.use_ai = True
                self.log_analyzer.ark_client = self.ark
                self.script_gen.use_ai = True
                self.script_gen.ark_client = self.ark
                logger.info("Orchestrator：AI模式已启用")
            else:
                logger.info("Orchestrator：使用本地规则模式")
        except Exception as e:
            logger.warning(f"Orchestrator：AI初始化失败 ({e})，使用本地规则模式")

    async def execute(self, user_input: str) -> OrchestrateResult:
        """执行多 Agent 协作流程

        Args:
            user_input: 用户的运维问题描述

        Returns:
            OrchestrateResult: 包含任务计划、执行日志和诊断报告
        """
        result = OrchestrateResult()

        # 步骤 1：意图分析 → 拆解任务
        tasks = await self._analyze_intent(user_input)

        for t in tasks:
            agent_task = AgentTask(
                agent=t.get("agent", ""),
                task=t.get("task", ""),
            )
            result.plan.append(agent_task)
            result.log_entries.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "agent": "🎯 总指挥",
                "message": f"拆解任务 → {t['agent']}: {t['task'][:50]}..."
            })

        if not result.plan:
            # 无法拆解时：至少使用全部三个Agent进行尝试
            result.log_entries.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "agent": "🎯 总指挥",
                "message": "无法精确拆解，启动全部Agent协同分析..."
            })
            result.plan = [
                AgentTask(agent="log_analyzer", task=user_input),
                AgentTask(agent="cmd_generator", task=user_input),
                AgentTask(agent="script_generator", task=user_input),
            ]

        # 步骤 2：并行调度所有子 Agent
        async def run_agent(task_item: AgentTask):
            task_item.status = "running"
            task_item.start_time = datetime.now().strftime("%H:%M:%S")
            try:
                if task_item.agent == "log_analyzer":
                    # 只调用一次 analyze()，避免重复请求大模型 API
                    r = self.log_analyzer.analyze(task_item.task)
                    task_item.result = {
                        "level": r.level,
                        "error_type": r.error_type,
                        "summary": r.summary,
                        "steps": r.steps,
                    }
                elif task_item.agent == "cmd_generator":
                    r = self.cmd_gen.generate(task_item.task)
                    task_item.result = {
                        "command": r.command,
                        "explanation": r.explanation,
                        "safety_level": r.safety_level,
                    }
                elif task_item.agent == "script_generator":
                    r = self.script_gen.generate(task_item.task)
                    task_item.result = {
                        "script": r.script,
                        "language": r.language,
                        "description": r.description,
                    }
                else:
                    task_item.result = {"error": f"未知Agent: {task_item.agent}"}
                task_item.status = "done"
            except Exception as e:
                task_item.status = "failed"
                task_item.result = {"error": str(e)}
                logger.error(f"Agent {task_item.agent} 执行失败: {e}")

            task_item.end_time = datetime.now().strftime("%H:%M:%S")
            result.log_entries.append({
                "time": task_item.end_time,
                "agent": _agent_icon(task_item.agent),
                "message": f"状态: {'✅ 完成' if task_item.status == 'done' else '❌ 失败'}",
            })
            return task_item

        # 并行执行所有子任务
        await asyncio.gather(*[run_agent(t) for t in result.plan])

        # 步骤 3：聚合结果 → 生成诊断报告
        agent_results_str = "\n".join([
            f"[{_agent_icon(t.agent)} {t.agent}] {json.dumps(t.result, ensure_ascii=False, indent=2)[:500]}"
            for t in result.plan
        ])

        if agent_results_str and self.ark and self.ark.is_available:
            try:
                raw = await self.ark.chat(
                    self.SUMMARY_PROMPT.format(agent_results=agent_results_str)
                )
                result.summary = raw
                result.log_entries.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "agent": "🎯 总指挥",
                    "message": "✅ 聚合完成，生成诊断报告",
                })
            except Exception as e:
                logger.warning(f"聚合失败: {e}")
                result.summary = self._local_summary(result.plan)
        else:
            result.summary = self._local_summary(result.plan)

        return result

    async def _analyze_intent(self, user_input: str) -> List[dict]:
        """用大模型分析用户意图，拆解为子任务"""
        # 简单关键词拆解（无AI时的本地策略）
        tasks = self._local_intent_analysis(user_input)

        # 如果有AI，尝试用大模型做更精准的拆解
        if self.ark and self.ark.is_available:
            try:
                full_prompt = f"{self.INTENT_PROMPT}\n\n用户输入：{user_input}"
                raw = await self.ark.chat(full_prompt)
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
                ai_tasks = json.loads(raw).get("tasks", [])
                if ai_tasks:
                    tasks = ai_tasks
                    logger.info(f"AI拆解出 {len(tasks)} 个子任务")
            except Exception as e:
                logger.warning(f"AI意图分析失败，使用本地策略：{e}")

        return tasks

    def _local_intent_analysis(self, user_input: str) -> List[dict]:
        """本地意图分析（基于关键词，无需AI）"""
        tasks = []
        user_lower = user_input.lower()

        # 检测日志相关内容
        log_keywords = ["日志", "log", "error", "错误", "报错", "exception", "异常",
                        "traceback", "oom", "out of memory", "fail", "失败"]
        if any(kw in user_lower for kw in log_keywords):
            tasks.append({
                "agent": "log_analyzer",
                "task": f"分析以下内容中的异常：{user_input[:200]}"
            })

        # 检测操作/命令需求
        cmd_keywords = ["怎么", "如何", "命令", "查看", "检查", "排查", "配置",
                        "安装", "部署", "cmd", "command", "how to"]
        if any(kw in user_lower for kw in cmd_keywords):
            tasks.append({
                "agent": "cmd_generator",
                "task": f"生成以下需求的运维命令：{user_input[:200]}"
            })

        # 检测脚本/自动化需求
        script_keywords = ["脚本", "自动", "批量", "定时", "监控", "备份",
                           "script", "automate", "cron", "schedule"]
        if any(kw in user_lower for kw in script_keywords):
            tasks.append({
                "agent": "script_generator",
                "task": f"生成以下需求的运维脚本：{user_input[:200]}"
            })

        # 如果完全没有匹配，默认至少分配一个
        if not tasks:
            # 判断最可能的Agent
            if len(user_input) > 500:  # 长文本 → 很可能是日志
                tasks.append({"agent": "log_analyzer", "task": user_input[:200]})
            else:
                tasks.append({"agent": "cmd_generator", "task": user_input})

        return tasks

    def _local_summary(self, plan: List[AgentTask]) -> str:
        """本地聚合（无AI时），将各Agent结果简单合并"""
        lines = ["📋 诊断汇总（本地模式）\n"]

        for t in plan:
            if t.status != "done" or not t.result:
                continue
            icon = _agent_icon(t.agent)
            lines.append(f"**{icon} {t.agent}**：")

            if t.agent == "log_analyzer":
                lines.append(f"- 日志等级：{t.result.get('level', 'N/A')}")
                lines.append(f"- 错误类型：{t.result.get('error_type', 'N/A')}")
                lines.append(f"- 摘要：{t.result.get('summary', 'N/A')}")
                steps = t.result.get("steps", [])
                if steps:
                    lines.append("- 排查建议：")
                    for i, step in enumerate(steps[:5], 1):
                        lines.append(f"  {i}. {step}")

            elif t.agent == "cmd_generator":
                lines.append(f"- 命令：`{t.result.get('command', 'N/A')[:200]}`")
                lines.append(f"- 说明：{t.result.get('explanation', 'N/A')[:200]}")
                lines.append(f"- 安全等级：{t.result.get('safety_level', 'N/A')}")

            elif t.agent == "script_generator":
                lines.append(f"- 语言：{t.result.get('language', 'N/A')}")
                lines.append(f"- 说明：{t.result.get('description', 'N/A')[:200]}")

            lines.append("")

        return "\n".join(lines) if len(lines) > 1 else "📋 诊断报告：所有Agent均未能产生有效结果。建议提供更详细的问题描述。"


def _agent_icon(agent_name: str) -> str:
    """Agent 图标映射"""
    icons = {
        "log_analyzer": "🔍",
        "cmd_generator": "⚙️",
        "script_generator": "📝",
    }
    return icons.get(agent_name, "🤖")


# 全局单例
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """获取Orchestrator全局单例"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
