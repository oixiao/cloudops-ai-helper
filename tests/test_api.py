"""
API接口层测试 — 命令生成、日志分析、脚本生成、多Agent协作
"""
import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


class TestHealthCheck:
    """健康检查接口测试"""

    def test_health_returns_200(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["status"] == "healthy"

    def test_health_includes_version(self):
        response = client.get("/api/health")
        data = response.json()
        assert "version" in data["data"]


class TestCmdGenerateAPI:
    """命令生成接口测试"""

    def test_valid_input_returns_command(self):
        response = client.post("/api/cmd/generate", json={"input": "查看磁盘使用情况"})
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "command" in data["data"]
        assert "explanation" in data["data"]
        assert "safety_level" in data["data"]
        assert data["data"]["safety_level"] in ["safe", "warning", "dangerous"]

    def test_empty_input_returns_422(self):
        response = client.post("/api/cmd/generate", json={"input": ""})
        assert response.status_code == 422

    def test_missing_input_returns_422(self):
        response = client.post("/api/cmd/generate", json={})
        assert response.status_code == 422

    def test_dangerous_command_returns_dangerous_safety(self):
        response = client.post("/api/cmd/generate", json={"input": "强制删除所有日志文件"})
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["safety_level"] == "dangerous"

    def test_response_has_model_field(self):
        response = client.post("/api/cmd/generate", json={"input": "查看进程"})
        data = response.json()
        assert "model" in data


class TestLogAnalyzeAPI:
    """日志分析接口测试"""

    def test_error_log_returns_analysis(self):
        response = client.post("/api/log/analyze", json={
            "input": "2024-06-01 ERROR Database connection timeout"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["level"] in ["normal", "warning", "error", "fatal"]
        assert "summary" in data["data"]
        assert "steps" in data["data"]

    def test_normal_log_returns_normal_level(self):
        response = client.post("/api/log/analyze", json={
            "input": "2024-06-01 INFO Server started successfully"
        })
        data = response.json()
        assert data["data"]["level"] == "normal"

    def test_empty_input_returns_422(self):
        response = client.post("/api/log/analyze", json={"input": ""})
        assert response.status_code == 422

    def test_oom_log_detected(self):
        response = client.post("/api/log/analyze", json={
            "input": "Out of memory: Kill process 12345 (java)"
        })
        data = response.json()
        assert data["data"]["level"] == "fatal"


class TestScriptGenerateAPI:
    """脚本生成接口测试"""

    def test_valid_input_returns_script(self):
        response = client.post("/api/script/generate", json={
            "input": "备份MySQL数据库"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "script" in data["data"]
        assert len(data["data"]["script"]) > 0
        assert "language" in data["data"]
        assert "description" in data["data"]
        assert "warnings" in data["data"]

    def test_empty_input_returns_422(self):
        response = client.post("/api/script/generate", json={"input": ""})
        assert response.status_code == 422

    def test_python_script_request(self):
        response = client.post("/api/script/generate", json={
            "input": "用Python写一个日志分析脚本"
        })
        data = response.json()
        assert data["data"]["language"] == "python"

    def test_backup_script_contains_mysqldump(self):
        response = client.post("/api/script/generate", json={
            "input": "备份MySQL数据库"
        })
        data = response.json()
        assert "mysqldump" in data["data"]["script"].lower()


class TestOrchestrateAPI:
    """多Agent协作接口测试"""

    def test_valid_input_returns_orchestration(self):
        response = client.post("/api/orchestrate", json={
            "input": "服务器CPU持续90%，dmesg日志显示OOM Killer，帮我排查"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "plan" in data["data"]
        assert "log_entries" in data["data"]
        assert "summary" in data["data"]
        assert len(data["data"]["plan"]) > 0

    def test_orchestrate_plan_has_valid_agents(self):
        response = client.post("/api/orchestrate", json={
            "input": "服务器CPU持续90%，dmesg日志显示OOM Killer，帮我排查"
        })
        data = response.json()
        valid_agents = ["log_analyzer", "cmd_generator", "script_generator"]
        for task in data["data"]["plan"]:
            assert task["agent"] in valid_agents
            assert task["status"] in ["pending", "running", "done", "failed"]

    def test_empty_input_returns_422(self):
        response = client.post("/api/orchestrate", json={"input": ""})
        assert response.status_code == 422

    def test_log_only_input_uses_log_analyzer(self):
        response = client.post("/api/orchestrate", json={
            "input": "ERROR Connection refused: connect to 10.0.0.1:3306 timeout"
        })
        data = response.json()
        agents = [t["agent"] for t in data["data"]["plan"]]
        assert "log_analyzer" in agents

    def test_orchestrate_returns_log_entries(self):
        response = client.post("/api/orchestrate", json={
            "input": "查看磁盘使用情况和内存使用情况"
        })
        data = response.json()
        assert len(data["data"]["log_entries"]) > 0
