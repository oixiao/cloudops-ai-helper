"""
运维脚本生成模块
根据运维场景需求，自动生成可运行的 Shell/Python 脚本
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ScriptResult:
    """脚本生成结果"""
    script: str
    language: str        # bash | sh | python
    description: str     # 使用说明
    warnings: List[str]  # 注意事项


class ScriptGenerator:
    """运维脚本生成器

    根据运维需求描述，自动生成可运行的脚本。
    支持 Bash 和 Python 两种语言。
    """

    # 危险操作关键词 → 警告信息
    DANGER_WARNINGS = {
        "删除": "⚠ 此脚本包含删除操作，执行前请务必备份数据，并先在测试环境验证。",
        "强制": "⚠ 此脚本包含强制操作，可能导致数据丢失或服务中断。",
        "卸载": "⚠ 此脚本包含卸载操作，请确认影响范围后再执行。",
        "清空": "⚠ 此脚本包含清空操作，数据将不可恢复。",
        "drop": "⚠ 此脚本包含 DROP 操作，数据库/表将被永久删除。",
        "格式化": "⚠ 此脚本包含格式化操作，所有数据将不可恢复！",
    }

    def __init__(self, use_ai: bool = False, ark_client=None):
        self.use_ai = use_ai
        self.ark_client = ark_client

    def generate(self, requirement: Optional[str]) -> ScriptResult:
        """根据运维需求生成脚本

        Args:
            requirement: 运维需求描述

        Returns:
            ScriptResult: 包含脚本、语言、使用说明、注意事项

        Raises:
            ValueError: 输入为空或None时抛出
        """
        if requirement is None:
            raise ValueError("需求描述不能为空")

        requirement = str(requirement).strip()
        if not requirement:
            raise ValueError("需求描述不能为空")

        # 检测语言偏好
        language = self._detect_language(requirement)
        # 生成脚本
        script, description = self._generate_by_type(requirement, language)
        # 收集警告
        warnings = self._collect_warnings(requirement)

        return ScriptResult(
            script=script,
            language=language,
            description=description,
            warnings=warnings,
        )

    def _detect_language(self, requirement: str) -> str:
        """检测用户期望的脚本语言"""
        if re.search(r"python|Python|\.py", requirement):
            return "python"
        # 默认 bash
        return "bash"

    def _generate_by_type(self, requirement: str, language: str) -> tuple:
        """根据需求类型生成对应脚本"""
        req_lower = requirement.lower()

        # --- 数据库备份 ---
        if any(kw in req_lower for kw in ["备份", "backup", "mysqldump", "pg_dump", "数据库"]):
            if language == "python":
                script = '''#!/usr/bin/env python3
"""MySQL 数据库自动备份脚本"""
import subprocess
import os
from datetime import datetime

# ========== 配置 ==========
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "mydb")
BACKUP_DIR = os.getenv("BACKUP_DIR", "/backup/mysql")
KEEP_DAYS = int(os.getenv("KEEP_DAYS", "7"))

def backup():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{DB_NAME}_{timestamp}.sql.gz"
    filepath = os.path.join(BACKUP_DIR, filename)

    os.makedirs(BACKUP_DIR, exist_ok=True)

    cmd = [
        "mysqldump",
        f"--host={DB_HOST}",
        f"--port={DB_PORT}",
        f"--user={DB_USER}",
        f"--password={DB_PASS}",
        "--single-transaction",
        "--routines",
        "--triggers",
        DB_NAME,
    ]

    with open(filepath + ".tmp", "wb") as f:
        proc1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc2 = subprocess.Popen(["gzip"], stdin=proc1.stdout, stdout=f)
        proc1.stdout.close()
        proc2.communicate()

    os.rename(filepath + ".tmp", filepath)
    print(f"[OK] 备份完成: {filepath}")

    # 清理旧备份
    import glob
    import time
    cutoff = time.time() - KEEP_DAYS * 86400
    for old in glob.glob(os.path.join(BACKUP_DIR, f"{DB_NAME}_*.sql.gz")):
        if os.path.getmtime(old) < cutoff:
            os.remove(old)
            print(f"[清理] 删除旧备份: {old}")

if __name__ == "__main__":
    backup()
'''
                description = "MySQL数据库备份脚本（Python版）：使用 mysqldump 导出数据，gzip 压缩，自动清理超过 KEEP_DAYS 天的旧备份。通过环境变量配置数据库连接信息。"
            else:
                script = '''#!/bin/bash
# MySQL 数据库自动备份脚本
set -euo pipefail

# ========== 配置 ==========
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-root}"
DB_PASS="${DB_PASS:-}"
DB_NAME="${DB_NAME:-mydb}"
BACKUP_DIR="${BACKUP_DIR:-/backup/mysql}"
KEEP_DAYS="${KEEP_DAYS:-7}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] 开始备份 $DB_NAME ..."
mysqldump \\
    --host="$DB_HOST" \\
    --port="$DB_PORT" \\
    --user="$DB_USER" \\
    --password="$DB_PASS" \\
    --single-transaction \\
    --routines \\
    --triggers \\
    "$DB_NAME" | gzip > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "[$(date)] [OK] 备份完成: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
else
    echo "[$(date)] [ERROR] 备份失败！" >&2
    exit 1
fi

# 清理超过 KEEP_DAYS 天的旧备份
find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -mtime +"$KEEP_DAYS" -delete
echo "[$(date)] [清理] 已清理 ${KEEP_DAYS} 天前的备份"
'''
                description = "MySQL数据库备份脚本（Bash版）：使用 mysqldump 导出，gzip 压缩，自动清理旧备份。通过环境变量配置，支持 set -euo pipefail 安全模式。"

        # --- 日志清理 ---
        elif any(kw in req_lower for kw in ["清理", "clean", "日志删除", "logs"]):
            script = '''#!/bin/bash
# 日志清理脚本 — 删除超过指定天数的日志文件
set -euo pipefail

LOG_DIR="${LOG_DIR:-/var/log}"
KEEP_DAYS="${KEEP_DAYS:-7}"
DRY_RUN="${DRY_RUN:-false}"
PATTERN="${PATTERN:-*.log}"

echo "=== 日志清理脚本 ==="
echo "目标目录: $LOG_DIR"
echo "保留天数: $KEEP_DAYS"
echo "匹配模式: $PATTERN"
echo "模拟运行: $DRY_RUN"
echo ""

FILES=$(find "$LOG_DIR" -type f -name "$PATTERN" -mtime +"$KEEP_DAYS" 2>/dev/null || true)
COUNT=$(echo "$FILES" | grep -c . || echo 0)

if [ "$COUNT" -eq 0 ]; then
    echo "没有需要清理的日志文件。"
    exit 0
fi

echo "找到 $COUNT 个超过 ${KEEP_DAYS} 天的日志文件："
echo "$FILES" | head -20
[ "$COUNT" -gt 20 ] && echo "... 还有 $((COUNT - 20)) 个文件"

if [ "$DRY_RUN" = "true" ]; then
    echo "[DRY RUN] 以上文件不会被实际删除。"
else
    echo ""
    read -p "确认删除以上文件？(yes/no): " CONFIRM
    if [ "$CONFIRM" = "yes" ]; then
        find "$LOG_DIR" -type f -name "$PATTERN" -mtime +"$KEEP_DAYS" -delete 2>/dev/null
        echo "[OK] 已删除 $COUNT 个日志文件。"
    else
        echo "已取消删除操作。"
    fi
fi
'''
            description = "日志清理脚本：查找并删除超过 KEEP_DAYS 天的日志文件。支持 DRY_RUN 模式预览要删除的文件，删除前需要用户确认。通过环境变量配置目标目录、保留天数和文件匹配模式。"

        # --- 服务监控重启 ---
        elif any(kw in req_lower for kw in ["重启", "restart", "监控", "monitor", "nginx", "服务"]):
            script = '''#!/bin/bash
# 服务健康监控与自动重启脚本
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-nginx}"
CHECK_URL="${CHECK_URL:-http://localhost:80/health}"
MAX_RETRIES=3
SLEEP_BETWEEN=5

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

check_service() {
    # 方式1：HTTP 健康检查
    if [ -n "$CHECK_URL" ]; then
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$CHECK_URL" 2>/dev/null || echo "000")
        if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
            return 0
        fi
        log "WARNING: $CHECK_URL 返回 HTTP $HTTP_CODE"
    fi

    # 方式2：systemctl 状态检查
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        return 0
    fi

    return 1
}

# ===== 主逻辑 =====
log "开始监控服务: $SERVICE_NAME"

for i in $(seq 1 $MAX_RETRIES); do
    if check_service; then
        log "OK: 服务 $SERVICE_NAME 运行正常"
        exit 0
    fi

    log "尝试 $i/$MAX_RETRIES: 服务异常，正在重启..."

    systemctl restart "$SERVICE_NAME" 2>/dev/null || \\
    service "$SERVICE_NAME" restart 2>/dev/null || \\
    docker restart "$SERVICE_NAME" 2>/dev/null || true

    sleep "$SLEEP_BETWEEN"

    if check_service; then
        log "OK: 服务 $SERVICE_NAME 已恢复"
        # 可选：发送通知
        # curl -X POST "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY" \\
        #   -H "Content-Type: application/json" \\
        #   -d "{\\"msgtype\\":\\"text\\",\\"text\\":{\\"content\\":\\"$SERVICE_NAME 已自动恢复\\"}}"
        exit 0
    fi
done

log "ERROR: 服务 $SERVICE_NAME 重启 $MAX_RETRIES 次后仍未恢复！"
exit 1
'''
            description = "服务健康监控与自动重启脚本：通过HTTP健康检查和systemctl状态双重检测服务状态，异常时自动重启，支持最大重试次数。适用于 Nginx/MySQL/Docker 等服务。"

        # --- CPU/资源监控 ---
        elif any(kw in req_lower for kw in ["cpu", "内存", "资源", "监控", "使用率", "负载"]):
            script = '''#!/bin/bash
# 系统资源监控脚本
set -euo pipefail

THRESHOLD_CPU="${THRESHOLD_CPU:-80}"
THRESHOLD_MEM="${THRESHOLD_MEM:-80}"
THRESHOLD_DISK="${THRESHOLD_DISK:-85}"
ALERT_SCRIPT="${ALERT_SCRIPT:-}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# --- CPU 检查 ---
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1 | cut -d'.' -f1)
if [ -n "$CPU_USAGE" ] && [ "$CPU_USAGE" -gt "$THRESHOLD_CPU" ] 2>/dev/null; then
    log "WARNING: CPU 使用率 ${CPU_USAGE}% (阈值: ${THRESHOLD_CPU}%)"
    log "TOP 5 进程:"
    ps aux --sort=-%cpu | head -6
fi

# --- 内存检查 ---
MEM_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100}')
if [ -n "$MEM_USAGE" ] && [ "$MEM_USAGE" -gt "$THRESHOLD_MEM" ] 2>/dev/null; then
    log "WARNING: 内存使用率 ${MEM_USAGE}% (阈值: ${THRESHOLD_MEM}%)"
    log "TOP 5 内存进程:"
    ps aux --sort=-%mem | head -6
fi

# --- 磁盘检查 ---
df -h --exclude-type=tmpfs --exclude-type=devtmpfs 2>/dev/null | tail -n +2 | while read -r line; do
    DISK_USAGE=$(echo "$line" | awk '{print $5}' | sed 's/%//')
    MOUNT=$(echo "$line" | awk '{print $6}')
    if [ -n "$DISK_USAGE" ] && [ "$DISK_USAGE" -gt "$THRESHOLD_DISK" ] 2>/dev/null; then
        log "WARNING: 磁盘 $MOUNT 使用率 ${DISK_USAGE}% (阈值: ${THRESHOLD_DISK}%)"
    fi
done

log "资源监控检查完成。"
'''
            description = "系统资源监控脚本：检查CPU、内存、磁盘使用率，超过阈值时输出告警信息和TOP进程列表。配合 cron 定时任务使用效果最佳。"

        # --- 默认通用脚本 ---
        else:
            script = '''#!/bin/bash
# 运维脚本 — 自动生成
# 需求：{requirement}
set -euo pipefail

echo "========================================="
echo "  CloudOps AI - 运维脚本"
echo "  需求: {requirement}"
echo "  时间: $(date)"
echo "========================================="

# TODO: 根据具体需求调整以下命令

# 1. 系统信息收集
echo ""
echo ">>> 系统基本信息 <<<"
echo "主机名: $(hostname)"
echo "内核版本: $(uname -r)"
echo "运行时间: $(uptime -p)"

# 2. 资源使用概览
echo ""
echo ">>> 资源使用概览 <<<"
echo "CPU:"
top -bn1 | grep "Cpu(s)" | head -1
echo ""
echo "内存:"
free -h
echo ""
echo "磁盘:"
df -h --exclude-type=tmpfs 2>/dev/null | head -10

echo ""
echo ">>> 脚本执行完成 <<<"
'''.replace("{requirement}", requirement)
            description = f"通用运维脚本模板 — 需求: {requirement}。包含系统信息收集和资源使用概览。请根据具体需求修改 TODO 部分的命令。"

        # 添加shebang（如果缺失）
        if language == "bash" and not script.startswith("#!/"):
            script = "#!/bin/bash\n" + script

        return script, description

    def _collect_warnings(self, requirement: str) -> List[str]:
        """收集操作警告"""
        warnings = []
        for keyword, warning in self.DANGER_WARNINGS.items():
            if keyword in requirement:
                warnings.append(warning)

        # 通用提醒
        if not warnings:
            warnings.append("💡 提示：首次使用请先在测试环境执行，确认无误后再用于生产环境。")
        else:
            warnings.append("💡 生产环境执行前，务必先在测试环境验证脚本的正确性。")

        return warnings

    async def generate_async(self, requirement: str) -> ScriptResult:
        """异步生成脚本（AI模式入口）"""
        if not self.use_ai or self.ark_client is None:
            return self.generate(requirement)

        prompt = (
            "你是一个运维脚本专家。请根据用户需求生成运维脚本。\n\n"
            "要求：\n"
            "1. 只返回JSON格式："
            '{"script": "完整脚本内容", "language": "bash|python", '
            '"description": "使用说明", "warnings": ["注意事项1", "注意事项2"]}\n'
            "2. 脚本必须可执行，包含适当的错误处理\n"
            "3. 脚本包含清晰的注释\n"
            "4. 危险操作必须在 warnings 中明确警告\n"
        )

        try:
            import json
            raw = await self.ark_client.chat(
                f"{prompt}\n\n用户需求：{requirement}"
            )
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
            data = json.loads(raw)
            return ScriptResult(
                script=data.get("script", ""),
                language=data.get("language", "bash"),
                description=data.get("description", ""),
                warnings=data.get("warnings", []),
            )
        except Exception:
            return self.generate(requirement)
