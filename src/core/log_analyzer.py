"""
日志智能分析模块
自动识别日志异常等级、错误类型，给出分步排查建议
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AnalyzeResult:
    """日志分析结果"""
    level: str           # normal | warning | error | fatal
    error_type: str      # 错误类型
    summary: str         # 一句话摘要
    steps: List[str]     # 排查步骤列表
    confidence: float = 0.8  # 置信度 0-1


class LogAnalyzer:
    """日志智能分析器

    支持：
    - 系统日志（Linux syslog / dmesg）
    - Web服务器日志（Nginx / Apache）
    - 应用日志（通用错误日志格式）
    """

    # 错误模式匹配表
    ERROR_PATTERNS = [
        # (正则模式, 错误类型, 等级, 排查步骤)
        (r"Out of memory|OOM|out of memory|OOM Killer|oom-killer", "内存溢出(OOM)", "fatal", [
            "用 free -h 查看当前内存使用情况",
            "用 ps aux --sort=-%mem | head -20 定位内存占用最高的进程",
            "检查应用是否有内存泄漏：观察进程内存是否持续增长",
            "考虑增加服务器物理内存或配置 swap",
            "调整 OOM Killer 策略或为关键进程设置 oom_score_adj",
        ]),
        (r"Connection refused|connection refused|ECONNREFUSED", "连接拒绝", "error", [
            "用 ss -tlnp 确认目标服务是否在监听对应端口",
            "检查服务是否已启动：systemctl status <service>",
            "检查防火墙规则是否放行目标端口：iptables -L -n",
            "用 telnet <host> <port> 或 nc -zv <host> <port> 测试连通性",
            "检查服务是否绑定在正确的IP上（127.0.0.1 仅本机可访问）",
        ]),
        (r"Permission denied|permission denied|EACCES", "权限拒绝", "error", [
            "用 ls -la 检查文件/目录的权限和所有者",
            "确认当前用户是否有访问权限：whoami && id",
            "使用 sudo 或切换到有权限的用户执行",
            "检查 SELinux/AppArmor 是否拦截：getenforce / aa-status",
            "如果是新创建的文件，检查 umask 设置",
        ]),
        (r"No space left|no space|disk full|ENOSPC|磁盘空间不足", "磁盘空间不足", "error", [
            "用 df -h 查看所有分区的磁盘使用率",
            "用 du -sh /* | sort -rh | head -20 定位大目录",
            "清理系统日志：journalctl --vacuum-size=500M",
            "清理Docker无用镜像和数据：docker system prune -a",
            "清理旧内核：dpkg -l | grep linux-image（Debian/Ubuntu）",
        ]),
        (r"timeout|Timeout|timed out|ETIMEDOUT|connection timeout", "连接超时", "error", [
            "用 ping 测试网络连通性：ping -c 4 <host>",
            "用 curl -v <url> 查看详细的请求过程",
            "检查DNS解析：nslookup <host> 或 dig <host>",
            "检查防火墙或安全组是否禁止了外发请求",
            "增加应用层的超时时间配置",
        ]),
        (r"FATAL|fatal|CRITICAL|critical|EMERGENCY", "严重错误", "fatal", [
            "立即检查服务运行状态：systemctl status <service>",
            "查看完整错误日志：journalctl -u <service> -n 100",
            "检查系统资源使用情况：top / free / df",
            "查看系统日志：dmesg | tail -50",
            "如果是应用崩溃，检查 core dump 文件",
        ]),
        (r"Segfault|segfault|SIGSEGV|segmentation fault|段错误", "内存段错误", "fatal", [
            "查看 dmesg 中的 segfault 详细信息：dmesg | grep segfault",
            "检查应用版本是否与系统库兼容",
            "使用 valgrind 或 gdb 进行内存调试",
            "检查 ulimit -c 是否开启 core dump",
            "升级或重新编译相关的二进制程序",
        ]),
        (r"ERROR|error|Error|fail|FAIL|failed|Failed", "运行时错误", "error", [
            "仔细阅读错误信息中的具体原因",
            "检查相关配置文件语法是否正确",
            "查看应用自身日志文件的详细记录",
            "用 grep -i error /var/log/ 查找更多错误上下文",
            "尝试以调试模式启动服务获取更多信息",
        ]),
        (r"WARNING|warning|WARN|warn|deprecated", "警告", "warning", [
            "关注警告内容，评估是否需要立即处理",
            "检查是否为已知的兼容性问题",
            "查看相关软件版本的Release Notes",
            "如果功能正常，可计划在维护窗口处理",
        ]),
        # Nginx 特定模式
        (r'" (50[0-9]) ', "Nginx服务端错误", "error", [
            "查看 Nginx 错误日志：tail -f /var/log/nginx/error.log",
            "检查 upstream 后端服务是否正常运行",
            "确认 PHP-FPM / uWSGI 等后端是否存活",
            "检查 Nginx 配置：nginx -t",
        ]),
        (r'" (40[34]) ', "Nginx客户端错误", "warning", [
            "确认请求的URL路径是否正确",
            "检查文件/资源是否存在",
            "查看 Nginx access log 确认请求来源",
        ]),
    ]

    def __init__(self, use_ai: bool = False, ark_client=None):
        self.use_ai = use_ai
        self.ark_client = ark_client

    def analyze(self, log_content: Optional[str]) -> AnalyzeResult:
        """分析日志内容，返回标准化诊断结果

        Args:
            log_content: 日志文本内容

        Returns:
            AnalyzeResult: 包含等级、错误类型、摘要、排查步骤的结构化结果

        Raises:
            ValueError: 输入为空或None时抛出
        """
        if log_content is None:
            raise ValueError("日志内容不能为空")

        log_content = str(log_content).strip()
        if not log_content:
            raise ValueError("日志内容不能为空")

        return self._pattern_analyze(log_content)

    def _pattern_analyze(self, log_content: str) -> AnalyzeResult:
        """基于模式匹配分析日志"""

        # 按优先级从高到低匹配错误模式
        for pattern, error_type, level, steps in self.ERROR_PATTERNS:
            if re.search(pattern, log_content, re.IGNORECASE):
                return AnalyzeResult(
                    level=level,
                    error_type=error_type,
                    summary=self._generate_summary(error_type, log_content),
                    steps=steps.copy(),
                    confidence=0.85 if level in ["error", "fatal"] else 0.7,
                )

        # 没有匹配到任何已知错误模式 — 判断是否为正常日志
        if self._is_normal_log(log_content):
            return AnalyzeResult(
                level="normal",
                error_type="无异常",
                summary="日志内容正常，未检测到异常信息。",
                steps=[],
                confidence=0.9,
            )

        # 无法归类但可能含异常
        return AnalyzeResult(
            level="warning",
            error_type="未知异常",
            summary="日志中包含未识别的异常信息，建议人工审查。",
            steps=[
                "仔细阅读日志全文，寻找异常关键字",
                "对比正常时期的日志，找出差异",
                "查看同一时间段内的系统日志（/var/log/syslog 或 journalctl）",
                "在搜索引擎或技术社区中搜索日志中的关键错误信息",
            ],
            confidence=0.5,
        )

    def _is_normal_log(self, log_content: str) -> bool:
        """判断是否为正常日志（无异常）"""
        # 检测到明确的正常标记
        normal_markers = [
            r"successfully|success|completed|started|running|ok",
            r"INFO|info|Info|DEBUG|debug|Debug",
            r"200 OK|201 Created|304 Not Modified",
        ]

        error_markers = [
            r"error|ERROR|Error|fail|FAIL|Failed|failed",
            r"exception|Exception|traceback|Traceback",
            r"FATAL|CRITICAL|WARNING|WARN",
        ]

        has_error = any(re.search(m, log_content) for m in error_markers)
        has_normal = any(re.search(m, log_content, re.IGNORECASE) for m in normal_markers)

        # 有正常标记且没有错误标记 → 正常
        return has_normal and not has_error

    def _generate_summary(self, error_type: str, log_content: str) -> str:
        """生成一句话摘要"""
        # 提取日志中的关键信息
        first_line = log_content.strip().split("\n")[0][:120]
        return f"检测到【{error_type}】：{first_line}..."

    async def analyze_async(self, log_content: str) -> AnalyzeResult:
        """异步分析日志（AI模式入口）"""
        if not self.use_ai or self.ark_client is None:
            return self.analyze(log_content)

        prompt = (
            "你是一个日志分析专家。请分析以下日志内容，给出结构化诊断结果。\n\n"
            "要求：\n"
            "1. 只返回JSON格式："
            '{"level": "normal|warning|error|fatal", "type": "错误类型", '
            '"summary": "一句话摘要", "steps": ["排查步骤1", "步骤2", ...], "confidence": 0-1}\n'
            "2. 如果日志内容正常，level为normal，steps为空数组\n"
            "3. 排查步骤必须具体可操作，不要泛泛而谈\n"
            "4. confidence表示你的判断信心度，如果不确定请低于0.7\n"
        )

        try:
            import json
            raw = await self.ark_client.chat(
                f"{prompt}\n\n日志内容：\n{log_content[:4000]}"
            )
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
            data = json.loads(raw)
            return AnalyzeResult(
                level=data.get("level", "warning"),
                error_type=data.get("type", "未知"),
                summary=data.get("summary", ""),
                steps=data.get("steps", []),
                confidence=float(data.get("confidence", 0.5)),
            )
        except Exception:
            return self._pattern_analyze(log_content)
