export const AI_ASSISTANT_CONFIG_KEYS = {
    apiKey: 'floating_ai_api_key',
    tavilyApiKey: 'floating_ai_tavily_api_key',
    model: 'floating_ai_model',
    chatModel: 'floating_ai_chat_model',
    reasonerModel: 'floating_ai_reasoner_model',
    baseUrl: 'floating_ai_base_url',
    systemPrompt: 'floating_ai_system_prompt'
};

const API_BASE_URL = process.env.REACT_APP_API_URL || '';
const AI_SESSION_TOKEN_KEY = 'aiSessionToken';
const CHAT_HISTORY_MAX_MESSAGES = 240;
const CHAT_HISTORY_MAX_CONTENT_LENGTH = 12000;

export const DEFAULT_AI_ASSISTANT_CONFIG = {
    apiKey: '',
    tavilyApiKey: '',
    model: 'deepseek-chat',
    chatModel: 'deepseek-chat',
    reasonerModel: 'deepseek-reasoner',
    baseUrl: 'https://api.deepseek.com',
    systemPrompt: '你是福州理工学院AI编程实践教学平台小助手。请使用简洁、准确、教学友好的中文回答，优先结合编程实践课程场景给出可执行建议。'
};

function normalizeAIConfig(config) {
    const source = config || {};
    const chatModel = String(source.chatModel || source.chat_model || source.model || DEFAULT_AI_ASSISTANT_CONFIG.chatModel).trim() || DEFAULT_AI_ASSISTANT_CONFIG.chatModel;
    const reasonerModel = String(source.reasonerModel || source.reasoner_model || DEFAULT_AI_ASSISTANT_CONFIG.reasonerModel).trim() || DEFAULT_AI_ASSISTANT_CONFIG.reasonerModel;
    const baseUrl = String(source.baseUrl || source.base_url || DEFAULT_AI_ASSISTANT_CONFIG.baseUrl).trim() || DEFAULT_AI_ASSISTANT_CONFIG.baseUrl;
    const systemPrompt = String(source.systemPrompt || source.system_prompt || DEFAULT_AI_ASSISTANT_CONFIG.systemPrompt).trim() || DEFAULT_AI_ASSISTANT_CONFIG.systemPrompt;
    const apiKey = String(source.apiKey || source.api_key || '').trim();
    const tavilyApiKey = String(source.tavilyApiKey || source.tavily_api_key || '').trim();
    return {
        apiKey,
        tavilyApiKey,
        model: chatModel,
        chatModel,
        reasonerModel,
        baseUrl,
        systemPrompt
    };
}

export function normalizeAIChatHistoryMessages(messages) {
    const output = [];
    const source = Array.isArray(messages) ? messages : [];
    source.forEach((raw) => {
        if (!raw || typeof raw !== 'object') return;
        const role = String(raw.role || '').trim().toLowerCase();
        if (!['system', 'user', 'assistant'].includes(role)) return;
        const content = String(raw.content || '').trim();
        if (!content) return;
        output.push({
            role,
            content: content.slice(0, CHAT_HISTORY_MAX_CONTENT_LENGTH)
        });
    });
    return output.slice(-CHAT_HISTORY_MAX_MESSAGES);
}

async function parseErrorResponse(response) {
    const raw = await response.text();
    if (!raw) {
        return `HTTP ${response.status}`;
    }
    try {
        const payload = JSON.parse(raw);
        return payload?.detail || payload?.message || raw;
    } catch {
        return raw;
    }
}

function readItem(key, fallback) {
    if (typeof window === 'undefined') {
        return fallback;
    }
    const value = localStorage.getItem(key);
    return value === null ? fallback : value;
}

function readAISessionToken() {
    if (typeof window === 'undefined') {
        return '';
    }
    return String(localStorage.getItem(AI_SESSION_TOKEN_KEY) || '').trim();
}

export function buildAIAuthHeaders(extraHeaders = {}) {
    const headers = { ...extraHeaders };
    const token = readAISessionToken();
    if (token) {
        headers['X-AI-Session-Token'] = token;
    }
    return headers;
}

export function readAIConfig() {
    const legacyModel = readItem(AI_ASSISTANT_CONFIG_KEYS.model, DEFAULT_AI_ASSISTANT_CONFIG.model);
    return normalizeAIConfig({
        apiKey: readItem(AI_ASSISTANT_CONFIG_KEYS.apiKey, DEFAULT_AI_ASSISTANT_CONFIG.apiKey),
        tavilyApiKey: readItem(AI_ASSISTANT_CONFIG_KEYS.tavilyApiKey, DEFAULT_AI_ASSISTANT_CONFIG.tavilyApiKey),
        model: legacyModel,
        chatModel: readItem(AI_ASSISTANT_CONFIG_KEYS.chatModel, legacyModel || DEFAULT_AI_ASSISTANT_CONFIG.chatModel),
        reasonerModel: readItem(AI_ASSISTANT_CONFIG_KEYS.reasonerModel, DEFAULT_AI_ASSISTANT_CONFIG.reasonerModel),
        baseUrl: readItem(AI_ASSISTANT_CONFIG_KEYS.baseUrl, DEFAULT_AI_ASSISTANT_CONFIG.baseUrl),
        systemPrompt: readItem(AI_ASSISTANT_CONFIG_KEYS.systemPrompt, DEFAULT_AI_ASSISTANT_CONFIG.systemPrompt)
    });
}

