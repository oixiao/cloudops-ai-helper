---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 0362637170925008963f5da69832c48d_35d06ab479f411f1b95a525400d9a7a1
    ReservedCode1: naCPUF6FcX5SVrtsOAn3TqsjIbMKzhj0A5a3pxFlZSqp+7FPZ8VNFPc9hx1i7JaeyByO+/DgFNDEq6Y1oyvacvHpJEI1U/Mn33H0Nf/3VK9zCE4/LDTzhZu8otLJzdyygkG2aKlRZzzg9LipwFoH7ExFcHescbF9EkGLQ6mm7up7PdyR9VUbCk78nfE=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 0362637170925008963f5da69832c48d_35d06ab479f411f1b95a525400d9a7a1
    ReservedCode2: naCPUF6FcX5SVrtsOAn3TqsjIbMKzhj0A5a3pxFlZSqp+7FPZ8VNFPc9hx1i7JaeyByO+/DgFNDEq6Y1oyvacvHpJEI1U/Mn33H0Nf/3VK9zCE4/LDTzhZu8otLJzdyygkG2aKlRZzzg9LipwFoH7ExFcHescbF9EkGLQ6mm7up7PdyR9VUbCk78nfE=
---

# CloudOps AI — 多 Agent 协作升级方案

> 基于现有 CloudOps AI 运维助手的架构升级，将三个独立功能模块改造为多 Agent 协作系统。
> 面向场景：字节跳动校园合伙人申请作品展示。

---

## 一、升级目标

| 现状 | 目标 |
|------|------|
| 三个功能 Tab 各自独立 | 一个 Orchestrator 总指挥调度三个 Agent 并行协作 |
| 用户需要手动选择用哪个功能 | 用户描述问题，系统自动拆解并调度 |
| 无协作过程可视化 | 前端看板实时展示任务拆解、Agent 状态、执行日志 |

**核心原则**：最小改动，最大效果。不改动现有的 CmdGenerator、LogAnalyzer、ScriptGenerator 核心代码，仅新增 Orchestrator 编排层和协作看板页面。

---

## 二、升级后架构

```
用户输入：「服务器CPU 90%，日志有OOM，帮我排查」
                │
                ▼
┌─────────────────────────────────────┐
│         Orchestrator 总指挥          │  ← 新增
│   1. 意图分析 → 拆解为子任务          │
│   2. 并行调度子 Agent                │
│   3. 聚合结果 → 生成诊断报告          │
└──────┬──────────┬──────────┬────────┘
       │          │          │
       ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ 🔍 分析   │ │ ⚙️ 命令   │ │ 📝 脚本   │  ← 已有，不动
│LogAnalyzer│ │CmdGenerator│ │ScriptGenerator│
└──────────┘ └──────────┘ └──────────┘
```

---

## 三、新增代码清单

| 文件 | 功能 | 预估行数 |
|------|------|---------|
| `src/core/orchestrator.py` | 意图分析 + 任务拆解 + 并行调度 + 结果聚合 | ~100 行 |
| `src/api/routes.py` | 新增 `POST /api/orchestrate` 接口 | ~40 行 |
| `static/orchestrate.html` | 协作工作台前端页面 | ~200 行 |
| `static/css/orchestrate.css` | 看板动画与 Agent 卡片样式 | ~80 行 |
| `static/js/orchestrate.js` | 前端 SSE/轮询 + 看板渲染逻辑 | ~120 行 |

---

## 四、核心模块设计

### 4.1 Orchestrator（`src/core/orchestrator.py`）

