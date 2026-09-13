"""
运维命令生成模块
根据自然语言描述生成对应的 Linux/运维命令
"""
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GenerateResult:
    """命令生成结果"""
    command: str
    explanation: str
    safety_level: str = "safe"  # safe | warning | dangerous


class CmdGenerator:
    """运维命令生成器

    支持两种模式：
    - 本地规则匹配（无AI依赖，快速响应）
    - AI大模型生成（通过 ArkClient 调用）
    """

    # 危险操作关键词
    DANGEROUS_KEYWORDS = [
        "删除", "强制删除", "格式化", "清空", "rm -rf", "dd if",
        "mkfs", "fdisk", "drop", "truncate",
        "强制", "全部删除", "永久删除", "不可恢复",
    ]

    # 警告操作关键词
    WARNING_KEYWORDS = [
        "杀掉", "杀死", "kill", "重启", "停止", "停用",
        "修改", "更改", "覆盖", "移除", "卸载",
        "pkill", "reboot", "shutdown", "halt",
    ]

    # 本地规则匹配表（危险/警告规则优先，然后按精确度排序）
    RULES = [
        # === 危险操作规则（高优先级） ===
        {
            "pattern": r"强制.*删除|rm -rf|全部删除|永久删除|不可恢复",
            "command": "# ⚠ 危险命令 — 请谨慎使用\nrm -rf /path/to/target",
            "explanation": "rm -rf /path/to/target：递归强制删除指定目录下的所有内容，不可恢复！⚠ 请务必：① 确认路径正确 ② 先备份重要数据 ③ 不要对 / 或 /* 执行此命令。",
            "safety": "dangerous",
        },
        {
            "pattern": r"日志.*删除|清理.*日志|删除.*日志",
            "command": "find /var/log -type f -name '*.log' -mtime +7 -delete",
            "explanation": "find /var/log -type f -name '*.log' -mtime +7 -delete：查找 /var/log 下7天前的 .log 文件并删除。⚠ 危险命令，执行前建议先用 -print 代替 -delete 预览要删除的文件。",
            "safety": "dangerous",
        },
        # === 警告级操作 ===
        {
            "pattern": r"杀死.*进程|杀掉.*进程|结束.*进程|kill.*进程",
            "command": "# 找到目标进程\nps aux | grep <进程名>\n# 安全终止（优先使用）\nkill <PID>\n# 强制终止（仅在无响应时使用）\nkill -9 <PID>",
            "explanation": "kill <PID>：优雅地终止进程（发送SIGTERM信号），给进程保存数据的机会。kill -9 <PID>：强制终止（SIGKILL），进程无法忽略，仅在进程无响应时使用。",
            "safety": "warning",
        },
        # === 常用只读操作 ===
        {
            "pattern": r"内存|memory|RAM|free|内存使用",
            "command": "free -h",
            "explanation": "free -h：显示系统内存（物理内存和交换空间）的使用情况。-h 参数使用人类可读格式。关注 available 列而非 free 列。",
            "safety": "safe",
        },
        {
            "pattern": r"进程|process|ps|运行.*程序|查看.*运行|进程列表",
            "command": "ps aux --sort=-%mem | head -20",
            "explanation": "ps aux：列出所有用户的所有进程，--sort=-%mem 按内存使用量降序排列，head -20 仅显示前20行。可改为 --sort=-%cpu 按CPU排序。",
            "safety": "safe",
        },
        {
            "pattern": r"CPU|处理器|负载|load|cpu使用",
            "command": "top -bn1 | head -20",
            "explanation": "top -bn1：以批处理模式运行一次 top，显示CPU使用率、负载均衡和进程信息。head -20 限制输出行数。",
            "safety": "safe",
        },
        {
            "pattern": r"网络|端口|连接|netstat|ss|监听|连通",
            "command": "ss -tlnp",
            "explanation": "ss -tlnp：显示所有TCP监听端口及对应进程。-t=TCP, -l=监听状态, -n=数字格式显示端口号, -p=显示进程名称。比 netstat 更快。",
            "safety": "safe",
        },
        {
            "pattern": r"大文件|查找.*文件|搜索.*文件|find|大目录",
            "command": "find / -type f -size +100M -exec ls -lh {} \\; 2>/dev/null | head -20",
            "explanation": "find / -type f -size +100M：从根目录查找大于100MB的文件，2>/dev/null 屏蔽权限错误，ls -lh 显示文件大小。使用时注意：扫描根目录可能消耗较多I/O。",
            "safety": "safe",
        },
        {
            "pattern": r"系统版本|系统信息|uname|发行版|内核",
            "command": "uname -a && cat /etc/os-release",
            "explanation": "uname -a：显示内核版本、主机名、架构等完整系统信息。cat /etc/os-release：显示Linux发行版名称和版本。",
            "safety": "safe",
        },
        {
            "pattern": r"磁盘|硬盘|存储|容量|df\b|磁盘空间",
            "command": "df -h",
            "explanation": "df -h：以人类可读格式显示所有挂载文件系统的磁盘使用情况。-h 参数将大小转换为 GB/MB 等易读单位。",
            "safety": "safe",
        },
        {
            "pattern": r"权限|chmod|chown|归属",
            "command": "ls -la <filename>\n# 查看文件权限和所有者\nstat <filename>",
            "explanation": "ls -la：以长格式显示所有文件（包括隐藏文件）的权限、所有者、大小等信息。stat：显示文件的详细元数据。修改权限使用 chmod，修改所有者使用 chown。",
            "safety": "safe",
        },
        {
            "pattern": r"Docker|docker|容器",
            "command": "docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'",
            "explanation": "docker ps -a：列出所有Docker容器（包括已停止的）。--format 以表格形式输出名称、状态和端口映射。docker stats：查看容器资源使用情况。",
            "safety": "safe",
        },
        {
            "pattern": r"定时任务|cron|crontab|计划任务",
            "command": "crontab -l",
            "explanation": "crontab -l：列出当前用户的所有定时任务。crontab -e：编辑定时任务。格式：分 时 日 月 周 命令。",
            "safety": "safe",
        },
        {
            "pattern": r"防火墙|iptables|firewall|安全组",
            "command": "# firewalld (CentOS7+/RHEL7+)\nsudo firewall-cmd --list-all\n# iptables\nsudo iptables -L -n -v",
            "explanation": "firewall-cmd --list-all：查看当前防火墙区域的所有规则。iptables -L -n -v：列出所有iptables规则，-n数字格式 -v详细输出。",
            "safety": "safe",
        },
        {
            "pattern": r"用户|user|登录|who|账号",
            "command": "who && echo '---' && w",
            "explanation": "who：查看当前登录用户列表。w：显示更详细信息，包括用户正在执行的命令和登录时间。last：查看历史登录记录。",
            "safety": "safe",
        },
    ]

    def __init__(self, use_ai: bool = False, ark_client=None):
        """
        Args:
            use_ai: 是否启用AI大模型生成
            ark_client: ArkClient 实例（use_ai=True 时必须提供）
        """
        self.use_ai = use_ai
        self.ark_client = ark_client

    def generate(self, user_input: Optional[str]) -> GenerateResult:
        """根据自然语言描述生成运维命令

        Args:
            user_input: 用户的运维需求描述（自然语言）

        Returns:
            GenerateResult: 包含命令、解释、安全等级的标准化结果

        Raises:
            ValueError: 输入为空或None时抛出
        """
        if user_input is None:
            raise ValueError("输入不能为空")

        user_input = str(user_input).strip()
        if not user_input:
            raise ValueError("输入不能为空")

        # 本地规则匹配
        return self._local_match(user_input)

    def _local_match(self, user_input: str) -> GenerateResult:
        """本地规则匹配 — 基于关键词匹配返回预定义命令"""
        # 按规则顺序匹配
        for rule in self.RULES:
            if re.search(rule["pattern"], user_input, re.IGNORECASE):
                return GenerateResult(
                    command=rule["command"],
                    explanation=rule["explanation"],
                    safety_level=rule["safety"],
                )

        # 无匹配时：检查是否与运维相关
        if self._is_it_related(user_input):
            return GenerateResult(
                command="# 请提供更具体的运维需求\n# 例如：查看磁盘使用情况、检查网络连通性、查看进程列表",
                explanation="您的描述较为宽泛，请补充更多细节。支持的命令类别：磁盘管理、内存监控、进程管理、网络诊断、日志分析、Docker管理、用户管理等。",
                safety_level="safe",
            )
        else:
            return GenerateResult(
                command="# 无法理解您的需求\n# CloudOps AI 专注于运维场景",
                explanation="您的输入似乎与运维场景无关。CloudOps AI 支持：磁盘管理、内存监控、进程管理、网络诊断、日志分析、Docker管理、定时任务、用户管理等运维操作。请重新描述您的运维需求。",
                safety_level="safe",
            )

    def _is_it_related(self, user_input: str) -> bool:
        """判断输入是否与运维相关"""
        it_keywords = [
            "服务器", "运维", "linux", "命令", "系统", "服务",
            "部署", "监控", "备份", "日志", "配置", "安装",
            "磁盘", "内存", "CPU", "网络", "进程", "端口",
            "docker", "容器", "数据库", "mysql", "nginx",
            "apache", "redis", "k8s", "kubernetes",
            "查看", "检查", "查询", "获取", "列出", "显示",
        ]
        return any(kw in user_input.lower() for kw in it_keywords)

    def _determine_safety(self, user_input: str) -> str:
        """根据输入内容判断命令安全等级"""
        for kw in self.DANGEROUS_KEYWORDS:
            if kw in user_input:
                return "dangerous"
        for kw in self.WARNING_KEYWORDS:
            if kw in user_input:
                return "warning"
        return "safe"

    async def generate_async(self, user_input: str) -> GenerateResult:
        """异步生成命令（AI模式入口）

        当 use_ai=True 时，通过大模型API生成命令。
        """
        if not self.use_ai or self.ark_client is None:
            return self.generate(user_input)

        prompt = (
            "你是一个专业的Linux运维专家。请根据用户的自然语言描述，生成对应的运维命令。\n\n"
            "要求：\n"
            "1. 只返回一个JSON对象，不要包含其他解释性文字\n"
            '2. JSON格式固定为：{"command": "生成的命令", "explanation": "参数解释和使用说明", "safety_level": "safe|warning|dangerous"}\n'
            "3. 如果命令涉及删除、格式化等危险操作，safety_level标记为dangerous并给出警告\n"
            "4. 命令必须可直接在终端运行，不要包含伪代码\n"
            "5. 如果用户需求不明确，在explanation中说明使用前提条件\n"
        )

        try:
            import json
            raw = await self.ark_client.chat(
                f"{prompt}\n\n用户需求：{user_input}"
            )
            # 清洗 JSON
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
            data = json.loads(raw)
            return GenerateResult(
                command=data.get("command", ""),
                explanation=data.get("explanation", ""),
                safety_level=data.get("safety_level", "safe"),
            )
        except Exception:
            # AI 生成失败，降级到本地匹配
            return self._local_match(user_input)
