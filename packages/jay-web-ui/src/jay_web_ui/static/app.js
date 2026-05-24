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
        this._lastContextZone = 'smart';
        this.chatTitle = document.querySelector('.chat-title');
        this.sessionTitle = 'New Chat';
        this.paletteOverlay = document.getElementById('paletteOverlay');
        this.paletteInput = document.getElementById('paletteInput');
        this.paletteList = document.getElementById('paletteList');
        this._paletteCache = { ts: 0, items: [] };
        this._paletteSelected = 0;
        this._paletteCurrentItems = [];
        this._paletteFlat = [];

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

        // Chat title click to rename
        if (this.chatTitle) {
            this.chatTitle.addEventListener('click', () => this.editSessionTitle());
        }

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
        document.getElementById('filesBtn')?.addEventListener('click', () => this.openPanel('files'));
        document.getElementById('skillsBtn')?.addEventListener('click', () => this.openPanel('skills'));
        document.getElementById('toolsBtn')?.addEventListener('click', () => this.openPanel('tools'));
        document.getElementById('mcpBtn')?.addEventListener('click', () => this.openPanel('mcp'));
        document.getElementById('configBtn')?.addEventListener('click', () => this.openPanel('config'));
        document.getElementById('handoffBtn')?.addEventListener('click', () => this.doHandoff());
        document.getElementById('compactBtn')?.addEventListener('click', () => this.doCompact());
        document.getElementById('historyBtn')?.addEventListener('click', () => this.openPanel('sessions'));
        document.getElementById('forkCancel')?.addEventListener('click', () => this.hideForkModal());
        document.querySelectorAll('.fork-option').forEach(el => {
            el.addEventListener('click', () => this.doFork(el.dataset.mode));
        });

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

        // Drag-and-drop attach (D4)
        let dragCounter = 0;
        const dropOverlay = document.getElementById('dropOverlay');
        const showOverlay = () => dropOverlay?.classList.add('active');
        const hideOverlay = () => dropOverlay?.classList.remove('active');
        document.addEventListener('dragenter', (e) => {
            if (!e.dataTransfer || !Array.from(e.dataTransfer.types).includes('Files')) return;
            dragCounter++;
            showOverlay();
        });
        document.addEventListener('dragleave', () => {
            dragCounter = Math.max(0, dragCounter - 1);
            if (dragCounter === 0) hideOverlay();
        });
        document.addEventListener('dragover', (e) => {
            if (e.dataTransfer && Array.from(e.dataTransfer.types).includes('Files')) {
                e.preventDefault();
            }
        });
        document.addEventListener('drop', (e) => {
            if (!e.dataTransfer || e.dataTransfer.files.length === 0) return;
            e.preventDefault();
            dragCounter = 0;
            hideOverlay();
            this.handleFileSelect({ target: { files: e.dataTransfer.files } });
        });

        // ⌘K / Ctrl+K — command palette (D2)
        document.addEventListener('keydown', (e) => {
            const meta = e.metaKey || e.ctrlKey;
            if (meta && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                this.openPalette();
            } else if (e.key === 'Escape' && this.paletteOverlay?.classList.contains('active')) {
                e.preventDefault();
                this.closePalette();
            }
        });
        this.paletteOverlay?.addEventListener('click', (e) => {
            if (e.target === this.paletteOverlay) this.closePalette();
        });
        this.paletteInput?.addEventListener('input', () => this.renderPalette());
        this.paletteInput?.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); this.movePaletteSelection(1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); this.movePaletteSelection(-1); }
            else if (e.key === 'Enter') { e.preventDefault(); this.executePaletteSelection(); }
        });

        // Global shortcuts (D6)
        document.getElementById('helpModalClose')?.addEventListener('click', () => {
            document.getElementById('helpModal')?.classList.remove('active');
        });
        document.getElementById('helpModal')?.addEventListener('click', (e) => {
            if (e.target.id === 'helpModal') e.target.classList.remove('active');
        });
        document.addEventListener('keydown', (e) => {
            const meta = e.metaKey || e.ctrlKey;
            const inTextField = ['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName);

            // Esc — close top-most surface (palette is handled in its own listener)
            if (e.key === 'Escape') {
                const helpModal = document.getElementById('helpModal');
                if (helpModal?.classList.contains('active')) {
                    helpModal.classList.remove('active');
                    return;
                }
                if (this.paletteOverlay?.classList.contains('active')) {
                    return; // palette has its own Esc handler
                }
                if (this.sidePanel?.classList.contains('active')) {
                    this.closePanel();
                    return;
                }
                if (this.modelDropdown?.classList.contains('active')) {
                    this.closeModelDropdown();
                    return;
                }
            }

            // ⌘N — new chat
            if (meta && e.key.toLowerCase() === 'n') {
                e.preventDefault();
                this.newChat();
                return;
            }
            // ⌘L — clear view
            if (meta && e.key.toLowerCase() === 'l') {
                e.preventDefault();
                this.clearView();
                return;
            }
            // ⌘Enter — force send (only inside the message input)
            if (meta && e.key === 'Enter' && document.activeElement === this.messageInput) {
                e.preventDefault();
                this.handleSendOrCancel();
                return;
            }
            // ⌘/ — toggle help
            if (meta && e.key === '/') {
                e.preventDefault();
                document.getElementById('helpModal')?.classList.toggle('active');
                return;
            }
            // ? — help (when not typing in a text field)
            if (e.key === '?' && !inTextField) {
                e.preventDefault();
                document.getElementById('helpModal')?.classList.add('active');
                return;
            }
            // ⌘↑ / ⌘↓ — jump between user messages (skip inside the textarea so users can move the cursor)
            if (meta && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
                if (inTextField && document.activeElement === this.messageInput) return;
                e.preventDefault();
                this._jumpUserMessage(e.key === 'ArrowUp' ? -1 : 1);
                return;
            }
        });

        this.loadHistory();
    }

    // ── Theme ──────────────────────────────────────────────────────
    toggleTheme() {
        document.body.classList.toggle('light');
        localStorage.setItem('jayclaw-theme', document.body.classList.contains('light') ? 'light' : 'dark');
    }

    // ── New Chat ───────────────────────────────────────────────────
    async newChat() {
        if (this.messageHistory.length === 0) return;

        // Offer to summarize this session into AGENTS.md before clearing.
        // Only if AGENTS.md exists in the workspace AND the session has real content (>= 2 user turns).
        const userTurns = this.messageHistory.filter(m => m.role === 'user').length;
        const status = await this._fetchAgentsMdStatus();
        if (status && status.exists && userTurns >= 2) {
            // Show modal; the user decides: analyze + write, or skip
            const proceed = await this.showAgentsSummaryModal();
            if (proceed === 'cancel') return;  // user backed out entirely
        }

        // Save current conversation as a session before clearing
        try { await fetch('/api/fork', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({mode:'session_only'}) }); } catch {}
        await this.clearHistory(false);
        this.setSessionTitle('New Chat');
        this.sessionTitle = 'New Chat';
    }

    // ── Welcome ────────────────────────────────────────────────────
    hideWelcome() { if (this.welcomeScreen) this.welcomeScreen.style.display = 'none'; }
    showWelcome() { if (this.welcomeScreen) this.welcomeScreen.style.display = 'flex'; }

    // ── Side Panel ─────────────────────────────────────────────────
    openPanel(type) {
        const titles = { sessions: 'Sessions', files: 'Files', skills: 'Skills', tools: 'Tools', config: 'Configuration', mcp: 'MCP Servers' };
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
                this.renderFiles();
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
            case 'mcp':
                this.renderMcp();
                break;
        }
    }

    renderFiles() {
        this.panelBody.innerHTML = '<div class="panel-empty">加载中...</div>';
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 5000);
        fetch('/api/files', {signal: ctrl.signal}).then(r => r.json()).then(data => {
            clearTimeout(timer);
            const files = data.files || [];
            if (files.length === 0) {
                this.panelBody.innerHTML = '<div class="panel-empty">暂无上传文件</div>';
                return;
            }
            const html = files.map(f => {
                const size = f.size < 1024 ? `${f.size} B` : f.size < 1048576 ? `${(f.size/1024).toFixed(1)} KB` : `${(f.size/1048576).toFixed(1)} MB`;
                const date = new Date(f.modified * 1000).toLocaleString('zh-CN', {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
                const ext = (f.filename.split('.').pop() || '?').toUpperCase().slice(0, 4);
                return `<div class="session-item file-item" data-filename="${this.escapeHtml(f.filename)}">
                    <div class="session-item-title"><span class="att-ext">${ext}</span> ${this.escapeHtml(f.filename)}</div>
                    <div class="session-item-meta">${size} · ${date}</div>
                    <button class="file-delete-btn" data-filename="${this.escapeHtml(f.filename)}" title="删除">✕</button>
                </div>`;
            }).join('');
            this.panelBody.innerHTML = `<div class="panel-section-title">已上传文件 (${files.length})</div>${html}`;
            this.panelBody.querySelectorAll('.file-delete-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.deleteFile(btn.dataset.filename);
                });
            });
        }).catch(() => {
            clearTimeout(timer);
            this.panelBody.innerHTML = '<div class="panel-empty">加载失败，服务可能繁忙</div>';
        });
    }

    async deleteFile(filename) {
        if (!confirm(`删除文件 ${filename}？`)) return;
        try {
            const resp = await fetch('/api/files', {
                method: 'DELETE',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({filename}),
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                this.showToast(`已删除: ${filename}`, 'success');
                this.renderFiles();
            } else {
                this.showToast(data.error || '删除失败', 'error');
            }
        } catch { this.showToast('删除失败', 'error'); }
    }

    renderSessions() {
        this.panelBody.innerHTML = '<div class="panel-empty">加载中...</div>';
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 5000);
        fetch('/api/sessions', {signal: ctrl.signal}).then(r => r.json()).then(data => {
            clearTimeout(timer);
            const sessions = data.sessions || [];
            if (sessions.length === 0) {
                this.panelBody.innerHTML = '<div class="panel-empty">暂无历史会话</div>';
                return;
            }
            const html = sessions.map(s => {
                const date = new Date(s.modified).toLocaleString('zh-CN', {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
                return `<div class="session-item session-clickable" data-path="${this.escapeHtml(s.path)}">
                    <div class="session-item-title">${this.escapeHtml(s.name)}</div>
                    <div class="session-item-meta">${date} · ${s.entries} 条消息</div>
                    <button class="file-delete-btn session-delete-btn" data-path="${this.escapeHtml(s.path)}" title="删除">✕</button>
                </div>`;
            }).join('');
            this.panelBody.innerHTML = `<div class="panel-section-title">已保存会话</div>${html}`;
            this.panelBody.querySelectorAll('.session-clickable').forEach(el => {
                el.addEventListener('click', (e) => {
                    if (e.target.closest('.session-delete-btn')) return;
                    this.loadSession(el.dataset.path);
                });
            });
            this.panelBody.querySelectorAll('.session-delete-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.deleteSession(btn.dataset.path);
                });
            });
        }).catch(() => {
            clearTimeout(timer);
            this.panelBody.innerHTML = '<div class="panel-empty">加载失败，服务可能繁忙</div>';
        });
    }

    async deleteSession(path) {
        if (!confirm('删除此会话？')) return;
        try {
            const resp = await fetch('/api/sessions', {
                method: 'DELETE',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({path}),
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                this.showToast('会话已删除', 'success');
                this.renderSessions();
            } else {
                this.showToast(data.error || '删除失败', 'error');
            }
        } catch { this.showToast('删除失败', 'error'); }
    }

    renderSkills() {
        this.panelBody.innerHTML = '<div class="panel-empty">加载中...</div>';
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 5000);
        fetch('/api/skills', {signal: ctrl.signal}).then(r => r.json()).then(data => {
            clearTimeout(timer);
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
            this.panelBody.innerHTML = `<div class="panel-empty">加载失败，服务可能繁忙</div>`;
            clearTimeout(timer);
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
        this.panelBody.innerHTML = '<div class="panel-empty">加载中...</div>';
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 5000);
        fetch('/api/tools', {signal: ctrl.signal}).then(r => r.json()).then(data => {
            clearTimeout(timer);
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
            this.panelBody.innerHTML = `<div class="panel-empty">加载失败，服务可能繁忙</div>`;
            clearTimeout(timer);
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
        this.panelBody.innerHTML = '<div class="panel-empty">加载中...</div>';
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 5000);
        Promise.all([
            fetch('/api/config', {signal: ctrl.signal}).then(r => r.json()),
            fetch('/api/vision-model', {signal: ctrl.signal}).then(r => r.json()),
            fetch('/api/models', {signal: ctrl.signal}).then(r => r.json()).catch(() => ({models: []})),
        ]).then(([data, visionData, modelsData]) => {
            clearTimeout(timer);
            const rows = Object.entries(data).map(([k, v]) => `
                <div class="config-row">
                    <div class="config-label">${this.escapeHtml(k)}</div>
                    <div class="config-value">${this.escapeHtml(String(v ?? '—'))}</div>
                </div>
            `).join('');

            const currentVision = visionData.vision_model || '';
            const models = modelsData.models || [];
            const modelOptions = models.map(m =>
                `<option value="${this.escapeHtml(m)}" ${m === currentVision ? 'selected' : ''}>${this.escapeHtml(m)}</option>`
            ).join('');

            this.panelBody.innerHTML = `
                <div class="panel-section-title">当前配置</div>${rows}
                <div class="panel-section-title" style="margin-top:16px">视觉模型降级</div>
                <div class="config-row">
                    <div class="config-label">视觉模型</div>
                    <div class="config-value">
                        <select id="visionModelSelect" class="panel-input" style="width:100%;padding:4px 8px">
                            <option value="">不降级（直接发给主模型）</option>
                            ${modelOptions}
                        </select>
                    </div>
                </div>
                <div class="config-row" style="opacity:0.7;font-size:12px">
                    <div class="config-label"></div>
                    <div class="config-value">当主模型不支持视觉时，先用此模型描述图片内容</div>
                </div>
            `;

            document.getElementById('visionModelSelect')?.addEventListener('change', async (e) => {
                const model = e.target.value;
                const resp = await fetch('/api/vision-model', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({model}),
                });
                const result = await resp.json();
                if (result.status === 'ok') {
                    this.showToast(model ? `视觉模型已设为 ${model}` : '已关闭视觉模型降级', 'success');
                }
            });
        }).catch(() => {
            this.panelBody.innerHTML = `<div class="panel-empty">加载失败，服务可能繁忙</div>`;
            clearTimeout(timer);
        });
    }

    renderMcp() {
        this.panelBody.innerHTML = '<div class="panel-empty">加载中...</div>';
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 5000);
        fetch('/api/mcp/servers', {signal: ctrl.signal}).then(r => r.json()).then(data => {
            clearTimeout(timer);
            const servers = data.servers || [];
            const statusDot = (s) => s === 'running' ? '🟢' : s === 'error' ? '🔴' : '⚪';
            const serversHtml = servers.map(s => `
                <div class="session-item mcp-server-item">
                    <div class="session-item-title">${statusDot(s.status)} ${this.escapeHtml(s.name)}</div>
                    <div class="session-item-meta">${s.tools.length} tools · ${s.status}${s.error ? ' · ' + this.escapeHtml(s.error) : ''}</div>
                    ${s.tools.length ? `<div class="mcp-tools-list">${s.tools.map(t => `<span class="mcp-tool-tag">${this.escapeHtml(t.name)}</span>`).join(' ')}</div>` : ''}
                    <div class="mcp-server-actions">
                        <button class="panel-btn-secondary mcp-restart-btn" data-name="${this.escapeHtml(s.name)}">重启</button>
                        <button class="panel-btn-secondary mcp-remove-btn" data-name="${this.escapeHtml(s.name)}">删除</button>
                    </div>
                </div>
            `).join('');

            this.panelBody.innerHTML = `
                <div class="panel-section-title">MCP Servers</div>
                ${serversHtml || '<div class="panel-empty">暂无 MCP 服务器</div>'}
                <button class="panel-add-btn" id="addMcpBtn">+ 添加 MCP Server</button>
                <div class="panel-form" id="mcpForm" style="display:none">
                    <input type="text" id="mcpName" placeholder="名称 (如 filesystem)" class="panel-input">
                    <input type="text" id="mcpCommand" placeholder="命令 (如 npx)" class="panel-input">
                    <input type="text" id="mcpArgs" placeholder="参数 (逗号分隔)" class="panel-input">
                    <textarea id="mcpEnv" placeholder="环境变量 (每行 KEY=VALUE)" class="panel-textarea" rows="3"></textarea>
                    <div class="panel-form-actions">
                        <button class="panel-btn-primary" id="saveMcpBtn">添加</button>
                        <button class="panel-btn-secondary" id="cancelMcpBtn">取消</button>
                    </div>
                </div>
            `;

            document.getElementById('addMcpBtn')?.addEventListener('click', () => {
                document.getElementById('mcpForm').style.display = 'block';
                document.getElementById('addMcpBtn').style.display = 'none';
            });
            document.getElementById('cancelMcpBtn')?.addEventListener('click', () => {
                document.getElementById('mcpForm').style.display = 'none';
                document.getElementById('addMcpBtn').style.display = 'block';
            });
            document.getElementById('saveMcpBtn')?.addEventListener('click', () => this.saveMcpServer());
            this.panelBody.querySelectorAll('.mcp-restart-btn').forEach(btn => {
                btn.addEventListener('click', () => this.restartMcpServer(btn.dataset.name));
            });
            this.panelBody.querySelectorAll('.mcp-remove-btn').forEach(btn => {
                btn.addEventListener('click', () => this.removeMcpServer(btn.dataset.name));
            });
        }).catch(() => {
            clearTimeout(timer);
            this.panelBody.innerHTML = '<div class="panel-empty">加载失败</div>';
        });
    }

    async saveMcpServer() {
        const name = document.getElementById('mcpName').value.trim();
        const command = document.getElementById('mcpCommand').value.trim();
        const argsStr = document.getElementById('mcpArgs').value.trim();
        const envStr = document.getElementById('mcpEnv').value.trim();
        if (!name || !command) { this.showToast('名称和命令为必填', 'error'); return; }
        const args = argsStr ? argsStr.split(',').map(s => s.trim()).filter(Boolean) : [];
        const env = {};
        if (envStr) {
            for (const line of envStr.split('\n')) {
                const idx = line.indexOf('=');
                if (idx > 0) env[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
            }
        }
        try {
            const resp = await fetch('/api/mcp/servers', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name, command, args, env}),
            });
            const data = await resp.json();
            if (data.status === 'ok') { this.showToast(`MCP "${name}" 已添加`, 'success'); this.renderMcp(); }
            else { this.showToast(data.error || '添加失败', 'error'); }
        } catch { this.showToast('添加失败', 'error'); }
    }

    async restartMcpServer(name) {
        try {
            const resp = await fetch(`/api/mcp/servers/${encodeURIComponent(name)}/restart`, {method: 'POST'});
            const data = await resp.json();
            if (data.status === 'ok') { this.showToast(`"${name}" 已重启`, 'success'); this.renderMcp(); }
            else { this.showToast(data.error || '重启失败', 'error'); }
        } catch { this.showToast('重启失败', 'error'); }
    }

    async removeMcpServer(name) {
        if (!confirm(`删除 MCP 服务器 "${name}"？`)) return;
        try {
            const resp = await fetch(`/api/mcp/servers/${encodeURIComponent(name)}`, {method: 'DELETE'});
            const data = await resp.json();
            if (data.status === 'ok') { this.showToast(`"${name}" 已删除`, 'success'); this.renderMcp(); }
            else { this.showToast(data.error || '删除失败', 'error'); }
        } catch { this.showToast('删除失败', 'error'); }
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
                this.uploadedFiles.push({ filename: data.filename, path: data.path, size: data.size, type: data.type });
                this._renderAttachments();
                this.showToast(`已上传: ${file.name}`, 'success');
            } else {
                this.showToast(`上传失败: ${data.error}`, 'error');
            }
        } catch {
            this.showToast('上传失败', 'error');
        }
    }

    _renderAttachments() {
        const row = document.getElementById('attachmentRow');
        if (!row) return;
        if (this.uploadedFiles.length === 0) { row.innerHTML = ''; return; }
        row.innerHTML = this.uploadedFiles.map((f, i) => {
            const ext = (f.filename.split('.').pop() || '?').toUpperCase().slice(0, 4);
            return `<div class="attachment-chip">
                <span class="att-ext">${this.escapeHtml(ext)}</span>
                <span class="att-name" title="${this.escapeHtml(f.path)}">${this.escapeHtml(f.filename)}</span>
                <button class="att-remove" data-idx="${i}" title="移除">×</button>
            </div>`;
        }).join('');
        row.querySelectorAll('.att-remove').forEach(btn => {
            btn.addEventListener('click', () => {
                this.uploadedFiles.splice(parseInt(btn.dataset.idx), 1);
                this._renderAttachments();
            });
        });
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
        let message = this.messageInput.value.trim();
        if (!message || this.isStreaming) return;

        // Collect attachments to send with the request
        const attachments = this.uploadedFiles.length > 0
            ? this.uploadedFiles.map(f => ({filename: f.filename, path: f.path, type: f.type, size: f.size}))
            : null;

        // Show attachment names in the displayed message (for user reference only)
        let displayMessage = message;
        if (attachments) {
            const names = attachments.map(f => f.filename).join(', ');
            displayMessage = `📎 ${names}\n\n${message}`;
        }

        this.hideWelcome();
        this.addMessage('user', displayMessage);
        this.messageHistory.push({ role: 'user', content: displayMessage });

        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        if (this.charCount) this.charCount.textContent = '0';
        this.uploadedFiles = [];
        this._renderAttachments();

        this.isStreaming = true;
        this._pendingNewBubble = false;
        const sendIcon = this.sendBtn.querySelector('.send-icon');
        this._updateSendBtn();

        // Auto-title on first user message
        if (this.messageHistory.length === 1 && this.sessionTitle === 'New Chat') {
            const title = message.slice(0, 30).replace(/\n/g, ' ') + (message.length > 30 ? '...' : '');
            this.setSessionTitle(title);
        }

        let assistantMsg = this.addMessage('assistant', '', true);
        this._currentAssistantMsg = assistantMsg;

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message, attachments }),
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
                        } else if (data.type === 'message_start' && data.id) {
                            // Tag the DOM node with the message id (D3 needs this for truncate/edit).
                            if (this._currentAssistantMsg) {
                                this._currentAssistantMsg.dataset.messageId = data.id;
                            }
                        } else if (data.type === 'message_end' && data.id) {
                            // Final-pass render is triggered after the reader loop ends — nothing
                            // extra to do here, but keep the case so unknown-event-type fallbacks
                            // don't accidentally treat this as an error.
                        } else if (data.type === 'error') {
                            this.setMessageError(assistantMsg, data.error);
                        }
                    } catch (_) { /* ignore */ }
                }
            }

            // Streaming finished — flush throttled render and finalize (highlight + copy buttons).
            if (assistantMsg) this.finalizeMessage(assistantMsg);

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
            this._updateContextMeter();
            // Clear streaming status indicator
            if (assistantMsg) {
                const stepCur = assistantMsg.querySelector('.step-current');
                if (stepCur) stepCur.remove();
                // Add fork button to completed assistant message
                const meta = assistantMsg.querySelector('.message-meta');
                if (meta && !meta.querySelector('.msg-fork-btn')) {
                    const forkIcon = document.createElement('button');
                    forkIcon.className = 'msg-fork-btn';
                    forkIcon.title = 'Fork from here';
                    forkIcon.textContent = '⑂';
                    forkIcon.addEventListener('click', () => this.forkAtMessage(assistantMsg));
                    meta.appendChild(forkIcon);
                }
            }
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

        // Fork button on assistant messages
        if (role === 'assistant' && !isStreaming) {
            const forkIcon = document.createElement('button');
            forkIcon.className = 'msg-fork-btn';
            forkIcon.title = 'Fork from here';
            forkIcon.textContent = '⑂';
            forkIcon.addEventListener('click', () => this.forkAtMessage(messageDiv));
            meta.appendChild(forkIcon);
        }

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

        // D3 hover action row — Copy on all, Resend/Edit on user messages.
        // Edit visibility is managed by _refreshEditButtons() after streaming ends.
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        const copyBtn = document.createElement('button');
        copyBtn.className = 'message-action-btn';
        copyBtn.dataset.action = 'copy';
        copyBtn.title = '复制';
        copyBtn.setAttribute('aria-label', 'Copy');
        copyBtn.textContent = '⎘';
        copyBtn.addEventListener('click', () => this.copyMessage(messageDiv));
        actions.appendChild(copyBtn);
        if (role === 'user') {
            const resendBtn = document.createElement('button');
            resendBtn.className = 'message-action-btn';
            resendBtn.dataset.action = 'resend';
            resendBtn.title = '重发';
            resendBtn.setAttribute('aria-label', 'Resend');
            resendBtn.textContent = '⟳';
            resendBtn.addEventListener('click', () => this.resendMessage(messageDiv));
            actions.appendChild(resendBtn);

            const editBtn = document.createElement('button');
            editBtn.className = 'message-action-btn';
            editBtn.dataset.action = 'edit';
            editBtn.title = '编辑';
            editBtn.setAttribute('aria-label', 'Edit');
            editBtn.hidden = true;  // _refreshEditButtons reveals only the latest user message's edit btn.
            editBtn.textContent = '✎';
            editBtn.addEventListener('click', () => this.editMessage(messageDiv));
            actions.appendChild(editBtn);
        }
        body.appendChild(actions);

        // Store the raw text for Copy/Resend retrieval.
        messageDiv.dataset.raw = content || '';

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(body);
        this.chatContainer.appendChild(messageDiv);
        this.scrollToBottom();
        if (role === 'user') this._refreshEditButtons();
        return messageDiv;
    }

    renderContent(container, text) {
        // Configure marked once (idempotent).
        if (!window._markedConfigured) {
            window.marked.setOptions({
                gfm: true,
                breaks: false,
                headerIds: false,
                mangle: false,
            });
            window._markedConfigured = true;
        }

        const rawHtml = window.marked.parse(text || '');
        const safeHtml = window.DOMPurify.sanitize(rawHtml, {
            ALLOWED_ATTR: ['href', 'title', 'class', 'target', 'rel', 'colspan', 'rowspan', 'align'],
            ADD_ATTR: ['target', 'rel'],
            FORBID_TAGS: ['script', 'style', 'iframe', 'object'],
        });
        container.innerHTML = safeHtml;

        // External links open in new tab safely.
        container.querySelectorAll('a[href]').forEach((a) => {
            const href = a.getAttribute('href') || '';
            if (/^https?:/i.test(href)) {
                a.setAttribute('target', '_blank');
                a.setAttribute('rel', 'noopener noreferrer');
            }
        });
    }

    finalizeMessageRender(container) {
        // Final-pass: highlight code blocks and install copy buttons.
        // Called once per message after stream ends.
        container.querySelectorAll('pre > code').forEach((codeEl) => {
            // Wrap in chrome
            const pre = codeEl.parentElement;
            if (pre.parentElement?.classList.contains('code-block')) return;
            const wrapper = document.createElement('div');
            wrapper.className = 'code-block';
            const lang = (codeEl.className.match(/language-(\w+)/) || [, 'text'])[1];
            wrapper.innerHTML = `
                <div class="code-block-header">
                    <span class="code-block-lang">${lang}</span>
                    <button class="code-block-copy" type="button" aria-label="Copy">
                        <span class="copy-label">Copy</span>
                    </button>
                </div>
            `;
            pre.parentElement.insertBefore(wrapper, pre);
            wrapper.appendChild(pre);

            // Highlight
            try { window.hljs.highlightElement(codeEl); }
            catch (e) { /* unknown language — leave plain */ }

            // Collapse if > 20 lines
            const lineCount = (codeEl.textContent || '').split('\n').length;
            if (lineCount > 20) {
                wrapper.classList.add('collapsed');
                const expand = document.createElement('button');
                expand.className = 'code-block-expand';
                expand.type = 'button';
                expand.textContent = `Expand ${lineCount - 20} more lines`;
                expand.addEventListener('click', () => wrapper.classList.remove('collapsed'));
                wrapper.appendChild(expand);
            }

            // Copy button
            wrapper.querySelector('.code-block-copy').addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(codeEl.textContent || '');
                    const btn = wrapper.querySelector('.code-block-copy');
                    btn.classList.add('copied');
                    btn.querySelector('.copy-label').textContent = '✓ Copied';
                    setTimeout(() => {
                        btn.classList.remove('copied');
                        btn.querySelector('.copy-label').textContent = 'Copy';
                    }, 1500);
                } catch (_) { /* clipboard denied */ }
            });
        });
    }

    appendToMessage(messageDiv, text) {
        const contentDiv = messageDiv.querySelector('.message-content');
        contentDiv.querySelector('.typing-indicator')?.remove();
        if (!contentDiv.dataset.content) contentDiv.dataset.content = '';
        contentDiv.dataset.content += text;
        messageDiv.dataset.raw = contentDiv.dataset.content;

        // Throttle rerenders to ~200ms during streaming — avoids per-token reparses.
        if (!messageDiv._renderScheduled) {
            messageDiv._renderScheduled = setTimeout(() => {
                messageDiv._renderScheduled = null;
                this.renderContent(contentDiv, contentDiv.dataset.content);
                this.scrollToBottom();
            }, 200);
        }
    }

    finalizeMessage(messageDiv) {
        // Called when streaming ends. Flushes any pending throttled render
        // and runs the final highlight + copy-button pass.
        if (messageDiv._renderScheduled) {
            clearTimeout(messageDiv._renderScheduled);
            messageDiv._renderScheduled = null;
        }
        const contentDiv = messageDiv.querySelector('.message-content');
        if (contentDiv && contentDiv.dataset.content) {
            this.renderContent(contentDiv, contentDiv.dataset.content);
        }
        if (contentDiv) this.finalizeMessageRender(contentDiv);
        this._refreshEditButtons();
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
        contentDiv.innerHTML = '';
        const span = document.createElement('span');
        span.style.color = 'var(--warn)';
        span.textContent = `⚠ ${error}`;
        contentDiv.appendChild(span);
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

    // ── Session Title ──────────────────────────────────────────────
    setSessionTitle(title) {
        this.sessionTitle = title;
        if (this.chatTitle) this.chatTitle.textContent = title;
        fetch('/api/session/rename', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: title}),
        }).catch(() => {});
    }

    editSessionTitle() {
        const newName = prompt('会话名称:', this.sessionTitle);
        if (newName && newName.trim()) {
            this.setSessionTitle(newName.trim());
        }
    }

    // ── Utils ──────────────────────────────────────────────────────
    escapeHtml(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
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
                    // After workspace is set, decide whether to offer AGENTS.md initialization
                    this.maybeShowAgentsInitModal();
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
            .then(data => {
                if (data.workspace) {
                    input.value = data.workspace;
                    modal.classList.add('hidden');
                    this.maybeShowAgentsInitModal();
                }
            })
            .catch(() => {});

        input.focus();
    }


    // ── Context Meter ──────────────────────────────────────────────
    _updateContextMeter() {
        fetch('/api/context').then(r => r.json()).then(data => {
            const meter = document.getElementById('contextMeter');
            if (!meter || !data.available) return;
            const bar = meter.querySelector('.ctx-bar-fill');
            const label = meter.querySelector('.ctx-label');
            bar.style.width = `${data.percent}%`;
            bar.dataset.zone = data.zone;
            label.textContent = `${data.percent}%`;
            meter.style.display = 'flex';
            if (this._lastContextZone === 'smart' && data.zone !== 'smart') {
                this.showToast('上下文窗口已超过 40%，模型效果可能下降', 'warning');
            }
            this._lastContextZone = data.zone;
        }).catch(() => {});
    }

    // ── Session Load ────────────────────────────────────────────
    loadSession(path) {
        fetch('/api/sessions/load', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path }),
        }).then(r => r.json()).then(data => {
            if (data.status !== 'ok') { this.showToast(data.error || '加载失败', 'error'); return; }
            this.messageHistory = data.messages || [];
            // Re-render chat
            const msgs = this.chatContainer.querySelectorAll('.message');
            msgs.forEach(m => m.remove());
            this.hideWelcome();
            for (const m of this.messageHistory) {
                this.addMessage(m.role, m.content);
            }
            // Update session title from first user message
            const firstUser = this.messageHistory.find(m => m.role === 'user');
            if (firstUser) {
                const title = firstUser.content.slice(0, 30).replace(/\n/g, ' ') + (firstUser.content.length > 30 ? '...' : '');
                this.sessionTitle = title;
                if (this.chatTitle) this.chatTitle.textContent = title;
            }
            this.closePanel();
            this.showToast('会话已加载', 'success');
        }).catch(() => this.showToast('加载失败', 'error'));
    }

    // ── Fork ──────────────────────────────────────────────────────
    forkAtMessage(messageDiv) {
        // Find the index of this message in messageHistory
        const allMsgs = [...this.chatContainer.querySelectorAll('.message')];
        const idx = allMsgs.indexOf(messageDiv);
        this._forkIndex = idx;
        document.getElementById('forkModal').style.display = 'flex';
    }
    showForkModal() { document.getElementById('forkModal').style.display = 'flex'; this._forkIndex = -1; }
    hideForkModal() { document.getElementById('forkModal').style.display = 'none'; }

    async doFork(mode) {
        this.hideForkModal();
        try {
            const resp = await fetch('/api/fork', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode, fork_index: this._forkIndex }),
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                this.showToast(data.detail || 'Fork 完成', 'success');
                // Clear UI and re-render retained messages
                this.chatContainer.querySelectorAll('.message').forEach(m => m.remove());
                this.messageHistory = [];
                const retained = data.retained || [];
                if (retained.length > 0) {
                    this.hideWelcome();
                    for (const msg of retained) {
                        if (msg.role !== 'system') {
                            this.addMessage(msg.role, msg.content);
                            this.messageHistory.push(msg);
                        }
                    }
                } else {
                    this.showWelcome();
                }
            } else {
                this.showToast(data.error || 'Fork 失败', 'error');
            }
        } catch { this.showToast('Fork 失败', 'error'); }
    }

    // ── Compact ────────────────────────────────────────────────────
    async doCompact() {
        if (this.isStreaming) { this.showToast('请等待当前生成完成', 'error'); return; }
        const btn = document.getElementById('compactBtn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span>⊘</span><span>压缩中...</span>'; }
        try {
            const resp = await fetch('/api/compact', { method: 'POST' });
            const data = await resp.json();
            if (data.status === 'ok') {
                this.showToast(`上下文已压缩: ${data.before} → ${data.after} 条消息`, 'success');
                this._updateContextMeter();
            } else {
                this.showToast(data.error || '压缩失败', 'error');
            }
        } catch { this.showToast('压缩失败', 'error'); }
        finally { if (btn) { btn.disabled = false; btn.innerHTML = '<span>⊘</span><span>Compact</span>'; } }
    }

    // ── Handoff ────────────────────────────────────────────────────
    async doHandoff() {
        const btn = document.getElementById('handoffBtn');
        const origHTML = btn ? btn.innerHTML : null;
        if (btn) { btn.disabled = true; btn.innerHTML = '<span>⇥</span><span>生成中...</span>'; }
        try {
            const resp = await fetch('/api/handoff', { method: 'POST' });
            const data = await resp.json();
            if (data.status === 'ok') {
                const where = data.relative_path || data.path;
                const tag = data.mode === 'llm' ? 'LLM' : '模板';
                this.showToast(`Handoff 已生成 (${tag}): ${where}`, 'success');
            } else {
                this.showToast(`Handoff 失败: ${data.error}`, 'error');
            }
        } catch {
            this.showToast('Handoff 生成失败', 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = origHTML; }
        }
    }

    // ── AGENTS.md (init + session-end summarize) ──────────────────
    async _fetchAgentsMdStatus() {
        try {
            const resp = await fetch('/api/agents-md/status');
            return await resp.json();
        } catch {
            return null;
        }
    }

    async maybeShowAgentsInitModal() {
        const status = await this._fetchAgentsMdStatus();
        if (!status || !status.suggest_prompt) return;
        this.showAgentsInitModal();
    }

    showAgentsInitModal() {
        const modal = document.getElementById('agentsInitModal');
        const statusEl = document.getElementById('agentsInitStatus');
        const cancelBtn = document.getElementById('agentsInitCancel');
        if (!modal) return;

        statusEl.textContent = '';
        statusEl.className = 'agents-modal-status';
        cancelBtn.style.display = 'none';
        modal.style.display = 'flex';

        const options = modal.querySelectorAll('.agents-option');
        const setBusy = (busy) => {
            options.forEach(o => { o.style.pointerEvents = busy ? 'none' : ''; o.style.opacity = busy ? '0.5' : '1'; });
            cancelBtn.style.display = busy ? 'inline-block' : 'none';
        };

        const handleAction = async (action) => {
            statusEl.className = 'agents-modal-status';
            if (action === 'generate') {
                setBusy(true);
                statusEl.textContent = '正在扫描目录并请求 LLM 起草...';
                try {
                    const resp = await fetch('/api/agents-md/init', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({action: 'generate'}),
                    });
                    const data = await resp.json();
                    if (data.status === 'ok' && data.action === 'generated') {
                        statusEl.className = 'agents-modal-status success';
                        statusEl.textContent = `已写入: ${data.relative_path}`;
                        this.showToast(`AGENTS.md 已生成: ${data.relative_path}`, 'success');
                        setTimeout(() => { modal.style.display = 'none'; }, 800);
                    } else if (data.status === 'cancelled') {
                        statusEl.className = 'agents-modal-status';
                        statusEl.textContent = '已取消';
                        setBusy(false);
                    } else {
                        statusEl.className = 'agents-modal-status error';
                        statusEl.textContent = data.error || '生成失败';
                        setBusy(false);
                    }
                } catch (err) {
                    statusEl.className = 'agents-modal-status error';
                    statusEl.textContent = '网络错误';
                    setBusy(false);
                }
            } else if (action === 'skip') {
                modal.style.display = 'none';
                this.showToast('本次跳过 AGENTS.md 初始化', 'success');
            } else if (action === 'never') {
                try {
                    const resp = await fetch('/api/agents-md/init', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({action: 'never'}),
                    });
                    const data = await resp.json();
                    if (data.status === 'ok') {
                        modal.style.display = 'none';
                        this.showToast('已记住「永不为此目录生成」', 'success');
                    } else {
                        statusEl.className = 'agents-modal-status error';
                        statusEl.textContent = data.error || '写入标记失败';
                    }
                } catch {
                    statusEl.className = 'agents-modal-status error';
                    statusEl.textContent = '网络错误';
                }
            }
        };

        const optionListener = (e) => {
            const el = e.currentTarget;
            const action = el.dataset.action;
            if (action) handleAction(action);
        };
        options.forEach(o => {
            o.replaceWith(o.cloneNode(true));
        });
        modal.querySelectorAll('.agents-option').forEach(o => {
            o.addEventListener('click', optionListener);
        });

        const cancelHandler = async () => {
            try { await fetch('/api/agents-md/cancel', { method: 'POST' }); } catch {}
            statusEl.textContent = '正在取消...';
        };
        cancelBtn.replaceWith(cancelBtn.cloneNode(true));
        const freshCancelBtn = document.getElementById('agentsInitCancel');
        freshCancelBtn.addEventListener('click', cancelHandler);
    }

    // Returns Promise<'cancel' | 'proceed'> — proceed means: continue with newChat.
    showAgentsSummaryModal() {
        return new Promise((resolve) => {
            const modal = document.getElementById('agentsSummaryModal');
            const statusEl = document.getElementById('agentsSummaryStatus');
            const previewEl = document.getElementById('agentsSummaryPreview');
            const constraintsList = document.getElementById('agentsSummaryConstraintsList');
            const pitfallsList = document.getElementById('agentsSummaryPitfallsList');
            const constraintsCount = document.getElementById('agentsSummaryConstraintsCount');
            const pitfallsCount = document.getElementById('agentsSummaryPitfallsCount');
            const diffEl = document.getElementById('agentsSummaryDiff');
            const cancelBtn = document.getElementById('agentsSummaryCancel');
            const skipBtn = document.getElementById('agentsSummarySkip');
            const analyzeBtn = document.getElementById('agentsSummaryAnalyze');
            const writeBtn = document.getElementById('agentsSummaryWrite');

            if (!modal) { resolve('proceed'); return; }

            let pendingContent = null;

            const reset = () => {
                statusEl.className = 'agents-summary-status';
                statusEl.textContent = '点击「分析对话」开始';
                previewEl.style.display = 'none';
                constraintsList.innerHTML = '';
                pitfallsList.innerHTML = '';
                constraintsCount.textContent = '0';
                pitfallsCount.textContent = '0';
                diffEl.textContent = '';
                analyzeBtn.style.display = '';
                writeBtn.style.display = 'none';
                cancelBtn.style.display = 'none';
                pendingContent = null;
            };

            const close = (verdict) => {
                modal.style.display = 'none';
                resolve(verdict);
            };

            reset();
            modal.style.display = 'flex';

            // Use cloneNode to drop previous listeners (modal is reused across opens)
            const replaceBtn = (id) => {
                const el = document.getElementById(id);
                const clone = el.cloneNode(true);
                el.parentNode.replaceChild(clone, el);
                return clone;
            };
            const cancelFresh = replaceBtn('agentsSummaryCancel');
            const skipFresh = replaceBtn('agentsSummarySkip');
            const analyzeFresh = replaceBtn('agentsSummaryAnalyze');
            const writeFresh = replaceBtn('agentsSummaryWrite');

            // Initially: cancel hidden, skip+analyze visible, write hidden
            cancelFresh.style.display = 'none';
            writeFresh.style.display = 'none';

            cancelFresh.addEventListener('click', async () => {
                try { await fetch('/api/agents-md/cancel', { method: 'POST' }); } catch {}
                statusEl.textContent = '正在取消...';
            });

            skipFresh.addEventListener('click', () => {
                close('proceed');  // skip = proceed without summarizing
            });

            analyzeFresh.addEventListener('click', async () => {
                statusEl.className = 'agents-summary-status';
                statusEl.textContent = '正在分析对话，提取教训中（5–15 秒）...';
                analyzeFresh.disabled = true;
                skipFresh.disabled = true;
                cancelFresh.style.display = 'inline-block';

                try {
                    const resp = await fetch('/api/agents-md/summarize-preview', { method: 'POST' });
                    const data = await resp.json();
                    if (data.status === 'cancelled') {
                        statusEl.textContent = '已取消';
                        analyzeFresh.disabled = false;
                        skipFresh.disabled = false;
                        cancelFresh.style.display = 'none';
                        return;
                    }
                    if (data.status !== 'ok') {
                        statusEl.className = 'agents-summary-status error';
                        statusEl.textContent = data.error || '分析失败';
                        analyzeFresh.disabled = false;
                        skipFresh.disabled = false;
                        cancelFresh.style.display = 'none';
                        return;
                    }

                    cancelFresh.style.display = 'none';

                    if (data.no_changes) {
                        statusEl.className = 'agents-summary-status success';
                        statusEl.textContent = '没有发现需要新增的教训或约束 — AGENTS.md 保持不变';
                        analyzeFresh.style.display = 'none';
                        skipFresh.textContent = '完成';
                        skipFresh.disabled = false;
                        return;
                    }

                    // Populate preview
                    const escape = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    constraintsList.innerHTML = (data.new_constraints || [])
                        .map(c => `<li>${escape(c)}</li>`).join('');
                    pitfallsList.innerHTML = (data.new_pitfalls || [])
                        .map(p => `<li>${escape(p)}</li>`).join('');
                    constraintsCount.textContent = (data.new_constraints || []).length;
                    pitfallsCount.textContent = (data.new_pitfalls || []).length;
                    diffEl.textContent = data.diff || '(无 diff)';
                    pendingContent = data.new_content;
                    previewEl.style.display = 'block';

                    statusEl.className = 'agents-summary-status';
                    statusEl.textContent = `准备写入 ${data.relative_path}`;
                    analyzeFresh.style.display = 'none';
                    writeFresh.style.display = 'inline-block';
                    skipFresh.textContent = '放弃改动';
                    skipFresh.disabled = false;
                } catch (err) {
                    statusEl.className = 'agents-summary-status error';
                    statusEl.textContent = '网络错误';
                    analyzeFresh.disabled = false;
                    skipFresh.disabled = false;
                    cancelFresh.style.display = 'none';
                }
            });

            writeFresh.addEventListener('click', async () => {
                if (!pendingContent) return;
                writeFresh.disabled = true;
                skipFresh.disabled = true;
                statusEl.className = 'agents-summary-status';
                statusEl.textContent = '正在写入...';
                try {
                    const resp = await fetch('/api/agents-md/summarize-write', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({content: pendingContent}),
                    });
                    const data = await resp.json();
                    if (data.status === 'ok') {
                        statusEl.className = 'agents-summary-status success';
                        statusEl.textContent = `已写入 ${data.relative_path}`;
                        this.showToast(`AGENTS.md 已更新: ${data.relative_path}`, 'success');
                        setTimeout(() => close('proceed'), 600);
                    } else {
                        statusEl.className = 'agents-summary-status error';
                        statusEl.textContent = data.error || '写入失败';
                        writeFresh.disabled = false;
                        skipFresh.disabled = false;
                    }
                } catch {
                    statusEl.className = 'agents-summary-status error';
                    statusEl.textContent = '网络错误';
                    writeFresh.disabled = false;
                    skipFresh.disabled = false;
                }
            });
        });
    }

    // ── Command Palette (D2) ──────────────────────────────────────
    paletteStaticCommands() {
        return [
            { id: 'new', label: '新建对话', icon: '✦', group: '命令', shortcut: '⌘N', run: () => this.newChat() },
            { id: 'compact', label: '压缩上下文', icon: '⊘', group: '命令', run: () => this.doCompact() },
            { id: 'handoff', label: '生成 Handoff', icon: '⇥', group: '命令', run: () => this.doHandoff() },
            { id: 'fork', label: 'Fork 会话', icon: '⎇', group: '命令', run: () => this.showForkModal() },
            { id: 'export', label: '导出为 Markdown', icon: '📤', group: '命令', run: () => this.exportMarkdown() },
            { id: 'clear', label: '清屏', icon: '✕', group: '命令', shortcut: '⌘L', run: () => this.clearView() },
            { id: 'theme', label: '切换主题', icon: '☾', group: '命令', run: () => this.toggleTheme() },
            { id: 'files', label: '打开 Files', icon: '◫', group: '命令', run: () => this.openPanel('files') },
            { id: 'skills', label: '打开 Skills', icon: '◬', group: '命令', run: () => this.openPanel('skills') },
            { id: 'tools', label: '打开 Tools', icon: '◭', group: '命令', run: () => this.openPanel('tools') },
            { id: 'mcp', label: '打开 MCP', icon: '⬡', group: '命令', run: () => this.openPanel('mcp') },
            { id: 'config', label: '打开 Configuration', icon: '◮', group: '命令', run: () => this.openPanel('config') },
            { id: 'help', label: '快捷键帮助', icon: '?', group: '命令', shortcut: '⌘/', run: () => this.openHelp() },
        ];
    }

    async paletteLoadDynamic() {
        const now = Date.now();
        if (now - this._paletteCache.ts < 30000 && this._paletteCache.items.length) return this._paletteCache.items;
        const fetchJson = (url) => fetch(url).then(r => r.ok ? r.json() : null).catch(() => null);
        const [sessions, files, skills, tools, models] = await Promise.all([
            fetchJson('/api/sessions'),
            fetchJson('/api/files'),
            fetchJson('/api/skills'),
            fetchJson('/api/tools'),
            fetchJson('/api/models'),
        ]);
        const items = [];
        (sessions?.sessions || []).slice(0, 50).forEach(s => items.push({
            id: `session:${s.path}`,
            label: s.name,
            meta: `${s.entries || 0} 条 · ${s.mtime ? new Date(s.mtime * 1000).toLocaleDateString() : ''}`,
            icon: '§', group: '会话', run: () => this.loadSession(s.path),
        }));
        (files?.files || []).slice(0, 50).forEach(f => items.push({
            id: `file:${f.filename}`, label: f.filename,
            meta: f.size ? `${Math.round(f.size/1024)} KB` : '',
            icon: '◫', group: '文件', run: () => this.openPanel('files'),
        }));
        (skills?.skills || []).forEach(s => items.push({
            id: `skill:${s.name || s}`, label: s.name || s, icon: '◬', group: '技能',
            run: () => this.openPanel('skills'),
        }));
        (tools?.tools || []).forEach(t => items.push({
            id: `tool:${t.name || t}`, label: t.name || t, icon: '◭', group: '工具',
            run: () => this.openPanel('tools'),
        }));
        (models?.models || []).slice(0, 30).forEach(m => {
            const id = m.id || m;
            items.push({
                id: `model:${id}`, label: id, icon: '⬢', group: '模型',
                run: () => this.selectModel(id),
            });
        });
        this._paletteCache = { ts: now, items };
        return items;
    }

    async openPalette() {
        if (!this.paletteOverlay) return;
        this.paletteOverlay.classList.add('active');
        this.paletteInput.value = '';
        this.paletteInput.focus();
        this._paletteSelected = 0;
        // Render static + cached immediately, then refresh dynamic in background.
        this._paletteCurrentItems = this.paletteStaticCommands();
        this.renderPalette();
        const dynamic = await this.paletteLoadDynamic();
        this._paletteCurrentItems = this.paletteStaticCommands().concat(dynamic);
        this.renderPalette();
    }

    closePalette() {
        this.paletteOverlay?.classList.remove('active');
    }

    renderPalette() {
        if (!this.paletteList) return;
        const q = (this.paletteInput?.value || '').trim();
        let items = this._paletteCurrentItems;
        if (q) {
            const results = window.fuzzysort.go(q, items, { key: 'label', limit: 30, threshold: -10000 });
            items = results.map(r => r.obj);
        } else {
            // Empty query: recent 5 sessions + commands
            const cmds = items.filter(i => i.group === '命令');
            const sessions = items.filter(i => i.group === '会话').slice(0, 5);
            items = cmds.concat(sessions);
        }
        this._paletteFlat = items;
        if (this._paletteSelected >= items.length) this._paletteSelected = Math.max(0, items.length - 1);
        if (items.length === 0) {
            this.paletteList.innerHTML = '<div class="palette-empty">没有匹配项</div>';
            return;
        }
        const groups = {};
        items.forEach((it, i) => { (groups[it.group] = groups[it.group] || []).push({ it, i }); });
        const groupOrder = ['命令', '会话', '文件', '技能', '工具', '模型'];
        const groupNames = groupOrder.filter(g => groups[g]);
        this.paletteList.innerHTML = groupNames.map(g => `
            <div class="palette-group">
                <div class="palette-group-label">${g}</div>
                ${groups[g].map(({ it, i }) => `
                    <div class="palette-item" data-idx="${i}" aria-selected="${i === this._paletteSelected}">
                        <span class="palette-item-icon">${it.icon || '·'}</span>
                        <span class="palette-item-text">${this.escapeHtml(it.label)}</span>
                        ${it.meta ? `<span class="palette-item-meta">${this.escapeHtml(it.meta)}</span>` : ''}
                        ${it.shortcut ? `<span class="palette-item-shortcut">${it.shortcut}</span>` : ''}
                    </div>
                `).join('')}
            </div>
        `).join('');
        this.paletteList.querySelectorAll('.palette-item').forEach(el => {
            el.addEventListener('mouseenter', () => {
                this._paletteSelected = Number(el.dataset.idx);
                this.renderPalette();
            });
            el.addEventListener('click', () => this.executePaletteSelection());
        });
        // Scroll selected into view
        const sel = this.paletteList.querySelector(`[data-idx="${this._paletteSelected}"]`);
        sel?.scrollIntoView({ block: 'nearest' });
    }

    movePaletteSelection(delta) {
        const max = (this._paletteFlat?.length || 0) - 1;
        if (max < 0) return;
        this._paletteSelected = (this._paletteSelected + delta + max + 1) % (max + 1);
        this.renderPalette();
    }

    executePaletteSelection() {
        const item = this._paletteFlat?.[this._paletteSelected];
        if (!item) return;
        this.closePalette();
        try { item.run(); } catch (e) { console.error('palette run failed', e); }
    }

    // Palette-target helpers (will be expanded in later tasks)
    clearView() {
        // Visual-only clear; does NOT delete history.
        if (this.chatContainer) {
            this.chatContainer.querySelectorAll('.message').forEach(el => el.remove());
        }
    }
    openHelp() {
        // Real help modal wired in Task 21. For now, just toast.
        document.getElementById('helpModal')?.classList.add('active');
    }
    exportMarkdown() {
        // Real export route added in Task 24. For now, just open the URL — server returns 404 until then.
        window.open('/api/sessions/current/export.md', '_blank');
    }

    // ── D3: copy / resend / edit ───────────────────────────────────
    _refreshEditButtons() {
        // Hide all edit buttons; then reveal only the latest user message's.
        if (!this.chatContainer) return;
        this.chatContainer
            .querySelectorAll('.message-action-btn[data-action="edit"]')
            .forEach((b) => { b.hidden = true; });
        const userMsgs = this.chatContainer.querySelectorAll('.message.user');
        const last = userMsgs[userMsgs.length - 1];
        const editBtn = last?.querySelector('.message-action-btn[data-action="edit"]');
        if (editBtn) editBtn.hidden = false;
    }

    async copyMessage(messageDiv) {
        const raw = messageDiv.dataset.raw || '';
        try {
            await navigator.clipboard.writeText(raw);
            const btn = messageDiv.querySelector('.message-action-btn[data-action="copy"]');
            if (btn) {
                const orig = btn.textContent;
                btn.textContent = '✓';
                setTimeout(() => { btn.textContent = orig; }, 1500);
            }
        } catch (_) { /* clipboard denied; silent */ }
    }

    async resendMessage(messageDiv) {
        const id = messageDiv.dataset.messageId;
        const raw = messageDiv.dataset.raw || '';
        if (!id) {
            this.showToast('该消息没有 id，无法重发', 'error');
            return;
        }
        // Truncate everything from this user message onward by truncating
        // AFTER the previous message (so this user msg + everything after disappears).
        const allMessages = Array.from(this.chatContainer.querySelectorAll('.message'));
        const idx = allMessages.indexOf(messageDiv);
        const prev = idx > 0 ? allMessages[idx - 1] : null;
        const truncateAfter = prev?.dataset.messageId || null;

        try {
            if (truncateAfter) {
                const r = await fetch('/api/messages/truncate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ after_id: truncateAfter }),
                });
                if (!r.ok) { this.showToast('截断失败', 'error'); return; }
            } else {
                // No predecessor — clear all server history.
                await fetch('/api/history', { method: 'DELETE' });
            }
        } catch (e) {
            this.showToast('截断失败', 'error');
            return;
        }

        // Remove DOM messages from idx onward (including the user message we're resending).
        for (let i = idx; i < allMessages.length; i++) allMessages[i].remove();

        // Refill input with raw text and place cursor at the end.
        this.messageInput.value = raw;
        this.messageInput.dispatchEvent(new Event('input'));
        this.messageInput.focus();
        this.messageInput.selectionStart = this.messageInput.selectionEnd = raw.length;
        this._refreshEditButtons();
    }

    async editMessage(messageDiv) {
        // Spec treats Edit as Resend with cursor-at-end. The user can then modify
        // and press Enter to re-send.
        return this.resendMessage(messageDiv);
    }

    _jumpUserMessage(delta) {
        const userMsgs = Array.from(this.chatContainer.querySelectorAll('.message.user'));
        if (!userMsgs.length) return;
        // Find the user message currently nearest the top of the viewport.
        const curIdx = userMsgs.findIndex((el) => {
            const rect = el.getBoundingClientRect();
            return rect.top >= 80 && rect.top < window.innerHeight / 2;
        });
        const startIdx = curIdx >= 0 ? curIdx : (delta < 0 ? userMsgs.length : -1);
        const next = Math.max(0, Math.min(userMsgs.length - 1, startIdx + delta));
        userMsgs[next].scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

document.addEventListener('DOMContentLoaded', () => { new ChatApp(); });