```python
import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass, field

from src.core.cmd_generator import CmdGenerator
from src.core.log_analyzer import LogAnalyzer
from src.core.script_generator import ScriptGenerator
from src.utils.ark_client import ArkClient


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
    plan: List[AgentTask]
    log_entries: List[Dict[str, str]] = field(default_factory=list)
    summary: str = ""


class Orchestrator:
    """多 Agent 协作编排器"""

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
1. 先给出一句话诊断结论
2. 列出按优先级排序的建议操作（每条一行，编号）

各Agent分析结果：
{agent_results}
"""

    def __init__(self):
        self.cmd_gen = CmdGenerator()
        self.log_analyzer = LogAnalyzer()
        self.script_gen = ScriptGenerator()
        self.ark = ArkClient()

    async def execute(self, user_input: str) -> OrchestrateResult:
        """执行多 Agent 协作流程"""
        result = OrchestrateResult(plan=[])

        # 步骤 1：意图分析 → 拆解任务
        intent_result = await self._analyze_intent(user_input)
        tasks = intent_result.get("tasks", [])

        for t in tasks:
            agent_task = AgentTask(
                agent=t["agent"],
                task=t["task"]
            )
            result.plan.append(agent_task)
            result.log_entries.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "agent": "总指挥",
                "message": f"拆解任务 → {t['agent']}: {t['task'][:30]}..."
            })

        # 步骤 2：并行调度所有子 Agent
        async def run_agent(task_item: AgentTask):
            task_item.status = "running"
            task_item.start_time = datetime.now().strftime("%H:%M:%S")
            try:
                if task_item.agent == "log_analyzer":
                    task_item.result = await self.log_analyzer.analyze(task_item.task)
                elif task_item.agent == "cmd_generator":
                    task_item.result = await self.cmd_gen.generate(task_item.task)
                elif task_item.agent == "script_generator":
                    task_item.result = await self.script_gen.generate(task_item.task)
                task_item.status = "done"
            except Exception as e:
                task_item.status = "failed"
                task_item.result = {"error": str(e)}
            task_item.end_time = datetime.now().strftime("%H:%M:%S")
            result.log_entries.append({
                "time": task_item.end_time,
                "agent": task_item.agent,
                "message": f"状态: {task_item.status}"
            })
            return task_item

        # 并行执行
        await asyncio.gather(*[run_agent(t) for t in result.plan])

        # 步骤 3：聚合结果
        agent_results_str = "\n".join([
            f"[{t.agent}] {json.dumps(t.result, ensure_ascii=False)}"
            for t in result.plan
        ])
        if agent_results_str:
            raw = await self.ark.chat(self.SUMMARY_PROMPT.format(
                agent_results=agent_results_str
            ))
            result.summary = raw
            result.log_entries.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "agent": "总指挥",
                "message": "聚合完成，生成诊断报告"
            })

        return result

    async def _analyze_intent(self, user_input: str) -> dict:
        """用大模型分析用户意图，拆解为子任务"""
        full_prompt = f"{self.INTENT_PROMPT}\n\n用户输入：{user_input}"
        raw = await self.ark.chat(full_prompt)
        # 清洗 JSON
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(raw)
```

### 4.2 API 接口（`src/api/routes.py` 新增部分）

```python
from pydantic import BaseModel, Field

# --- 新增数据模型 ---

class OrchestrateRequest(BaseModel):
    input: str = Field(..., min_length=1, max_length=5000,
                       description="用户的运维问题描述")

class OrchestrateResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: dict = {}

# --- 新增路由 ---

@router.post("/api/orchestrate", response_model=OrchestrateResponse)
async def orchestrate(request: OrchestrateRequest):
    """多 Agent 协作入口"""
    orchestrator = get_orchestrator()  # 单例获取
    result = await orchestrator.execute(request.input)

    return OrchestrateResponse(
        data={
            "plan": [
                {
                    "agent": t.agent,
                    "task": t.task,
                    "status": t.status,
                    "result": t.result
                }
                for t in result.plan
            ],
            "log_entries": result.log_entries,
            "summary": result.summary
        }
    )
```

---

## 五、前端协作看板设计

### 5.1 页面结构（`static/orchestrate.html`）

