import React, { useEffect, useMemo, useState } from 'react';
import './TeacherAIModule.css';
import {
    DEFAULT_AI_ASSISTANT_CONFIG,
    loadAIConfigFromServer,
    readAIConfig,
    saveAIConfigToServer,
    writeAIConfig
} from './aiAssistantConfig';

function TeacherAIModule({ username }) {
    const [formData, setFormData] = useState(() => readAIConfig());
    const [showApiKey, setShowApiKey] = useState(false);
    const [showTavilyKey, setShowTavilyKey] = useState(false);
    const [isTesting, setIsTesting] = useState(false);
    const [testMode, setTestMode] = useState('chat');
    const [saveNotice, setSaveNotice] = useState('');
    const [testNotice, setTestNotice] = useState({ type: '', text: '' });

    const normalizedBaseUrl = useMemo(() => {
        const trimmed = String(formData.baseUrl || '').trim();
        return (trimmed || DEFAULT_AI_ASSISTANT_CONFIG.baseUrl).replace(/\/+$/, '');
    }, [formData.baseUrl]);

    const onChangeField = (field) => (event) => {
        setFormData((prev) => ({ ...prev, [field]: event.target.value }));
        setSaveNotice('');
    };

    useEffect(() => {
        let cancelled = false;
        const syncSharedConfig = async () => {
            const normalizedUser = String(username || '').trim();
            if (!normalizedUser) return;
            try {
                const sharedConfig = await loadAIConfigFromServer(normalizedUser);
                if (!cancelled && sharedConfig) {
                    setFormData(sharedConfig);
                }
            } catch {
                // Keep local fallback when shared config is unavailable.
            }
        };

        syncSharedConfig();
        return () => {
            cancelled = true;
        };
    }, [username]);

    const saveConfig = async () => {
        const normalizedUser = String(username || '').trim();
        try {
            if (normalizedUser) {
                const savedConfig = await saveAIConfigToServer(normalizedUser, formData);
                setFormData(savedConfig);
            } else {
                writeAIConfig(formData);
            }
            setSaveNotice('配置已保存，学生端与教师端将使用同一份 AI 配置。');
            setTestNotice({ type: '', text: '' });
        } catch (error) {
            const message = error instanceof Error ? error.message : '保存失败';
            setSaveNotice(`保存失败：${message}`);
        }
    };

    const useDefaultPrompt = () => {
        setFormData((prev) => ({ ...prev, systemPrompt: DEFAULT_AI_ASSISTANT_CONFIG.systemPrompt }));
        setSaveNotice('');
    };

    const getTestingModel = () => {
        if (testMode === 'reasoner') {
            return String(formData.reasonerModel || '').trim() || DEFAULT_AI_ASSISTANT_CONFIG.reasonerModel;
        }
        return String(formData.chatModel || formData.model || '').trim() || DEFAULT_AI_ASSISTANT_CONFIG.chatModel;
    };

    const testConnection = async () => {
        if (!String(formData.apiKey || '').trim()) {
            setTestNotice({ type: 'error', text: '请先填写 API Key。' });
            return;
        }

        setIsTesting(true);
        setTestNotice({ type: '', text: '' });
        const start = Date.now();

        try {
            const model = getTestingModel();
            const response = await fetch(`${normalizedBaseUrl}/chat/completions`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${String(formData.apiKey || '').trim()}`
                },
                body: JSON.stringify({
                    model,
                    stream: false,
                    messages: [
                        {
                            role: 'system',
                            content: String(formData.systemPrompt || '').trim() || DEFAULT_AI_ASSISTANT_CONFIG.systemPrompt
                        },
                        {
                            role: 'user',
                            content: `请回复“连接测试成功”，并说明当前模型是 ${model}。`
                        }
                    ]
                })
            });

            const raw = await response.text();
            let data = null;
            try {
                data = raw ? JSON.parse(raw) : null;
            } catch {
                data = null;
            }

            if (!response.ok) {
                const detail = data?.error?.message || data?.message || raw || `HTTP ${response.status}`;
                throw new Error(detail);
            }

            const answer = data?.choices?.[0]?.message?.content?.trim() || '连接成功，模型可用。';
            const normalizedUser = String(username || '').trim();
            if (normalizedUser) {
                const savedConfig = await saveAIConfigToServer(normalizedUser, formData);
                setFormData(savedConfig);
            } else {
                writeAIConfig(formData);
            }

            setSaveNotice('连接测试成功，已同步保存共享配置。');
            setTestNotice({ type: 'success', text: `连接成功（${Date.now() - start}ms）：${answer}` });
        } catch (error) {
            const message = error instanceof Error ? error.message : '连接失败，请检查配置。';
            setTestNotice({ type: 'error', text: `连接失败：${message}` });
        } finally {
            setIsTesting(false);
        }
    };

    return (
        <div className="teacher-ai-module">
            <section className="teacher-ai-card">
                <h2>AI 功能模块</h2>
                <p>在教师端统一配置密钥、模型和系统设定，保存后学生端与教师端会使用同一份配置。</p>

                <div className="teacher-ai-form-grid">
                    <label htmlFor="teacher-ai-chat-model">普通模型（关闭深度思考）</label>
                    <input
                        id="teacher-ai-chat-model"
                        type="text"
                        value={formData.chatModel || ''}
                        onChange={onChangeField('chatModel')}
                        placeholder="deepseek-chat"
                    />

                    <label htmlFor="teacher-ai-reasoner-model">深度思考模型（开启深度思考）</label>
                    <input
                        id="teacher-ai-reasoner-model"
                        type="text"
                        value={formData.reasonerModel || ''}
                        onChange={onChangeField('reasonerModel')}
                        placeholder="deepseek-reasoner"
                    />

                    <label htmlFor="teacher-ai-key">API Key</label>
                    <div className="teacher-ai-key-row">
                        <input
                            id="teacher-ai-key"
                            type={showApiKey ? 'text' : 'password'}
                            value={formData.apiKey}
                            onChange={onChangeField('apiKey')}
                            placeholder="sk-..."
                        />
                        <button type="button" onClick={() => setShowApiKey((prev) => !prev)}>
                            {showApiKey ? '隐藏' : '显示'}
                        </button>
                    </div>

                    <label htmlFor="teacher-ai-tavily-key">Tavily API Key（联网搜索）</label>
                    <div className="teacher-ai-key-row">
                        <input
                            id="teacher-ai-tavily-key"
                            type={showTavilyKey ? 'text' : 'password'}
                            value={formData.tavilyApiKey || ''}
                            onChange={onChangeField('tavilyApiKey')}
                            placeholder="tvly-..."
                        />
                        <button type="button" onClick={() => setShowTavilyKey((prev) => !prev)}>
                            {showTavilyKey ? '隐藏' : '显示'}
                        </button>
                    </div>

                    <label htmlFor="teacher-ai-base-url">Base URL</label>
                    <input
                        id="teacher-ai-base-url"
                        type="text"
                        value={formData.baseUrl}
                        onChange={onChangeField('baseUrl')}
                        placeholder="https://api.deepseek.com"
                    />

                    <label htmlFor="teacher-ai-prompt">系统设定</label>
                    <textarea
                        id="teacher-ai-prompt"
                        rows={4}
                        value={formData.systemPrompt}
                        onChange={onChangeField('systemPrompt')}
                        placeholder="输入系统提示词"
                    />
                </div>

                <div className="teacher-ai-actions">
                    <button type="button" className="primary" onClick={saveConfig}>保存配置</button>

                    <div className="teacher-ai-test-inline">
                        <select value={testMode} onChange={(event) => setTestMode(event.target.value)}>
                            <option value="chat">测试普通模型</option>
                            <option value="reasoner">测试深度思考模型</option>
                        </select>
                        <button type="button" onClick={testConnection} disabled={isTesting}>
                            {isTesting ? '测试中...' : '测试连接'}
                        </button>
                    </div>

                    <button type="button" onClick={useDefaultPrompt}>恢复默认设定</button>
                </div>

                {saveNotice ? <p className="teacher-ai-notice success">{saveNotice}</p> : null}
                {testNotice.text ? <p className={`teacher-ai-notice ${testNotice.type}`}>{testNotice.text}</p> : null}
            </section>

            <section className="teacher-ai-card compact">
                <h3>配置说明</h3>
                <ul>
                    <li>推荐 Base URL：`https://api.deepseek.com`</li>
                    <li>兼容地址：`https://api.deepseek.com/v1`</li>
                    <li>普通模型默认 `deepseek-chat`，深度思考模型默认 `deepseek-reasoner`</li>
                    <li>悬浮助手会根据“深度思考”开关自动切换模型</li>
                    <li>联网搜索为实验功能，需要后端可以访问公网后才会返回实时结果</li>
                    <li>开启联网搜索后，如配置了 Tavily API Key，后端会优先使用 Tavily。</li>
                </ul>
            </section>
        </div>
    );
}

export default TeacherAIModule;
