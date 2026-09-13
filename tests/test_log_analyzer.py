"""
TDD: 日志智能分析模块 — 测试用例
Red → Green → Refactor
"""
import pytest
from src.core.log_analyzer import LogAnalyzer, AnalyzeResult


class TestLogAnalyzer:
    """日志分析模块单元测试"""

    def setup_method(self):
        self.analyzer = LogAnalyzer(use_ai=False)

    # ========== Red Phase Tests ==========

    def test_normal_log_returns_valid_result(self):
        """测试：正常日志输入返回标准结构"""
        result = self.analyzer.analyze("2024-01-01 INFO Server started successfully")
        assert isinstance(result, AnalyzeResult)
        assert result.level in ["normal", "warning", "error", "fatal"]
        assert isinstance(result.summary, str)
        assert isinstance(result.steps, list)

    def test_empty_input_raises_error(self):
        """测试：空输入抛出异常"""
        with pytest.raises(ValueError, match="日志内容不能为空"):
            self.analyzer.analyze("")

    def test_whitespace_input_raises_error(self):
        """测试：纯空白输入抛出异常"""
        with pytest.raises(ValueError, match="日志内容不能为空"):
            self.analyzer.analyze("    \n\t  ")

    # ========== Log Level Tests ==========

    def test_error_log_detects_error_level(self):
        """测试：ERROR日志识别为 error 等级"""
        log = "2024-06-01 10:00:00 ERROR Database connection failed: timeout"
        result = self.analyzer.analyze(log)
        assert result.level == "error"

    def test_fatal_log_detects_fatal_level(self):
        """测试：FATAL日志识别为 fatal 等级"""
        log = "2024-06-01 10:00:00 FATAL Out of memory: process killed"
        result = self.analyzer.analyze(log)
        assert result.level == "fatal"

    def test_warning_log_detects_warning_level(self):
        """测试：WARNING日志识别为 warning 等级"""
        log = "2024-06-01 10:00:00 WARNING Disk usage exceeds 80%"
        result = self.analyzer.analyze(log)
        assert result.level == "warning"

    def test_normal_log_detects_normal_level(self):
        """测试：INFO日志识别为 normal 等级"""
        log = "2024-06-01 10:00:00 INFO Service started on port 8080"
        result = self.analyzer.analyze(log)
        assert result.level == "normal"

    # ========== Error Type Tests ==========

    def test_oom_log_detects_memory_error(self):
        """测试：OOM日志检测为内存错误"""
        log = "Out of memory: Kill process 12345 (java)"
        result = self.analyzer.analyze(log)
        assert "memory" in result.error_type.lower() or "内存" in result.error_type.lower() or "oom" in result.error_type.lower()

    def test_connection_refused_detects_network_error(self):
        """测试：连接拒绝检测为网络错误"""
        log = "ERROR Connection refused: connect to 10.0.0.1:3306"
        result = self.analyzer.analyze(log)
        assert "connection" in result.error_type.lower() or "network" in result.error_type.lower() or "连接" in result.error_type.lower()

    def test_permission_denied_detects_permission_error(self):
        """测试：权限拒绝检测为权限错误"""
        log = "ERROR Permission denied: /etc/nginx/nginx.conf"
        result = self.analyzer.analyze(log)
        assert "permission" in result.error_type.lower() or "权限" in result.error_type.lower()

    def test_disk_full_detects_disk_error(self):
        """测试：磁盘满检测为磁盘错误"""
        log = "ERROR No space left on device"
        result = self.analyzer.analyze(log)
        assert "disk" in result.error_type.lower() or "space" in result.error_type.lower() or "磁盘" in result.error_type.lower()

    # ========== Steps Tests ==========

    def test_error_log_returns_actionable_steps(self):
        """测试：错误日志返回可操作排查步骤"""
        log = "ERROR Database connection timeout after 30000ms"
        result = self.analyzer.analyze(log)
        assert len(result.steps) > 0

    def test_normal_log_returns_empty_steps(self):
        """测试：正常日志返回空排查步骤"""
        log = "INFO Backup completed successfully"
        result = self.analyzer.analyze(log)
        assert result.steps == [] or len(result.steps) == 0

    # ========== Nginx Log Tests ==========

    def test_nginx_500_error(self):
        """测试：Nginx 500错误"""
        log = '192.168.1.1 - - [01/Jun/2024:10:00:00 +0000] "GET /api HTTP/1.1" 500 1234'
        result = self.analyzer.analyze(log)
        assert result.level in ["error", "warning"]

    def test_nginx_404_error(self):
        """测试：Nginx 404错误"""
        log = '192.168.1.1 - - [01/Jun/2024:10:00:00 +0000] "GET /missing HTTP/1.1" 404 256'
        result = self.analyzer.analyze(log)
        assert result.level in ["warning", "error"]

    # ========== Edge Cases ==========

    def test_none_input_raises_error(self):
        """测试：None输入抛出异常"""
        with pytest.raises(ValueError):
            self.analyzer.analyze(None)

    def test_very_long_log(self):
        """测试：超长日志不崩溃"""
        log = "ERROR " + "error detail " * 500
        result = self.analyzer.analyze(log)
        assert result is not None
        assert result.level == "error"

    def test_multiline_log(self):
        """测试：多行日志能正常分析"""
        log = """2024-06-01 INFO Starting application
2024-06-01 ERROR Failed to connect to database
2024-06-01 FATAL Application terminated"""
        result = self.analyzer.analyze(log)
        assert result.level in ["error", "fatal"]
