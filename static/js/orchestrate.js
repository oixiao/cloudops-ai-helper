/**
 * CloudOps AI — 协作工作台交互逻辑
 * SSE/轮询 + Agent状态看板渲染 + 执行日志滚动 + 诊断报告展示
 */

const API_BASE = window.location.origin;

// ==================== 工具函数 ====================
function fillExample(text) {
    document.getElementById('taskInput').value = text;
    document.getElementById('taskInput').focus();
}

// ==================== Agent 状态管理 ====================
function setAgentStatus(agent, status, task) {
    const statusEl = document.getElementById(`status-${agent}`);
    const cardEl = document.getElementById(`card-${agent}`);
    const taskEl = document.getElementById(`task-${agent}`);

    if (statusEl) {
        statusEl.className = `agent-status ${status}`;
        const statusText = {
            idle: '待命中',
            pending: '等待中',
            running: '执行中',
            done: '已完成',
            failed: '已失败',
        };
        statusEl.textContent = statusText[status] || status;
    }

    if (cardEl) {
        cardEl.className = `agent-card ${status === 'running' ? 'running' : ''} ${status === 'done' ? 'done' : ''} ${status === 'failed' ? 'failed' : ''}`;
    }

    if (taskEl && task) {
        taskEl.textContent = task.length > 50 ? task.substring(0, 50) + '...' : task;
    }
}

// ==================== 执行日志 ====================
function addLogEntry(time, agent, message) {
    const panel = document.getElementById('logPanel');
    // 清除占位文本
    const placeholder = panel.querySelector('.placeholder');
    if (placeholder) placeholder.remove();

    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `
        <span class="time">[${time}]</span>
        <span class="agent-tag">${agent}:</span>
        <span class="message">${message}</span>
    `;
    panel.appendChild(entry);
    // 自动滚动到最新
    panel.scrollTop = panel.scrollHeight;
}

// ==================== 提交任务 ====================
async function submitTask() {
    const input = document.getElementById('taskInput').value.trim();
    if (!input) {
        alert('请输入运维问题描述');
        return;
    }

    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    btn.innerHTML = '分析中';

    // 重置UI
    resetUI();
    addLogEntry('--:--:--', '系统', '收到任务，Orchestrator 正在分析意图...');
    setAgentStatus('orchestrator', 'running', '分析意图并拆解任务...');
    try {
        const resp = await fetch(`${API_BASE}/api/orchestrate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input }),
        });
        const data = await resp.json();

        if (data.code !== 0) {
            addLogEntry('--:--:--', '系统', `错误: ${data.message}`);
            setAgentStatus('orchestrator', 'failed', data.message);
            return;
        }

        // 渲染结果
        renderResult(data.data);

    } catch (e) {
        addLogEntry('--:--:--', '系统', `请求失败: ${e.message}`);
        setAgentStatus('orchestrator', 'failed', e.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-play-fill"></i> 启动协作分析';
    }
}

// ==================== 重置UI ====================
function resetUI() {
    document.getElementById('logPanel').innerHTML = '';
    document.getElementById('reportSection').style.display = 'none';
    document.getElementById('reportContent').innerHTML = '';

    ['orchestrator', 'log_analyzer', 'cmd_generator', 'script_generator'].forEach(agent => {
        setAgentStatus(agent, agent === 'orchestrator' ? 'pending' : 'idle', '');
    });
}

// ==================== 渲染结果 ====================
function renderResult(data) {
    const { plan, log_entries, summary } = data;

    // 渲染执行日志
    if (log_entries && log_entries.length > 0) {
        log_entries.forEach(entry => {
            addLogEntry(entry.time, entry.agent, entry.message);
        });
    }

    // 渲染 Agent 状态
    if (plan && plan.length > 0) {
        plan.forEach(t => {
            const agent = t.agent;
            const status = t.status === 'done' ? 'done' : t.status === 'failed' ? 'failed' : 'idle';
            setAgentStatus(agent, status, t.task || '');

            // 如果有结果，在日志中展示关键信息
            if (t.status === 'done' && t.result) {
                if (agent === 'log_analyzer') {
                    addLogEntry('--:--:--', '日志分析',
                        `${t.result.summary ? t.result.summary.substring(0, 80) : '分析完成'}`);
                } else if (agent === 'cmd_generator') {
                    addLogEntry('--:--:--', '命令生成',
                        `命令: ${t.result.command ? t.result.command.substring(0, 60) : '生成完成'}`);
                } else if (agent === 'script_generator') {
                    addLogEntry('--:--:--', '脚本生成',
                        `${t.result.description ? t.result.description.substring(0, 80) : '生成完成'}`);
                }
            } else if (t.status === 'failed') {
                addLogEntry('--:--:--', _agentLabel(agent),
                    `执行失败: ${t.result?.error || '未知错误'}`);
            }
        });
    }

    // 标记 Orchestrator 完成
    setAgentStatus('orchestrator', 'done', '任务调度完成');

    // 渲染诊断报告
    if (summary) {
        document.getElementById('reportSection').style.display = 'block';
        // 简单的 Markdown 渲染
        let html = summary
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
        document.getElementById('reportContent').innerHTML = html;
    }
}

function _agentLabel(agent) {
    const labels = {
        'log_analyzer': '日志分析',
        'cmd_generator': '命令生成',
        'script_generator': '脚本生成',
        'orchestrator': '总指挥',
    };
    return labels[agent] || '未知 Agent';
}