export function writeAIConfig(config) {
    if (typeof window === 'undefined') {
        return;
    }

    const chatModel = String(config.chatModel || config.model || DEFAULT_AI_ASSISTANT_CONFIG.chatModel).trim();
    const reasonerModel = String(config.reasonerModel || DEFAULT_AI_ASSISTANT_CONFIG.reasonerModel).trim();

    localStorage.setItem(AI_ASSISTANT_CONFIG_KEYS.apiKey, String(config.apiKey || '').trim());
    localStorage.setItem(AI_ASSISTANT_CONFIG_KEYS.tavilyApiKey, String(config.tavilyApiKey || '').trim());
    localStorage.setItem(AI_ASSISTANT_CONFIG_KEYS.model, chatModel);
    localStorage.setItem(AI_ASSISTANT_CONFIG_KEYS.chatModel, chatModel);
    localStorage.setItem(AI_ASSISTANT_CONFIG_KEYS.reasonerModel, reasonerModel);
    localStorage.setItem(AI_ASSISTANT_CONFIG_KEYS.baseUrl, String(config.baseUrl || '').trim());
    localStorage.setItem(AI_ASSISTANT_CONFIG_KEYS.systemPrompt, String(config.systemPrompt || '').trim());
    window.dispatchEvent(new Event('ai-config-updated'));
}

export async function loadAIConfigFromServer(username) {
    const user = String(username || '').trim();
    if (!user) {
        throw new Error('username 不能为空');
    }

    const response = await fetch(`${API_BASE_URL}/api/ai/config?username=${encodeURIComponent(user)}`, {
        headers: buildAIAuthHeaders()
    });
    if (!response.ok) {
        throw new Error(await parseErrorResponse(response));
    }

    const payload = await response.json();
    const normalized = normalizeAIConfig(payload?.config || payload || {});
    const local = readAIConfig();
    const merged = normalizeAIConfig({
        ...normalized,
        apiKey: normalized.apiKey || local.apiKey || '',
        tavilyApiKey: normalized.tavilyApiKey || local.tavilyApiKey || ''
    });
    writeAIConfig(merged);
    return merged;
}

export async function saveAIConfigToServer(teacherUsername, config) {
    const user = String(teacherUsername || '').trim();
    if (!user) {
        throw new Error('teacher_username 不能为空');
    }

    const normalized = normalizeAIConfig(config);
    const response = await fetch(`${API_BASE_URL}/api/ai/config`, {
        method: 'PUT',
        headers: buildAIAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
            teacher_username: user,
            api_key: normalized.apiKey,
            tavily_api_key: normalized.tavilyApiKey,
            chat_model: normalized.chatModel,
            reasoner_model: normalized.reasonerModel,
            base_url: normalized.baseUrl,
            system_prompt: normalized.systemPrompt
        })
    });

    if (!response.ok) {
        throw new Error(await parseErrorResponse(response));
    }

    const payload = await response.json();
    const responseConfig = normalizeAIConfig(payload?.config || payload || normalized);
    const merged = normalizeAIConfig({
        ...responseConfig,
        apiKey: normalized.apiKey || responseConfig.apiKey || '',
        tavilyApiKey: normalized.tavilyApiKey || responseConfig.tavilyApiKey || ''
    });
    writeAIConfig(merged);
    return merged;
}

export async function loadAIChatHistoryFromServer(username) {
    const user = String(username || '').trim();
    if (!user) {
        throw new Error('username 不能为空');
    }

    const response = await fetch(`${API_BASE_URL}/api/ai/chat-history?username=${encodeURIComponent(user)}`, {
        headers: buildAIAuthHeaders()
    });
    if (!response.ok) {
        throw new Error(await parseErrorResponse(response));
    }

    const payload = await response.json();
    return normalizeAIChatHistoryMessages(payload?.messages || []);
}

export async function saveAIChatHistoryToServer(username, messages) {
    const user = String(username || '').trim();
    if (!user) {
        throw new Error('username 不能为空');
    }

    const normalizedMessages = normalizeAIChatHistoryMessages(messages);
    const response = await fetch(`${API_BASE_URL}/api/ai/chat-history`, {
        method: 'PUT',
        headers: buildAIAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
            username: user,
            messages: normalizedMessages
        })
    });

    if (!response.ok) {
        throw new Error(await parseErrorResponse(response));
    }

    const payload = await response.json();
    return normalizeAIChatHistoryMessages(payload?.messages || normalizedMessages);
}
