"""
Orchestrator 多Agent编排测试
"""
import pytest
import asyncio
from src.core.orchestrator import Orchestrator, AgentTask, OrchestrateResult, get_orchestrator


class TestAgentTask:
    """AgentTask数据类测试"""

    def test_agent_task_defaults(self):
        task = AgentTask(agent="log_analyzer", task="分析日志")
        assert task.agent == "log_analyzer"
        assert task.status == "pending"
        assert task.result is None
        assert task.start_time == ""

    def test_agent_task_with_result(self):
        task = AgentTask(
            agent="cmd_generator",
            task="生成命令",
            status="done",
            result={"command": "df -h"},
        )
        assert task.status == "done"
        assert task.result["command"] == "df -h"


class TestOrchestrateResult:
    """OrchestrateResult数据类测试"""

    def test_empty_result(self):
        result = OrchestrateResult()
        assert result.plan == []
        assert result.log_entries == []
        assert result.summary == ""


class TestOrchestrator:
    """Orchestrator核心逻辑测试"""

    def setup_method(self):
        self.orch = Orchestrator()

    def test_orchestrator_initialized(self):
        """测试Orchestrator正确初始化"""
        assert self.orch.cmd_gen is not None
        assert self.orch.log_analyzer is not None
        assert self.orch.script_gen is not None

    def test_local_intent_analysis_with_log(self):
        """测试本地意图分析—日志内容"""
        tasks = self.orch._local_intent_analysis(
            "ERROR Database connection timeout after 30000ms"
        )
        assert len(tasks) > 0
        agents = [t["agent"] for t in tasks]
        assert "log_analyzer" in agents

    def test_local_intent_analysis_with_command(self):
        """测试本地意图分析—命令需求"""
        tasks = self.orch._local_intent_analysis("怎么查看磁盘使用情况")
        assert len(tasks) > 0
        agents = [t["agent"] for t in tasks]
        assert "cmd_generator" in agents

    def test_local_intent_analysis_with_script(self):
        """测试本地意图分析—脚本需求"""
        tasks = self.orch._local_intent_analysis("写一个自动备份MySQL数据库的脚本")
        assert len(tasks) > 0
        agents = [t["agent"] for t in tasks]
        assert "script_generator" in agents

    def test_local_intent_analysis_empty_returns_default(self):
        """测试空输入至少返回一个默认任务"""
        tasks = self.orch._local_intent_analysis("hello")
        assert len(tasks) > 0

    def test_local_intent_analysis_complex_input(self):
        """测试复杂输入产生多个子任务"""
        tasks = self.orch._local_intent_analysis(
            "服务器CPU持续90%，dmesg日志显示OOM Killer杀了Java进程，"
            "帮我排查原因并写出自动恢复脚本"
        )
        assert len(tasks) >= 2  # 至少分配了日志分析 + 脚本生成

    def test_local_summary_with_tasks(self):
        """测试本地聚合生成摘要"""
        tasks = [
            AgentTask(
                agent="log_analyzer",
                task="分析日志",
                status="done",
                result={
                    "level": "fatal",
                    "error_type": "内存溢出(OOM)",
                    "summary": "检测到OOM错误",
                    "steps": ["步骤1", "步骤2"],
                },
            ),
            AgentTask(
                agent="cmd_generator",
                task="生成命令",
                status="done",
                result={
                    "command": "free -h",
                    "explanation": "查看内存",
                    "safety_level": "safe",
                },
            ),
        ]
        summary = self.orch._local_summary(tasks)
        assert "OOM" in summary
        assert len(summary) > 0

    def test_local_summary_empty(self):
        """测试空计划返回默认摘要"""
        summary = self.orch._local_summary([])
        assert len(summary) > 0

    @pytest.mark.asyncio
    async def test_execute_returns_valid_result(self):
        """测试完整执行流程"""
        result = await self.orch.execute("查看磁盘使用情况")
        assert isinstance(result, OrchestrateResult)
        assert len(result.plan) > 0
        assert len(result.log_entries) > 0
        assert result.summary is not None
        assert len(result.summary) > 0

    @pytest.mark.asyncio
    async def test_execute_with_log_content(self):
        """测试包含日志内容的执行"""
        result = await self.orch.execute(
            "ERROR Connection refused: connect to 10.0.0.1:3306, 帮我排查"
        )
        # 应该至少分配了log_analyzer
        agents = [t.agent for t in result.plan]
        assert "log_analyzer" in agents
        # 检查日志分析结果
        for t in result.plan:
            assert t.status in ["done", "failed"]

    @pytest.mark.asyncio
    async def test_execute_complex_scenario(self):
        """测试复杂运维场景"""
        result = await self.orch.execute(
            "服务器CPU持续90%，dmesg日志显示 Out of memory: Kill process 12345 (java)，"
            "应用响应超时，帮我全面排查并给出解决方案"
        )
        assert len(result.plan) >= 2
        assert len(result.summary) > 0

    @pytest.mark.asyncio
    async def test_all_agents_complete(self):
        """测试所有Agent都完成"""
        result = await self.orch.execute(
            "nginx错误日志出现大量502，帮我分析原因并写一个自动重启后端服务的脚本"
        )
        for task in result.plan:
            assert task.status in ["done", "failed"], \
                f"{task.agent} 状态应为done/failed，实际为{task.status}"


class TestOrchestratorSingleton:
    """Orchestrator单例测试"""

    def test_get_orchestrator_returns_same_instance(self):
        orch1 = get_orchestrator()
        orch2 = get_orchestrator()
        assert orch1 is orch2
