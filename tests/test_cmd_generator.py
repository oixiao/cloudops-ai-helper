"""
TDD: 运维命令生成模块 — 测试用例
Red → Green → Refactor
"""
import pytest
from src.core.cmd_generator import CmdGenerator, GenerateResult


class TestCmdGenerator:
    """命令生成模块单元测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.generator = CmdGenerator(use_ai=False)

    # ========== Red Phase Tests ==========

    def test_normal_input_returns_valid_result(self):
        """测试：正常运维描述输入，返回标准化结构"""
        result = self.generator.generate("查看磁盘使用情况")
        assert isinstance(result, GenerateResult)
        assert result.command is not None
        assert len(result.command) > 0
        assert result.explanation is not None
        assert result.safety_level in ["safe", "warning", "dangerous"]

    def test_empty_input_raises_error(self):
        """测试：空输入抛出异常"""
        with pytest.raises(ValueError, match="输入不能为空"):
            self.generator.generate("")

    def test_whitespace_input_raises_error(self):
        """测试：纯空白输入抛出异常"""
        with pytest.raises(ValueError, match="输入不能为空"):
            self.generator.generate("   \t\n  ")

    def test_irrelevant_input_returns_friendly_message(self):
        """测试：与运维无关输入，返回友好提示"""
        result = self.generator.generate("今天天气怎么样")
        assert result is not None
        assert isinstance(result, GenerateResult)

    def test_result_structure_is_consistent(self):
        """测试：返回结果字段固定"""
        result = self.generator.generate("查看进程列表")
        assert hasattr(result, 'command')
        assert hasattr(result, 'explanation')
        assert hasattr(result, 'safety_level')
        assert isinstance(result.command, str)
        assert isinstance(result.explanation, str)
        assert result.safety_level in ["safe", "warning", "dangerous"]

    # ========== Specific Command Tests ==========

    def test_disk_usage_command(self):
        """测试：磁盘使用情况 → df 命令"""
        result = self.generator.generate("查看磁盘使用情况")
        assert "df" in result.command.lower()

    def test_memory_usage_command(self):
        """测试：内存查看 → free 命令"""
        result = self.generator.generate("查看内存使用情况")
        assert "free" in result.command.lower() or "top" in result.command.lower()

    def test_process_list_command(self):
        """测试：进程查看 → ps 命令"""
        result = self.generator.generate("查看所有进程")
        assert "ps" in result.command.lower()

    def test_network_check_command(self):
        """测试：网络检查 → 网络相关命令"""
        result = self.generator.generate("检查网络连通性")
        assert any(cmd in result.command.lower() for cmd in ["ping", "netstat", "ss", "curl"])

    def test_file_search_command(self):
        """测试：文件查找 → find 命令"""
        result = self.generator.generate("查找大文件")
        assert "find" in result.command.lower() or "du" in result.command.lower()

    # ========== Safety Level Tests ==========

    def test_dangerous_command_marks_safety(self):
        """测试：危险操作标记 safety_level=dangerous"""
        result = self.generator.generate("强制删除所有日志文件")
        assert result.safety_level == "dangerous"

    def test_kill_process_marks_warning(self):
        """测试：杀进程标记为 warning"""
        result = self.generator.generate("杀掉nginx进程")
        assert result.safety_level in ["warning", "dangerous"]

    def test_read_only_command_is_safe(self):
        """测试：只读命令标记为 safe"""
        result = self.generator.generate("查看系统版本")
        assert result.safety_level == "safe"

    # ========== AI Mode Tests (Mock) ==========

    def test_ai_mode_returns_valid_result(self):
        """测试：AI模式开关可正常切换"""
        gen = CmdGenerator(use_ai=False)
        assert gen.use_ai is False
        gen_ai = CmdGenerator(use_ai=True)
        assert gen_ai.use_ai is True

    def test_none_input_raises_error(self):
        """测试：None输入抛出异常"""
        with pytest.raises(ValueError):
            self.generator.generate(None)