```
┌──────────────────────────────────────────────────────────┐
│  🧠 多 Agent 协作工作台                                   │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─ 任务输入 ───────────────────────────────────────┐   │
│  │  [                                                    │   │
│  │    文本输入框                                        │   │
│  │    示例：服务器CPU持续90%，dmesg日志显示OOM...     │   │
│  │  ]                                   [提交任务]      │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─ Agent 状态面板 ─────────────────────────────────┐   │
│  │                                                    │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐          │   │
│  │  │ 🎯 总指挥  │ │ 🔍 分析   │ │ ⚙️ 命令   │          │   │
│  │  │ 任务拆解  │ │ LogAnalyzer│ │CmdGenerator│          │   │
│  │  │ ✅ 完成   │ │ ⏳ 进行中 │ │ ⏸ 等待中 │          │   │
│  │  └──────────┘ └──────────┘ └──────────┘          │   │
│  │                                                    │   │
│  │                  ┌──────────┐                      │   │
│  │                  │ 📝 脚本   │                      │   │
│  │                  │ScriptGenerator│                   │   │
│  │                  │ ⏸ 等待中 │                      │   │
│  │                  └──────────┘                      │   │
│  └────────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─ 执行日志（实时滚动）────────────────────────────┐   │
│  │ [14:32:01] 🎯 总指挥：检测到 OOM + 高CPU →      │   │
│  │            拆解为3个子任务                       │   │
│  │ [14:32:02] 🔍 日志分析Agent：开始分析日志...    │   │
│  │ [14:32:03] ⚙️ 命令Agent：开始生成排查命令...    │   │
│  │ [14:32:05] 🔍 日志分析Agent：✅ 完成 → Java堆溢出│   │
│  │ [14:32:06] ⚙️ 命令Agent：✅ 完成 → jmap/jstack  │   │
│  │ [14:32:07] 📝 脚本Agent：✅ 完成 → 清理脚本     │   │
│  │ [14:32:08] 🎯 总指挥：聚合完成，生成诊断报告     │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─ 诊断报告 ───────────────────────────────────────┐   │
│  │                                                    │   │
│  │  📋 诊断结论：Java堆内存溢出导致CPU飙升            │   │
│  │                                                    │   │
│  │  建议操作：                                        │   │
│  │  1. 执行 jmap -heap <pid> 查看堆使用情况           │   │
│  │  2. 执行 jstack <pid> 排查是否存在死锁              │   │
│  │  3. 调整 JVM 参数 -Xmx/-Xms 后重启服务             │   │
│  │                                                    │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### 5.2 前端技术方案

- **通信方式**：由于 Agent 执行耗时较短（通常 3-8 秒），采用普通 POST 请求 + Loading 动画即可，无需 SSE/WebSocket
- **Agent 卡片动画**：CSS `@keyframes` 实现状态切换动画（pending→running 脉冲动画，done→绿色对勾）
- **执行日志**：收到响应后逐条渲染，配合 `scroll-behavior: smooth` 自动滚动到最新
- **诊断报告**：Markdown 渲染，支持代码块语法高亮

### 5.3 关键 CSS 动画（`static/css/orchestrate.css`）

```css
/* Agent 卡片基础样式 */
.agent-card {
    width: 180px;
    padding: 16px;
    border-radius: 12px;
    text-align: center;
    transition: all 0.3s ease;
    border: 2px solid #e0e0e0;
    background: #fafafa;
}

/* 运行中脉冲动画 */
.agent-card.running {
    border-color: #4A90D9;
    background: #EBF3FC;
    animation: pulse 1.5s infinite;
}

@keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(74, 144, 217, 0.4); }
    50% { box-shadow: 0 0 0 12px rgba(74, 144, 217, 0); }
}

/* 完成状态 */
.agent-card.done {
    border-color: #52C41A;
    background: #F6FFED;
}

/* 失败状态 */
.agent-card.failed {
    border-color: #FF4D4F;
    background: #FFF2F0;
}

/* 日志容器 */
.log-panel {
    max-height: 240px;
    overflow-y: auto;
    background: #1E1E1E;
    color: #D4D4D4;
    font-family: 'Consolas', monospace;
    padding: 12px;
    border-radius: 8px;
}

.log-entry {
    padding: 4px 0;
    font-size: 13px;
    line-height: 1.5;
}

