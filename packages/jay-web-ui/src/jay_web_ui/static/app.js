// JayClaw Chat Application
class ChatApp {
    constructor() {
        this.chatContainer = document.getElementById('chatContainer');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.fileInput = document.getElementById('fileInput');
        this.charCount = document.getElementById('charCount');
        this.welcomeScreen = document.getElementById('welcomeScreen');

        // Panel elements
        this.sidePanel = document.getElementById('sidePanel');
        this.panelOverlay = document.getElementById('panelOverlay');
        this.panelTitle = document.getElementById('panelTitle');
        this.panelBody = document.getElementById('panelBody');

        // Model dropdown elements
        this.modelDropdown = document.getElementById('modelDropdown');
        this.modelList = document.getElementById('modelList');
        this.modelSearch = document.getElementById('modelSearch');
        this.currentModelEl = document.getElementById('currentModel');

        this.isStreaming = false;
        this.uploadedFiles = [];
        this.messageHistory = [];
        this.allModels = [];
        this.currentModel = this.currentModelEl?.textContent || '';

        this.init();
    }

    init() {
        // Show workspace selector on startup
        this.initWorkspaceModal();

        // Send
        this.sendBtn.addEventListener('click', () => this.handleSendOrCancel());
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.handleSendOrCancel(); }
        });
        this.messageInput.addEventListener('input', () => {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 160) + 'px';
            if (this.charCount) this.charCount.textContent = this.messageInput.value.length;
            this._updateSendBtn();
        });

        // File upload
        const attachBtn = document.getElementById('attachBtn');
        if (attachBtn && this.fileInput) attachBtn.addEventListener('click', () => this.fileInput.click());
        if (this.fileInput) this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        this.messageInput.addEventListener('paste', (e) => this.handlePaste(e));

        // New chat
        document.getElementById('newChatBtn')?.addEventListener('click', () => this.newChat());

        // Theme toggle
        document.getElementById('themeToggle')?.addEventListener('click', () => this.toggleTheme());

        // Quick actions
        document.querySelectorAll('.quick-action-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const text = btn.querySelector('.quick-text')?.textContent;
                if (text) { this.messageInput.value = text; this.messageInput.dispatchEvent(new Event('input')); this.sendMessage(); }
            });
        });

        // Sidebar panel buttons
        document.getElementById('sessionsBtn')?.addEventListener('click', () => this.openPanel('sessions'));
        document.getElementById('filesBtn')?.addEventListener('click', () => this.openPanel('files'));
        document.getElementById('skillsBtn')?.addEventListener('click', () => this.openPanel('skills'));
        document.getElementById('toolsBtn')?.addEventListener('click', () => this.openPanel('tools'));
        document.getElementById('configBtn')?.addEventListener('click', () => this.openPanel('config'));

        // Panel close
        document.getElementById('panelClose')?.addEventListener('click', () => this.closePanel());
        this.panelOverlay?.addEventListener('click', () => this.closePanel());

        // Model dropdown
        document.querySelector('.model-selector')?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleModelDropdown();
        });
        this.modelSearch?.addEventListener('input', () => this.filterModels());
        document.addEventListener('click', (e) => {
            if (!this.modelDropdown?.contains(e.target) && !e.target.closest('.model-selector')) {
                this.closeModelDropdown();
            }
        });

        // Restore theme
        if (localStorage.getItem('jayclaw-theme') === 'light') document.body.classList.add('light');

        this.loadHistory();
    }

    // ── Theme ──────────────────────────────────────────────────────
    toggleTheme() {
        document.body.classList.toggle('light');
        localStorage.setItem('jayclaw-theme', document.body.classList.contains('light') ? 'light' : 'dark');
    }

    // ── New Chat ───────────────────────────────────────────────────
    newChat() {
        if (this.messageHistory.length > 0 && !confirm('开始新对话？当前对话将被清除。')) return;
        this.clearHistory(false);
    }

    // ── Welcome ────────────────────────────────────────────────────
    hideWelcome() { if (this.welcomeScreen) this.welcomeScreen.style.display = 'none'; }
    showWelcome() { if (this.welcomeScreen) this.welcomeScreen.style.display = 'flex'; }

    // ── Side Panel ─────────────────────────────────────────────────
    openPanel(type) {
        const titles = { sessions: 'Sessions', files: 'Files', skills: 'Skills', tools: 'Tools', config: 'Configuration' };
        this.panelTitle.textContent = titles[type] || type;
        this.panelBody.innerHTML = '';
        this.renderPanelContent(type);
        this.sidePanel.classList.add('active');
        this.panelOverlay.classList.add('active');

        // Mark active nav item
        document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
        const btn = document.getElementById(`${type}Btn`);
        if (btn) btn.classList.add('active');
    }

    closePanel() {
        this.sidePanel.classList.remove('active');
        this.panelOverlay.classList.remove('active');
        // Restore chat as active
        document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
        document.querySelector('.nav-section .nav-item')?.classList.add('active');
    }

    renderPanelContent(type) {
        switch (type) {
            case 'sessions':
                this.renderSessions();
                break;
            case 'files':
                this.panelBody.innerHTML = `<div class="panel-empty">暂无上传文件</div>`;
                break;
            case 'skills':
                this.renderSkills();
                break;
            case 'tools':
                this.renderTools();
                break;
            case 'config':
                this.renderConfig();
                break;
        }
    }

    renderSessions() {
        const msgs = this.messageHistory.filter(m => m.role === 'user');
        if (msgs.length === 0) {
            this.panelBody.innerHTML = `<div class="panel-empty">暂无历史会话</div>`;
            return;
        }
        const html = msgs.slice(-10).reverse().map((m, i) => `
            <div class="session-item">
                <div class="session-item-title">${this.escapeHtml(m.content.slice(0, 60))}${m.content.length > 60 ? '...' : ''}</div>
                <div class="session-item-meta">消息 #${msgs.length - i}</div>
            </div>
        `).join('');
        this.panelBody.innerHTML = `<div class="panel-section-title">最近对话</div>${html}`;
    }

    renderSkills() {
        fetch('/api/skills').then(r => r.json()).then(data => {
            const skills = data.skills || [];
            const skillsHtml = skills.map(s => `
                <div class="session-item">
                    <div class="session-item-title">${this.escapeHtml(s.name || s)}</div>
                    ${s.description ? `<div class="session-item-meta">${this.escapeHtml(s.description)}</div>` : ''}
                </div>
            `).join('');

            this.panelBody.innerHTML = `
                <div class="panel-section-title">可用 Skills</div>
                ${skillsHtml || '<div class="panel-empty">暂无 Skills</div>'}
                <button class="panel-add-btn" id="addSkillBtn">+ 新增 Skill</button>
                <div class="panel-form" id="skillForm" style="display:none">
                    <input type="text" id="skillName" placeholder="Skill 名称" class="panel-input">
                    <textarea id="skillContent" placeholder="Skill 内容 (Markdown)" class="panel-textarea" rows="10"></textarea>
                    <div class="panel-form-actions">
                        <button class="panel-btn-primary" id="saveSkillBtn">保存</button>
                        <button class="panel-btn-secondary" id="cancelSkillBtn">取消</button>
                    </div>
                </div>
            `;

            document.getElementById('addSkillBtn')?.addEventListener('click', () => {
                document.getElementById('skillForm').style.display = 'block';
                document.getElementById('addSkillBtn').style.display = 'none';
            });

            document.getElementById('cancelSkillBtn')?.addEventListener('click', () => {
                document.getElementById('skillForm').style.display = 'none';
                document.getElementById('addSkillBtn').style.display = 'block';
            });

            document.getElementById('saveSkillBtn')?.addEventListener('click', () => this.saveSkill());
        }).catch(() => {
            this.panelBody.innerHTML = `<div class="panel-empty">无法加载 Skills</div>`;
        });
    }

    async saveSkill() {
        const name = document.getElementById('skillName').value.trim();
        const content = document.getElementById('skillContent').value.trim();

        // 前端验证
        if (!name) {
            this.showToast('请输入 Skill 名称', 'error');
            return;
        }
        if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
            this.showToast('Skill 名称只能包含字母、数字、下划线和连字符', 'error');
            return;
        }
        if (name.length > 50) {
            this.showToast('Skill 名称不能超过 50 字符', 'error');
            return;
        }
        if (!content) {
            this.showToast('请输入 Skill 内容', 'error');
            return;
        }
        if (!content.startsWith('#')) {
            this.showToast('Skill 内容必须以 Markdown 标题开头（# 标题）', 'error');
            return;
        }
        if (content.length < 20) {
            this.showToast('Skill 内容过短，至少需要 20 字符', 'error');
            return;
        }

        try {
            const resp = await fetch('/api/skills', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, content }),
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                this.showToast(`Skill "${name}" 已保存`, 'success');
                this.renderSkills();
            } else {
                this.showToast(`保存失败: ${data.error}`, 'error');
            }
        } catch {
            this.showToast('保存失败', 'error');
        }
    }

    renderTools() {
        fetch('/api/tools').then(r => r.json()).then(data => {
            const tools = data.tools || [];
            const toolsHtml = tools.map(t => `
                <div class="session-item">
                    <div class="session-item-title">${this.escapeHtml(t.name || t)}</div>
                    ${t.description ? `<div class="session-item-meta">${this.escapeHtml(t.description)}</div>` : ''}
                </div>
            `).join('');

            this.panelBody.innerHTML = `
                <div class="panel-section-title">可用 Tools</div>
                ${toolsHtml || '<div class="panel-empty">暂无 Tools</div>'}
                <button class="panel-add-btn" id="addToolBtn">+ 新增 Tool</button>
                <div class="panel-form" id="toolForm" style="display:none">
                    <textarea id="toolCode" placeholder="Python 代码 (使用 @tool 装饰器)" class="panel-textarea" rows="12"></textarea>
                    <div class="panel-form-actions">
                        <button class="panel-btn-primary" id="saveToolBtn">保存</button>
                        <button class="panel-btn-secondary" id="cancelToolBtn">取消</button>
                    </div>
                </div>
            `;

            document.getElementById('addToolBtn')?.addEventListener('click', () => {
                document.getElementById('toolForm').style.display = 'block';
                document.getElementById('addToolBtn').style.display = 'none';
                document.getElementById('toolCode').value = `@tool(description="我的工具")
def my_tool(arg: str) -> str:
    """工具描述"""
    return f"结果: {arg}"`;
            });

            document.getElementById('cancelToolBtn')?.addEventListener('click', () => {
                document.getElementById('toolForm').style.display = 'none';
                document.getElementById('addToolBtn').style.display = 'block';
            });

            document.getElementById('saveToolBtn')?.addEventListener('click', () => this.saveTool());
        }).catch(() => {
            this.panelBody.innerHTML = `<div class="panel-empty">无法加载 Tools</div>`;
        });
    }

    async saveTool() {
        const code = document.getElementById('toolCode').value.trim();

        // 前端验证
        if (!code) {
            this.showToast('请输入代码', 'error');
            return;
        }
        if (!code.includes('@tool')) {
            this.showToast('代码必须包含 @tool 装饰器', 'error');
            return;
        }
        if (!code.includes('def ')) {
            this.showToast('代码必须定义函数', 'error');
            return;
        }

        try {
            const resp = await fetch('/api/tools', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }),
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                this.showToast(`已添加工具: ${data.tools.join(', ')}`, 'success');
                this.renderTools();
            } else {
                this.showToast(`添加失败: ${data.error}`, 'error');
            }
        } catch {
            this.showToast('添加失败', 'error');
        }
    }

    renderConfig() {
        fetch('/api/config').then(r => r.json()).then(data => {
            const rows = Object.entries(data).map(([k, v]) => `
                <div class="config-row">
                    <div class="config-label">${this.escapeHtml(k)}</div>
                    <div class="config-value">${this.escapeHtml(String(v ?? '—'))}</div>
                </div>
            `).join('');
            this.panelBody.innerHTML = `<div class="panel-section-title">当前配置</div>${rows}`;
        }).catch(() => {
            this.panelBody.innerHTML = `<div class="panel-empty">无法加载配置</div>`;
        });
    }

    // ── Model Dropdown ─────────────────────────────────────────────
    async toggleModelDropdown() {
        if (this.modelDropdown.classList.contains('active')) {
            this.closeModelDropdown();
            return;
        }
        this.modelDropdown.classList.add('active');
        this.modelSearch.value = '';
        this.modelList.innerHTML = '<div class="model-loading">加载中...</div>';
        this.modelSearch.focus();

        try {
            const resp = await fetch('/api/models');
            const data = await resp.json();
            this.allModels = data.models || [];
            this.currentModel = data.current || this.currentModel;
            this.renderModelList(this.allModels);
        } catch {
            this.modelList.innerHTML = '<div class="model-loading">加载失败</div>';
        }
    }

    closeModelDropdown() {
        this.modelDropdown.classList.remove('active');
    }

    filterModels() {
        const q = this.modelSearch.value.toLowerCase();
        const filtered = q ? this.allModels.filter(m => m.toLowerCase().includes(q)) : this.allModels;
        this.renderModelList(filtered);
    }

    renderModelList(models) {
        if (models.length === 0) {
            this.modelList.innerHTML = '<div class="model-loading">无匹配模型</div>';
            return;
        }
        this.modelList.innerHTML = models.map(m => `
            <div class="model-option ${m === this.currentModel ? 'active' : ''}" data-model="${this.escapeHtml(m)}">
                <span class="model-option-dot"></span>
                <span class="model-option-name">${this.escapeHtml(m)}</span>
            </div>
        `).join('');
        this.modelList.querySelectorAll('.model-option').forEach(el => {
            el.addEventListener('click', () => this.selectModel(el.dataset.model));
        });
    }

    async selectModel(model) {
        try {
            const resp = await fetch('/api/model', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model }),
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                this.currentModel = model;
                if (this.currentModelEl) this.currentModelEl.textContent = model;
                this.closeModelDropdown();
                this.showToast(`已切换到 ${model}`, 'success');
            } else {
                this.showToast(`切换失败: ${data.error}`, 'error');
            }
        } catch {
            this.showToast('切换模型失败', 'error');
        }
    }

    // ── File Upload ────────────────────────────────────────────────
    async handleFileSelect(event) {
        const files = event.target.files;
        if (!files || files.length === 0) return;
        for (const file of files) await this.uploadFile(file);
        event.target.value = '';
    }

    async handlePaste(event) {
        const items = event.clipboardData?.items;
        if (!items) return;
        for (const item of items) {
            if (item.type.startsWith('image/')) {
                event.preventDefault();
                const file = item.getAsFile();
                if (file) await this.uploadFile(file);
            }
        }
    }

    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        try {
            const response = await fetch('/api/upload', { method: 'POST', body: formData });
            const data = await response.json();
            if (data.status === 'ok') {
                this.uploadedFiles.push({ filename: data.filename, path: data.path });
                this.showToast(`已上传: ${file.name}`, 'success');
            } else {
                this.showToast(`上传失败: ${data.error}`, 'error');
            }
        } catch {
            this.showToast('上传失败', 'error');
        }
    }

    // ── Toast ──────────────────────────────────────────────────────
    showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    // ── Send Button State ──────────────────────────────────────────
    _updateSendBtn() {
        const sendIcon = this.sendBtn.querySelector('.send-icon');
        if (!this.isStreaming) return;
        const hasInput = this.messageInput.value.trim().length > 0;
        if (sendIcon) sendIcon.textContent = hasInput ? '↑' : '⏹';
        this.sendBtn.title = hasInput
            ? '注入引导消息（Steering）'
            : '中止生成';
    }

    // ── Send or Cancel ─────────────────────────────────────────────
    handleSendOrCancel() {
        if (this.isStreaming) {
            const message = this.messageInput.value.trim();
            if (message) {
                this.sendInterrupt(message);
            } else {
                this.cancelGeneration();
            }
        } else {
            this.sendMessage();
        }
    }

    async sendInterrupt(message) {
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        if (this.charCount) this.charCount.textContent = '0';
        this._updateSendBtn();

        // Mark current assistant bubble as interrupted
        if (this._currentAssistantMsg) {
            this.setInterrupted(this._currentAssistantMsg);
        }

        // Insert user bubble and signal the streaming loop to create a new assistant bubble
        this.addMessage('user', message);
        this.messageHistory.push({ role: 'user', content: message });
        this._pendingNewBubble = true;

        try {
            await fetch('/api/interrupt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message }),
            });
        } catch {
            this.showToast('注入失败', 'error');
        }
    }

    async cancelGeneration() {
        try {
            await fetch('/api/cancel', { method: 'POST' });
            this.showToast('已发送中止信号', 'success');
        } catch {
            this.showToast('中止失败', 'error');
        }
    }

    // ── Send Message ───────────────────────────────────────────────
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || this.isStreaming) return;

        this.hideWelcome();
        this.addMessage('user', message);
        this.messageHistory.push({ role: 'user', content: message });

        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        if (this.charCount) this.charCount.textContent = '0';

        this.isStreaming = true;
        this._pendingNewBubble = false;
        const sendIcon = this.sendBtn.querySelector('.send-icon');
        this._updateSendBtn();

        let assistantMsg = this.addMessage('assistant', '', true);
        this._currentAssistantMsg = assistantMsg;

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message }),
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let fullContent = '';
            let cancelled = false;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop();
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.type === 'status' && data.status) {
                            if (data.status.startsWith('⛔')) {
                                // Cancelled — replace spinner with abort notice
                                cancelled = true;
                                this.setAborted(assistantMsg);
                            } else {
                                // If user injected a steering message, seal current bubble and open new one
                                if (this._pendingNewBubble) {
                                    this._pendingNewBubble = false;
                                    if (fullContent) {
                                        this.messageHistory.push({ role: 'assistant', content: fullContent });
                                    }
                                    fullContent = '';
                                    assistantMsg = this.addMessage('assistant', '', true);
                                    this._currentAssistantMsg = assistantMsg;
                                }
                                this.updateThinkingStatus(assistantMsg, data.status);
                            }
                        } else if (data.type === 'token' && data.content) {
                            if (this._pendingNewBubble) {
                                this._pendingNewBubble = false;
                                if (fullContent) {
                                    this.messageHistory.push({ role: 'assistant', content: fullContent });
                                }
                                fullContent = '';
                                assistantMsg = this.addMessage('assistant', '', true);
                                this._currentAssistantMsg = assistantMsg;
                            }
                            fullContent += data.content;
                            this.appendToMessage(assistantMsg, data.content);
                        } else if (data.type === 'error') {
                            this.setMessageError(assistantMsg, data.error);
                        }
                    } catch (_) { /* ignore */ }
                }
            }

            if (fullContent && !cancelled) this.messageHistory.push({ role: 'assistant', content: fullContent });
        } catch (e) {
            this.setMessageError(assistantMsg, `请求失败: ${e.message}`);
        } finally {
            this.isStreaming = false;
            this._pendingNewBubble = false;
            const sendIcon = this.sendBtn.querySelector('.send-icon');
            if (sendIcon) sendIcon.textContent = '↑';
            this.sendBtn.title = '发送';
            this.messageInput.focus();
        }
    }

    // ── Message Rendering ──────────────────────────────────────────
    addMessage(role, content, isStreaming = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = role === 'user' ? 'U' : 'J';

        const body = document.createElement('div');
        body.className = 'message-body';

        const meta = document.createElement('div');
        meta.className = 'message-meta';
        meta.textContent = role === 'user' ? 'You' : 'JayClaw';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        if (isStreaming) {
            contentDiv.innerHTML = `<div class="typing-indicator"><span></span><span></span><span></span></div>`;
        } else if (content) {
            this.renderContent(contentDiv, content);
        }

        // step-log lives outside message-content so renderContent never clobbers it
        const stepLog = document.createElement('div');
        stepLog.className = 'step-log';

        body.appendChild(meta);
        body.appendChild(contentDiv);
        body.appendChild(stepLog);
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(body);
        this.chatContainer.appendChild(messageDiv);
        this.scrollToBottom();
        return messageDiv;
    }

    renderContent(container, text) {
        const escaped = text
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

        // Markdown 渲染
        let html = escaped
            // 代码块
            .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
            // 行内代码
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            // 标题
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/^## (.+)$/gm, '<h2>$1</h2>')
            .replace(/^# (.+)$/gm, '<h1>$1</h1>')
            // 粗体
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            // 斜体
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            // 无序列表
            .replace(/^\- (.+)$/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
            // 有序列表
            .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
            // 链接
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
            // 换行
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>');

        container.innerHTML = `<p>${html}</p>`;
    }

    appendToMessage(messageDiv, text) {
        const contentDiv = messageDiv.querySelector('.message-content');
        contentDiv.querySelector('.typing-indicator')?.remove();
        if (!contentDiv.dataset.content) contentDiv.dataset.content = '';
        contentDiv.dataset.content += text;
        this.renderContent(contentDiv, contentDiv.dataset.content);
        this.scrollToBottom();
    }

    updateThinkingStatus(messageDiv, status) {
        const stepLog = messageDiv.querySelector('.step-log');
        if (!stepLog) return;

        // Remove the "current step" spinner line if present
        stepLog.querySelector('.step-current')?.remove();

        // Append completed step (if there was a previous current step text stored)
        const prev = stepLog.dataset.currentStep;
        if (prev) {
            const done = document.createElement('div');
            done.className = 'step-done';
            done.textContent = prev;
            stepLog.appendChild(done);
        }

        // Add new current step with animated dot
        const cur = document.createElement('div');
        cur.className = 'step-current';
        cur.innerHTML = `<span class="step-dot"></span>${status}`;
        stepLog.appendChild(cur);
        stepLog.dataset.currentStep = status;

        this.scrollToBottom();
    }

    setMessageError(messageDiv, error) {
        const contentDiv = messageDiv.querySelector('.message-content');
        const typing = contentDiv.querySelector('.typing-indicator');
        if (typing) typing.remove();
        contentDiv.innerHTML = `<span style="color:var(--warn)">⚠ ${error}</span>`;
    }

    setAborted(messageDiv) {
        const contentDiv = messageDiv.querySelector('.message-content');
        contentDiv.querySelector('.typing-indicator')?.remove();
        const stepLog = messageDiv.querySelector('.step-log');
        if (stepLog) {
            stepLog.querySelector('.step-current')?.remove();
            const notice = document.createElement('div');
            notice.className = 'step-notice';
            notice.textContent = '⛔ 已中止';
            stepLog.appendChild(notice);
        }
    }

    setInterrupted(messageDiv) {
        const contentDiv = messageDiv.querySelector('.message-content');
        contentDiv.querySelector('.typing-indicator')?.remove();
        const stepLog = messageDiv.querySelector('.step-log');
        if (stepLog) {
            stepLog.querySelector('.step-current')?.remove();
            const notice = document.createElement('div');
            notice.className = 'step-notice';
            notice.textContent = '↩ 已中断，接受补充指令';
            stepLog.appendChild(notice);
        }
    }

    scrollToBottom() {
        this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
    }

    // ── History ────────────────────────────────────────────────────
    async clearHistory(confirmFirst = true) {
        if (confirmFirst && !confirm('清除所有消息？')) return;
        try { await fetch('/api/history', { method: 'DELETE' }); } catch (_) { /* ignore */ }
        this.chatContainer.querySelectorAll('.message').forEach(m => m.remove());
        this.messageHistory = [];
        this.showWelcome();
    }

    async loadHistory() {
        try {
            const response = await fetch('/api/history');
            const data = await response.json();
            const messages = data.messages || [];
            if (messages.length > 0) {
                this.hideWelcome();
                for (const msg of messages) {
                    if (msg.role !== 'system') {
                        this.addMessage(msg.role, msg.content);
                        this.messageHistory.push(msg);
                    }
                }
            }
        } catch (_) { /* ignore */ }
    }

    // ── Utils ──────────────────────────────────────────────────────
    escapeHtml(str) {
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    async initWorkspaceModal() {
        console.log('[workspace] initWorkspaceModal called');
        const modal = document.getElementById('workspaceModal');
        const input = document.getElementById('workspaceInput');
        const confirmBtn = document.getElementById('workspaceConfirm');
        const browseBtn = document.getElementById('workspaceBrowseBtn');
        const errorEl = document.getElementById('workspaceError');
        console.log('[workspace] elements:', {modal, input, confirmBtn, browseBtn, errorEl});
        if (!modal || !input || !confirmBtn || !errorEl) {
            console.warn('[workspace] missing elements, aborting');
            return;
        }

        if (browseBtn) {
            browseBtn.addEventListener('click', async () => {
                browseBtn.disabled = true;
                browseBtn.textContent = '⏳';
                try {
                    const resp = await fetch('/api/browse/native');
                    const data = await resp.json();
                    if (data.status === 'ok' && data.path) {
                        input.value = data.path;
                        errorEl.textContent = '';
                        input.focus();
                    }
                } catch {
                    errorEl.textContent = '无法打开文件对话框';
                } finally {
                    browseBtn.disabled = false;
                    browseBtn.textContent = '📂';
                }
            });
        }

        const confirm = async () => {
            const path = input.value.trim();
            if (!path) { errorEl.textContent = '请输入或选择目录路径'; return; }
            confirmBtn.disabled = true;
            errorEl.textContent = '';
            try {
                const resp = await fetch('/api/workspace', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path }),
                });
                const data = await resp.json();
                if (data.status === 'ok') {
                    modal.classList.add('hidden');
                    this.showToast(`工作目录: ${data.workspace}`, 'success');
                } else {
                    errorEl.textContent = data.error || '设置失败';
                    confirmBtn.disabled = false;
                }
            } catch {
                errorEl.textContent = '网络错误，请重试';
                confirmBtn.disabled = false;
            }
        };

        confirmBtn.addEventListener('click', confirm);
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') confirm(); });

        fetch('/api/workspace')
            .then(r => r.json())
            .then(data => { if (data.workspace) { input.value = data.workspace; input.select(); } })
            .catch(() => {});

        input.focus();
    }
}

document.addEventListener('DOMContentLoaded', () => { new ChatApp(); });

