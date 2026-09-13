/**
 * CloudOps AI Helper — 前端交互逻辑
 * Tab切换、API调用、结果渲染
 */

const API_BASE = window.location.origin;

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
});

async function checkHealth() {
    try {
        const resp = await fetch(`${API_BASE}/api/health`);
        const data = await resp.json();
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        const pill = document.getElementById('statusIndicator');
        if (data.code === 0) {
            const aiReady = data.data?.ai_available;
            dot.className = 'status-dot online';
            pill.classList.add('is-online');
            text.textContent = aiReady ? 'AI 已就绪' : '本地模式';
        } else {
            dot.className = 'status-dot offline';
            pill.classList.remove('is-online');
            text.textContent = '离线';
        }
    } catch (e) {
        document.getElementById('statusDot').className = 'status-dot offline';
        document.getElementById('statusIndicator').classList.remove('is-online');
        document.getElementById('statusText').textContent = '服务未连接';
    }
}

// ==================== 示例填充 ====================
function fillExample(tab, text) {
    const map = {
        'cmd': 'cmdInput',
        'log': 'logInput',
        'script': 'scriptInput',
    };
    const el = document.getElementById(map[tab]);
    if (el) {
        el.value = text;
        el.focus();
    }
}

// ==================== 命令生成 ====================
async function generateCmd() {
    const input = document.getElementById('cmdInput').value.trim();
    if (!input) {
        alert('请输入运维需求描述');
        return;
    }

    const btn = document.getElementById('cmdBtn');
    const loading = document.getElementById('cmdLoading');
    const empty = document.getElementById('cmdEmpty');
    const result = document.getElementById('cmdResult');
    const copyBtn = document.getElementById('cmdCopyBtn');

    btn.disabled = true;
    btn.innerHTML = '生成中';
    empty.style.display = 'none';
    result.style.display = 'none';
    loading.style.display = 'block';

    try {
        const resp = await fetch(`${API_BASE}/api/cmd/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input }),
        });
        const data = await resp.json();

        loading.style.display = 'none';
        result.style.display = 'block';
        copyBtn.style.display = 'inline-block';

        document.getElementById('cmdCommand').textContent = data.data.command;
        document.getElementById('cmdExplanation').textContent = data.data.explanation;

        const safetyBadge = document.getElementById('cmdSafety');
        const safety = data.data.safety_level;
        safetyBadge.textContent = { safe: '✅ 安全', warning: '⚠️ 注意', dangerous: '🚫 危险' }[safety] || safety;
        safetyBadge.className = `badge badge-${safety}`;
    } catch (e) {
        loading.style.display = 'none';
        empty.style.display = 'block';
        empty.innerHTML = `<p class="text-danger">请求失败：${e.message}</p>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-lightning-charge-fill"></i> 生成命令';
    }
}

// ==================== 日志分析 ====================
async function analyzeLog() {
    const input = document.getElementById('logInput').value.trim();
    if (!input) {
        alert('请输入日志内容');
        return;
    }

    const btn = document.getElementById('logBtn');
    const loading = document.getElementById('logLoading');
    const empty = document.getElementById('logEmpty');
    const result = document.getElementById('logResult');

    btn.disabled = true;
    btn.innerHTML = '分析中';
    empty.style.display = 'none';
    result.style.display = 'none';
    loading.style.display = 'block';

    try {
        const resp = await fetch(`${API_BASE}/api/log/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input }),
        });
        const data = await resp.json();

        loading.style.display = 'none';
        result.style.display = 'block';

        const level = data.data.level;
        const levelMap = {
            normal: 'bg-success',
            warning: 'bg-warning text-dark',
            error: 'bg-danger',
            fatal: 'bg-dark text-danger border border-danger',
        };
        const levelText = { normal: '✅ 正常', warning: '⚠️ 警告', error: '❌ 错误', fatal: '💀 致命' };

        const levelBadge = document.getElementById('logLevel');
        levelBadge.textContent = levelText[level] || level;
        levelBadge.className = `badge ${levelMap[level] || 'bg-secondary'}`;

        document.getElementById('logType').textContent = `类型：${data.data.error_type}`;
        document.getElementById('logSummary').textContent = data.data.summary;
        document.getElementById('logConfidence').textContent = `${Math.round(data.data.confidence * 100)}%`;

        const stepsList = document.getElementById('logSteps');
        stepsList.innerHTML = '';
        if (data.data.steps && data.data.steps.length > 0) {
            data.data.steps.forEach((step, i) => {
                const li = document.createElement('li');
                li.textContent = `${i + 1}. ${step}`;
                stepsList.appendChild(li);
            });
        } else {
            stepsList.innerHTML = '<li class="text-muted">无需排查操作</li>';
        }
    } catch (e) {
        loading.style.display = 'none';
        empty.style.display = 'block';
        empty.innerHTML = `<p class="text-danger">请求失败：${e.message}</p>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-search"></i> 分析日志';
    }
}

// ==================== 脚本生成 ====================
async function generateScript() {
    const input = document.getElementById('scriptInput').value.trim();
    if (!input) {
        alert('请输入脚本需求描述');
        return;
    }

    const btn = document.getElementById('scriptBtn');
    const loading = document.getElementById('scriptLoading');
    const empty = document.getElementById('scriptEmpty');
    const result = document.getElementById('scriptResult');
    const copyBtn = document.getElementById('scriptCopyBtn');

    btn.disabled = true;
    btn.innerHTML = '生成中';
    empty.style.display = 'none';
    result.style.display = 'none';
    loading.style.display = 'block';

    try {
        const resp = await fetch(`${API_BASE}/api/script/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input }),
        });
        const data = await resp.json();

        loading.style.display = 'none';
        result.style.display = 'block';
        copyBtn.style.display = 'inline-block';

        document.getElementById('scriptLang').textContent = data.data.language.toUpperCase();
        document.getElementById('scriptCode').textContent = data.data.script;
        document.getElementById('scriptDesc').textContent = data.data.description;

        const warningsDiv = document.getElementById('scriptWarnings');
        warningsDiv.innerHTML = '';
        if (data.data.warnings && data.data.warnings.length > 0) {
            data.data.warnings.forEach(w => {
                const alert = document.createElement('div');
                alert.className = 'warn-item';
                alert.textContent = '⚠️ ' + w;
                warningsDiv.appendChild(alert);
            });
        }
    } catch (e) {
        loading.style.display = 'none';
        empty.style.display = 'block';
        empty.innerHTML = `<p class="text-danger">请求失败：${e.message}</p>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-file-earmark-code"></i> 生成脚本';
    }
}

// ==================== 复制功能 ====================
function copyResult(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;

    const text = el.textContent;
    navigator.clipboard.writeText(text).then(() => {
        // 简单反馈：按钮文字短暂变化
        const btn = event.target.closest('button');
        if (btn) {
            const orig = btn.textContent;
            btn.textContent = '✅ 已复制';
            setTimeout(() => { btn.textContent = orig; }, 1500);
        }
    }).catch(() => {
        // Fallback
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
    });
}
