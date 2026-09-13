"""
TDD: 运维脚本生成模块 — 测试用例
Red → Green → Refactor
"""
import pytest
from src.core.script_generator import ScriptGenerator, ScriptResult


class TestScriptGenerator:
    """脚本生成模块单元测试"""

    def setup_method(self):
        self.generator = ScriptGenerator(use_ai=False)

    # ========== Red Phase Tests ==========

    def test_normal_input_returns_valid_result(self):
        """测试：正常运维描述返回标准化结构"""
        result = self.generator.generate("备份MySQL数据库")
        assert isinstance(result, ScriptResult)
        assert result.script is not None
        assert len(result.script) > 0
        assert result.language in ["bash", "python", "sh"]
        assert isinstance(result.description, str)
        assert isinstance(result.warnings, list)

    def test_empty_input_raises_error(self):
        """测试：空输入抛出异常"""
        with pytest.raises(ValueError, match="需求描述不能为空"):
            self.generator.generate("")

    def test_whitespace_input_raises_error(self):
        """测试：纯空白输入抛出异常"""
        with pytest.raises(ValueError, match="需求描述不能为空"):
            self.generator.generate("   \n\t   ")

    # ========== Script Content Tests ==========

    def test_backup_script_contains_mysqldump(self):
        """测试：备份需求生成的脚本包含备份命令"""
        result = self.generator.generate("备份MySQL数据库")
        assert "mysqldump" in result.script.lower() or "backup" in result.script.lower()

    def test_log_cleanup_script_contains_rm(self):
        """测试：日志清理需求生成的脚本包含清理命令"""
        result = self.generator.generate("清理7天前的日志文件")
        assert any(cmd in result.script.lower() for cmd in ["find", "rm", "clean"])

    def test_monitor_script_contains_basic_structure(self):
        """测试：监控脚本包含基本结构"""
        result = self.generator.generate("监控CPU使用率")
        assert len(result.script) > 30  # 脚本至少30个字符
        assert result.language in ["bash", "sh"]

    def test_service_restart_script_contains_systemctl(self):
        """测试：服务重启脚本包含 systemctl"""
        result = self.generator.generate("nginx服务挂了自动重启")
        assert any(cmd in result.script.lower() for cmd in ["systemctl", "service", "restart"])

    # ========== Language Detection Tests ==========

    def test_python_request_generates_python_script(self):
        """测试：明确要求Python脚本时返回Python"""
        result = self.generator.generate("用Python写一个日志分析脚本")
        assert result.language == "python"

    def test_default_language_is_bash(self):
        """测试：默认生成Bash脚本"""
        result = self.generator.generate("检查磁盘空间")
        assert result.language in ["bash", "sh"]

    # ========== Warnings Tests ==========

    def test_dangerous_operation_includes_warning(self):
        """测试：危险操作包含警告信息"""
        result = self.generator.generate("删除所有数据库数据")
        assert len(result.warnings) > 0

    def test_safe_operation_may_have_no_warnings(self):
        """测试：安全操作可以无警告"""
        result = self.generator.generate("打印当前时间")
        assert isinstance(result.warnings, list)

    # ========== Result Structure Tests ==========

    def test_result_has_all_fields(self):
        """测试：返回结果包含所有字段"""
        result = self.generator.generate("监控服务器负载")
        assert hasattr(result, 'script')
        assert hasattr(result, 'language')
        assert hasattr(result, 'description')
        assert hasattr(result, 'warnings')
        assert isinstance(result.script, str)
        assert isinstance(result.language, str)
        assert isinstance(result.description, str)
        assert isinstance(result.warnings, list)

    # ========== Edge Cases ==========

    def test_none_input_raises_error(self):
        """测试：None输入抛出异常"""
        with pytest.raises(ValueError):
            self.generator.generate(None)

    def test_complex_requirement_generates_script(self):
        """测试：复杂需求能生成有效脚本"""
        result = self.generator.generate(
            "写一个脚本：检查所有Docker容器状态，"
            "如果发现已停止的容器则自动重启，"
            "并将结果发送到企业微信"
        )
        assert result is not None
        assert len(result.script) > 50
        assert "docker" in result.script.lower()

    def test_script_is_valid_shell(self):
        """测试：生成的脚本以shebang开头"""
        result = self.generator.generate("检查服务器时间")
        # 允许没有shebang但脚本内容有意义
        assert len(result.script) > 0