.log-entry .time { color: #569CD6; }
.log-entry .agent-tag { color: #4EC9B0; font-weight: bold; }
.log-entry .message { color: #D4D4D4; }
```

---

## 六、实施步骤

### 第 1 天：搭建 Orchestrator 骨架

- [ ] 创建 `src/core/orchestrator.py`
- [ ] 实现 `Orchestrator` 类的基本结构（属性初始化、execute 方法签名）
- [ ] 实现 `_analyze_intent`：调用大模型做任务拆解
- [ ] 编写单元测试 `tests/test_orchestrator.py`：Mock ArkClient，验证任务拆解逻辑

### 第 2 天：实现并行调度与结果聚合

- [ ] 实现 `asyncio.gather` 并行调度三个子 Agent
- [ ] 实现 `_generate_summary`：聚合结果生成诊断报告
- [ ] 完善 `AgentTask` 状态流转和日志记录
- [ ] 补全单元测试：验证并行调度、失败降级、空输入边界

### 第 3 天：新增 API 接口

- [ ] 在 `src/api/routes.py` 新增 `POST /api/orchestrate`
- [ ] 定义 `OrchestrateRequest` / `OrchestrateResponse` Pydantic 模型
- [ ] 编写接口测试：正常场景、空输入、超长输入
- [ ] 在 `src/api/main.py` 中注册 Orchestrator 单例

### 第 4 天：前端协作看板

- [ ] 创建 `static/orchestrate.html`（复用现有 Bootstrap5 框架）
- [ ] 实现 Agent 状态卡片区（2×2 网格布局）
- [ ] 实现执行日志面板（深色终端风格，逐条渲染）
- [ ] 实现诊断报告展示区（Markdown 渲染）
- [ ] 编写 `static/css/orchestrate.css`（动画 + 布局）

### 第 5 天：联调与优化

- [ ] 前后端联调，保证响应格式对齐
- [ ] 添加 Loading 状态和错误提示
- [ ] 在首页导航栏新增「协作工作台」Tab 入口
- [ ] 优化移动端响应式布局
- [ ] 录一段 2 分钟的演示视频（申请时用）

---

## 七、精简后的路线图

相比原迭代路线图，砍掉所有非展示必需的工程化内容，聚焦校园合伙人申请场景：

| 阶段 | 内容 | 时间 |
|------|------|------|
| 🔴 升级 | Orchestrator + 协作看板 | 5 天 |
| 🟡 加固（可选） | 多模型路由、错误重试、数据持久化 | 2-3 天 |
| 🟡 前端（可选） | Monaco Editor 语法高亮、一键复制 | 1-2 天 |
| ❌ 砍掉 | CI/CD、监控、用户系统、插件、Serverless | — |

**砍掉理由**：
- CI/CD / Prometheus / Grafana：面试不看你流水线配置
- 用户系统 / JWT：校园合伙人不考察权限管理
- Serverless / K8s 插件：单机 Docker 足够展示
- 批量日志分析 / PDF 导出：核心演示不需要

---

## 八、申请话术参考

**项目一句话介绍**：

> CloudOps AI 是一个多 Agent 协作的智能运维助手。我设计了一个 Orchestrator 总指挥 Agent，它能够自动分析用户的运维问题，拆解为子任务，然后并行调度日志分析 Agent、命令生成 Agent 和脚本生成 Agent 协同工作，最后聚合结果生成诊断报告。

**技术亮点**（面试时可以展开的点）：

1. **多 Agent 架构设计**：Orchestrator 拆解 → 并行调度 → 结果聚合，真实还原了多 Agent 协作范式
2. **asyncio 并行调度**：三个子 Agent 通过 `asyncio.gather` 并行执行，而非串行等待
3. **字节豆包大模型接入**：所有 Agent 的推理能力基于豆包 API，实际体验了字节 AI 生态
4. **可视化协作看板**：前端实时展示 Agent 状态迁移和执行日志，可演示可录屏
5. **工程化基础**：Docker 容器化、Pydantic 数据校验、TDD 测试驱动

---

> 文档版本：v2.0  
> 基于 CloudOps AI 运维助手完整开发文档的升级方案
*（内容由AI生成，仅供参考）*
