import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import mammoth from 'mammoth';
import * as XLSX from 'xlsx';
import './FloatingAIAssistant.css';
import {
    buildAIAuthHeaders,
    DEFAULT_AI_ASSISTANT_CONFIG,
    loadAIChatHistoryFromServer,
    loadAIConfigFromServer,
    readAIConfig,
    saveAIChatHistoryToServer
} from './aiAssistantConfig';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

const POSITION_STORAGE_KEY = 'floating_ai_window_position';
const SIZE_STORAGE_KEY = 'floating_ai_window_size';
const TRIGGER_POSITION_STORAGE_KEY = 'floating_ai_trigger_position';
const DEEP_THINK_STORAGE_KEY = 'floating_ai_deep_thinking';
const WEB_SEARCH_STORAGE_KEY = 'floating_ai_web_search';
const CHAT_HISTORY_STORAGE_PREFIX = 'floating_ai_chat_history::';
const CHAT_HISTORY_MAX_MESSAGES = 240;
const CHAT_HISTORY_MAX_CONTENT_LENGTH = 12000;
const CHAT_CONTEXT_MAX_MESSAGES = 80;
const CHAT_CONTEXT_MAX_TOTAL_CHARS = 48000;

const WINDOW_EDGE_GAP = 12;
const WINDOW_DEFAULT_WIDTH = 420;
const WINDOW_DEFAULT_HEIGHT = 700;
const WINDOW_MIN_WIDTH = 340;
const WINDOW_MIN_HEIGHT = 440;

const MAX_ATTACHMENTS = 6;
const MAX_FILE_SIZE = 8 * 1024 * 1024;
const MAX_TEXT_LENGTH = 12000;
const SEARCH_RESULT_LIMIT = 4;
const DATE_TIME_QUERY_REGEX = /(what\s+date|what\s+time|current\s+date|current\s+time|today'?s\s+date|date\s+and\s+time|beijing\s+time|\u73b0\u5728\u51e0\u70b9|\u73b0\u5728\u51e0\u70b9\u4e86|\u4eca\u5929\u51e0\u53f7|\u4eca\u5929\u51e0\u6708\u51e0\u65e5|\u73b0\u5728\u65f6\u95f4|\u5317\u4eac\u65f6\u95f4|\u5f53\u524d\u65f6\u95f4|\u5f53\u524d\u65e5\u671f|\u65e5\u671f\u548c\u65f6\u95f4)/i;

const TEXT_FILE_EXTENSIONS = new Set([
    'txt', 'md', 'markdown', 'json', 'js', 'jsx', 'ts', 'tsx', 'py',
    'java', 'c', 'cpp', 'h', 'hpp', 'css', 'html', 'xml', 'yaml', 'yml',
    'sql', 'csv', 'tsv', 'log', 'ipynb'
]);

const QUICK_QUESTIONS = [
    '\u5e2e\u6211\u5236\u5b9a\u4e00\u4efd Python \u57fa\u7840\u5b9e\u9a8c\u5b66\u4e60\u8ba1\u5212',
    '\u8fd9\u4e2a\u62a5\u9519\u6211\u5e94\u8be5\u600e\u4e48\u6392\u67e5\uff1f',
    '\u89e3\u91ca\u4e00\u4e0b\u8fd9\u4e2a\u7b97\u6cd5\u7684\u65f6\u95f4\u590d\u6742\u5ea6',
    '\u7ed9\u6211\u4e00\u4e2a\u5b9e\u9a8c\u62a5\u544a\u603b\u7ed3\u6a21\u677f'
];

const WELCOME_MESSAGE = {
    role: 'assistant',
    content: '\u4f60\u597d\uff0c\u6211\u662f AI \u7f16\u7a0b\u5b9e\u8bad\u52a9\u624b\uff0c\u53ef\u4ee5\u76f4\u63a5\u63d0\u95ee\u6216\u4e0a\u4f20\u6587\u4ef6/\u56fe\u7247\u3002'
};

function normalizeLegacyAssistantWelcome(content) {
    const text = String(content || '').trim();
    if (!text) return text;

    const lower = text.toLowerCase();
    const isLegacyEnglishWelcome =
        lower.includes('ai coding practice assistant')
        || (lower.includes('ask questions') && lower.includes('upload') && lower.includes('images'));

    return isLegacyEnglishWelcome ? WELCOME_MESSAGE.content : text;
}

function getCurrentUsername() {
    if (typeof window === 'undefined') return '';
    return String(localStorage.getItem('username') || '').trim();
}

function normalizeUserRole(rawRole, username) {
    const role = String(rawRole || '').trim().toLowerCase();
    if (['teacher', 'student', 'admin'].includes(role)) return role;

    const user = String(username || '').trim().toLowerCase();
    if (!user) return 'student';
    if (user === 'admin' || user.startsWith('admin')) return 'admin';
    if (user.startsWith('teacher')) return 'teacher';
    return 'student';
}

function getCurrentUserProfile() {
    if (typeof window === 'undefined') {
        return {
            username: '',
            role: 'student',
            displayName: '',
            avatarUrl: '',
            avatarInitial: 'U',
            roleClass: 'role-student'
        };
    }

    const username = String(localStorage.getItem('username') || '').trim();
    const role = normalizeUserRole(localStorage.getItem('userRole'), username);
    const realName = String(localStorage.getItem('real_name') || '').trim();

    const avatarUrl = [
        'avatar_url',
        'avatarUrl',
        'avatar',
        'userAvatar',
        'profile_avatar',
        'profileAvatar'
    ]
        .map((key) => String(localStorage.getItem(key) || '').trim())
        .find(Boolean) || '';

    const displayName = realName || username || 'User';
    const firstChar = Array.from(displayName)[0] || Array.from(username)[0] || 'U';
    const avatarInitial = String(firstChar).toUpperCase();

    let roleClass = 'role-student';
    if (role === 'teacher') roleClass = 'role-teacher';
    if (role === 'admin') roleClass = 'role-admin';

    return {
        username,
        role,
        displayName,
        avatarUrl,
        avatarInitial,
        roleClass
    };
}

function getChatHistoryStorageKey(username) {
    const normalized = String(username || '').trim();
    return normalized ? `${CHAT_HISTORY_STORAGE_PREFIX}${normalized}` : '';
}

function normalizePersistedMessage(raw) {
    if (!raw || typeof raw !== 'object') return null;

    const role = String(raw.role || '').trim().toLowerCase();
    if (!['system', 'user', 'assistant'].includes(role)) return null;

    let content = String(raw.content || '').trim();
    if (!content) return null;
    if (role === 'assistant') {
        content = normalizeLegacyAssistantWelcome(content);
    }

    const payload = {
        role,
        content: content.slice(0, CHAT_HISTORY_MAX_CONTENT_LENGTH)
    };

    const apiContent = String(raw.apiContent || '').trim();
    if (apiContent) {
        payload.apiContent = apiContent.slice(0, CHAT_HISTORY_MAX_CONTENT_LENGTH);
    }

    if (role === 'user' && Array.isArray(raw.attachments)) {
        payload.attachments = raw.attachments
            .map((item) => {
                if (!item || typeof item !== 'object') return null;
                const name = String(item.name || '').trim();
                if (!name) return null;
                return {
                    id: String(item.id || `${Date.now()}-${Math.random()}`).slice(0, 120),
                    name: name.slice(0, 240),
                    kind: String(item.kind || '').slice(0, 40)
                };
            })
            .filter(Boolean)
            .slice(0, 6);
    }

    if (role === 'assistant') {
        payload.searchProvider = String(raw.searchProvider || '').slice(0, 80);
        payload.searchResolvedQuery = String(raw.searchResolvedQuery || '').slice(0, 240);
        if (Array.isArray(raw.searchResults)) {
            payload.searchResults = raw.searchResults
                .map((item) => {
                    if (!item || typeof item !== 'object') return null;
                    const url = String(item.url || '').trim();
                    if (!url) return null;
                    return {
                        title: String(item.title || '').slice(0, 240),
                        url: url.slice(0, 1000),
                        snippet: String(item.snippet || '').slice(0, 240)
                    };
                })
                .filter(Boolean)
                .slice(0, 8);
        }
    }

    return payload;
}

function loadChatHistoryByUser(username, welcomeMessage) {
    const storageKey = getChatHistoryStorageKey(username);
    if (!storageKey || typeof window === 'undefined') return [welcomeMessage];

    try {
        const raw = localStorage.getItem(storageKey);
        if (!raw) return [welcomeMessage];
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [welcomeMessage];
        const normalized = parsed
            .map(normalizePersistedMessage)
            .filter(Boolean)
            .slice(-CHAT_HISTORY_MAX_MESSAGES);
        return normalized.length > 0 ? normalized : [welcomeMessage];
    } catch {
        return [welcomeMessage];
    }
}

function saveChatHistoryByUser(username, messages) {
    const storageKey = getChatHistoryStorageKey(username);
    if (!storageKey || typeof window === 'undefined') return;

    try {
        const normalized = (Array.isArray(messages) ? messages : [])
            .map(normalizePersistedMessage)
            .filter(Boolean)
            .slice(-CHAT_HISTORY_MAX_MESSAGES);
        if (normalized.length === 0) {
            localStorage.removeItem(storageKey);
            return;
        }
        localStorage.setItem(storageKey, JSON.stringify(normalized));
    } catch {
        // Ignore quota / serialization errors.
    }
}

function buildServerHistoryMessages(messages) {
    return (Array.isArray(messages) ? messages : [])
        .map(normalizePersistedMessage)
        .filter(Boolean)
        .map((item) => ({
            role: item.role,
            content: String(item.content || '').slice(0, CHAT_HISTORY_MAX_CONTENT_LENGTH)
        }))
        .filter((item) => item.content)
        .slice(-CHAT_HISTORY_MAX_MESSAGES);
}

function buildContextHistoryForModel(messages) {
    const normalized = (Array.isArray(messages) ? messages : [])
        .map(normalizePersistedMessage)
        .filter(Boolean)
        .map((item) => ({
            role: item.role,
            content: String(item.apiContent || item.content || '').slice(0, CHAT_HISTORY_MAX_CONTENT_LENGTH)
        }))
        .filter((item) => item.content)
        .slice(-CHAT_CONTEXT_MAX_MESSAGES);
    let totalChars = 0;
    const selected = [];

    for (let index = normalized.length - 1; index >= 0; index -= 1) {
        const item = normalized[index];
        const content = String(item.content || '');
        const estimatedChars = content.length + 16;
        if (selected.length > 0 && (totalChars + estimatedChars > CHAT_CONTEXT_MAX_TOTAL_CHARS)) {
            break;
        }
        selected.push({ role: item.role, content });
        totalChars += estimatedChars;
    }

    if (selected.length === 0 && normalized.length > 0) {
        const lastItem = normalized[normalized.length - 1];
        selected.push({
            role: lastItem.role,
            content: String(lastItem.content || '').slice(0, CHAT_CONTEXT_MAX_TOTAL_CHARS)
        });
    }

    return selected.reverse();
}

function historyMessagesHash(messages) {
    try {
        return JSON.stringify(buildServerHistoryMessages(messages));
    } catch {
        return '';
    }
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function getTriggerSize() {
    if (typeof window === 'undefined') {
        return { width: 64, height: 64 };
    }
    if (window.innerWidth <= 768) {
        return { width: 56, height: 56 };
    }
    return { width: 64, height: 64 };
}

function getDefaultTriggerPosition() {
    const size = getTriggerSize();
    if (typeof window === 'undefined') {
        return { x: WINDOW_EDGE_GAP, y: WINDOW_EDGE_GAP };
    }
    return {
        x: Math.max(WINDOW_EDGE_GAP, window.innerWidth - size.width - 16),
        y: Math.max(WINDOW_EDGE_GAP, window.innerHeight - size.height - 20)
    };
}

function getFileExt(name) {
    const parts = String(name || '').toLowerCase().split('.');
    return parts.length > 1 ? parts.pop() : '';
}

function truncateText(text, maxLen = MAX_TEXT_LENGTH) {
    if (!text) return '';
    if (text.length <= maxLen) return text;
    return `${text.slice(0, maxLen)}\n\n[\u5185\u5bb9\u5df2\u622a\u65ad]`;
}

function formatFileSize(size) {
    const bytes = Number(size || 0);
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function cleanMarkdownDecorations(plainText) {
    return String(plainText || '')
        .replace(/^\s{0,3}#{1,6}\s+/gm, '')
        .replace(/\*\*(.*?)\*\*/g, '$1')
        .replace(/\r\n/g, '\n');
}

function removeIrrelevantSearchNotice(text) {
    let output = String(text || '');
    output = output.replace(/\[WEB_SEARCH_CONTEXT_START\][\s\S]*?\[WEB_SEARCH_CONTEXT_END\]/g, '\n');

    const noisyParagraphPatterns = [
        /(?:^|\n)\s*(?:About web search context|Web search note|Friendly note|\u5173\u4e8e\u8054\u7f51\u641c\u7d22\u4e0a\u4e0b\u6587|\u8054\u7f51\u641c\u7d22\u63d0\u793a|\u53cb\u597d\u63d0\u793a)\s*[:?]\s*[\s\S]*?(?=\n\s*\n|$)/g,
        /^\s*>\s*.*(?:system time|internal system time|datetime\.now|LocalDate\.now|\u7cfb\u7edf\u65f6\u95f4|\u5185\u90e8\u7cfb\u7edf\u65f6\u95f4).*$/gim
    ];
    noisyParagraphPatterns.forEach((pattern) => {
        output = output.replace(pattern, '\n');
    });

    return output.replace(/\n{3,}/g, '\n\n').trim();
}

function isDateTimeQuestion(text) {
    return DATE_TIME_QUERY_REGEX.test(String(text || '').trim());
}

function formatTimeDisplay(isoValue) {
    if (!isoValue) return '';
    const date = new Date(isoValue);
    if (Number.isNaN(date.getTime())) return '';
    const datePart = date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        weekday: 'long'
    });
    const timePart = date.toLocaleTimeString('zh-CN', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    return `${datePart} ${timePart}`;
}
function sanitizeAssistantText(content) {
    const source = String(content || '');
    const codeFencePattern = /```[\s\S]*?```/g;
    let result = '';
    let lastIndex = 0;
    let match;

    while ((match = codeFencePattern.exec(source)) !== null) {
        const start = match.index;
        if (start > lastIndex) {
            result += cleanMarkdownDecorations(source.slice(lastIndex, start));
        }
        result += match[0];
        lastIndex = start + match[0].length;
    }

    if (lastIndex < source.length) {
        result += cleanMarkdownDecorations(source.slice(lastIndex));
    }

    return removeIrrelevantSearchNotice(result);
}

function splitByCodeFence(text) {
    const source = String(text || '');
    const blocks = [];
    const pattern = /```([a-zA-Z0-9_-]+)?\n?([\s\S]*?)```/g;
    let lastIndex = 0;
    let match;

    while ((match = pattern.exec(source)) !== null) {
        const [full, lang, code] = match;
        const start = match.index;
        if (start > lastIndex) {
            blocks.push({ type: 'text', content: source.slice(lastIndex, start) });
        }
        blocks.push({ type: 'code', lang: lang || '', content: code || '' });
        lastIndex = start + full.length;
    }

    if (lastIndex < source.length) {
        blocks.push({ type: 'text', content: source.slice(lastIndex) });
    }

    if (blocks.length === 0) {
        blocks.push({ type: 'text', content: source });
    }

    return blocks;
}

function readFileAsText(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(new Error('\u8bfb\u53d6\u6587\u4ef6\u6587\u672c\u5931\u8d25'));
        reader.readAsText(file);
    });
}

function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(new Error('\u8bfb\u53d6\u56fe\u7247\u5931\u8d25'));
        reader.readAsDataURL(file);
    });
}

async function extractPdfText(file) {
    const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
    const buffer = await file.arrayBuffer();
    const loadingTask = pdfjs.getDocument({ data: new Uint8Array(buffer), disableWorker: true });
    const doc = await loadingTask.promise;
    const maxPages = Math.min(doc.numPages, 10);
    let output = '';

    for (let pageIndex = 1; pageIndex <= maxPages; pageIndex += 1) {
        const page = await doc.getPage(pageIndex);
        const textContent = await page.getTextContent();
        const pageText = (textContent.items || [])
            .map((item) => item.str || '')
            .join(' ')
            .replace(/\s+/g, ' ')
            .trim();
        if (pageText) {
            output += `[Page ${pageIndex}] ${pageText}\n`;
        }
        if (output.length >= MAX_TEXT_LENGTH) break;
    }

    if (!output.trim()) {
        return '\u672a\u63d0\u53d6\u5230\u53ef\u8bfb\u6587\u672c\uff08\u53ef\u80fd\u662f\u626b\u63cf\u7248 PDF\uff09\u3002';
    }
    return truncateText(output);
}

async function extractDocxText(file) {
    const buffer = await file.arrayBuffer();
    const result = await mammoth.extractRawText({ arrayBuffer: buffer });
    const text = (result.value || '').trim();
    return text ? truncateText(text) : '\u672a\u63d0\u53d6\u5230\u53ef\u8bfb\u6587\u672c\u3002';
}

async function extractExcelText(file) {
    const buffer = await file.arrayBuffer();
    const workbook = XLSX.read(buffer, { type: 'array' });
    const selectedSheets = workbook.SheetNames.slice(0, 3);
    let output = '';

    selectedSheets.forEach((sheetName) => {
        const sheet = workbook.Sheets[sheetName];
        const csv = XLSX.utils.sheet_to_csv(sheet, { blankrows: false }).trim();
        if (csv) {
            output += `[Sheet ${sheetName}]\n${csv}\n\n`;
        }
    });

    return output.trim() ? truncateText(output) : '\u672a\u63d0\u53d6\u5230\u53ef\u8bfb\u6570\u636e\u3002';
}

function createAttachmentId(file) {
    return `${file.name}-${file.size}-${file.lastModified}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

async function parseAttachment(file) {
    const base = {
        id: createAttachmentId(file),
        name: file.name,
        size: file.size,
        ext: getFileExt(file.name),
        kind: 'text',
        status: 'ready',
        extractedText: '',
        previewUrl: '',
        error: ''
    };

    if (file.size > MAX_FILE_SIZE) {
        return { ...base, kind: 'unsupported', status: 'error', error: `\u6587\u4ef6\u8fc7\u5927\uff0c\u6700\u5927\uff1a${formatFileSize(MAX_FILE_SIZE)}` };
    }

    const mime = String(file.type || '').toLowerCase();
    const ext = base.ext;

    try {
        if (mime.startsWith('image/')) {
            return { ...base, kind: 'image', previewUrl: await readFileAsDataUrl(file) };
        }

        if (ext === 'pdf') {
            return { ...base, kind: 'pdf', extractedText: await extractPdfText(file) };
        }

        if (ext === 'doc') {
            return { ...base, kind: 'unsupported', status: 'error', error: '\u4e0d\u652f\u6301 .doc\uff0c\u8bf7\u53e6\u5b58\u4e3a .docx \u540e\u91cd\u65b0\u4e0a\u4f20\u3002' };
        }

        if (ext === 'docx') {
            return { ...base, kind: 'docx', extractedText: await extractDocxText(file) };
        }

        if (ext === 'xlsx' || ext === 'xls') {
            return { ...base, kind: 'excel', extractedText: await extractExcelText(file) };
        }

        if (ext === 'csv' || ext === 'tsv') {
            return { ...base, kind: 'excel', extractedText: truncateText(await readFileAsText(file)) };
        }

        if (TEXT_FILE_EXTENSIONS.has(ext) || mime.startsWith('text/') || mime.includes('json') || mime.includes('xml')) {
            return { ...base, kind: 'text', extractedText: truncateText(await readFileAsText(file)) };
        }

        return { ...base, kind: 'unsupported', status: 'error', error: '\u4e0d\u652f\u6301\u7684\u683c\u5f0f\uff0c\u8bf7\u4f7f\u7528 txt/md/pdf/docx/xlsx/csv \u6216\u56fe\u7247\u3002' };
    } catch (error) {
        return { ...base, kind: 'unsupported', status: 'error', error: error instanceof Error ? error.message : '\u89e3\u6790\u5931\u8d25' };
    }
}

function kindLabel(kind) {
    switch (kind) {
    case 'image':
        return '\u56fe\u7247';
    case 'pdf':
        return 'PDF';
    case 'docx':
        return '\u6587\u6863';
    case 'excel':
        return 'Excel';
    case 'text':
        return '\u6587\u672c';
    default:
        return '\u9644\u4ef6';
    }
}

function buildAttachmentContext(attachment) {
    if (attachment.kind === 'image') {
        return `[\u56fe\u7247\u9644\u4ef6] ${attachment.name} (\u53ef\u9884\u89c8\uff0c\u5f53\u524d\u7248\u672c\u672a\u542f\u7528 OCR)`;
    }
    const text = String(attachment.extractedText || '').trim();
    return text ? `[\u9644\u4ef6\u5185\u5bb9 ${attachment.name}]\n${text}` : `[\u9644\u4ef6] ${attachment.name} (\u65e0\u53ef\u63d0\u53d6\u6587\u672c)`;
}

function renderMessageContent(content) {
    const blocks = splitByCodeFence(content);
    return blocks.map((block, index) => {
        if (block.type === 'code') {
            return (
                <div className="floating-ai-code-wrap" key={`code-${index}`}>
                    {block.lang ? <div className="floating-ai-code-lang">{block.lang}</div> : null}
                    <pre className="floating-ai-code-block"><code>{block.content}</code></pre>
                </div>
            );
        }

        const lines = String(block.content || '').split('\n');
        return (
            <p key={`text-${index}`} className="floating-ai-text-block">
                {lines.map((line, lineIndex) => (
                    <React.Fragment key={`${index}-${lineIndex}`}>
                        {line}
                        {lineIndex < lines.length - 1 ? <br /> : null}
                    </React.Fragment>
                ))}
            </p>
        );
    });
}

function FloatingAIAssistant() {
    const [isOpen, setIsOpen] = useState(false);
    const [draft, setDraft] = useState('');
    const [isSending, setIsSending] = useState(false);
    const [sendingProgress, setSendingProgress] = useState(0);
    const [sendingStage, setSendingStage] = useState('');
    const [isPreparingFiles, setIsPreparingFiles] = useState(false);
    const [isDragging, setIsDragging] = useState(false);
    const [isResizing, setIsResizing] = useState(false);
    const [isTriggerDragging, setIsTriggerDragging] = useState(false);
    const [errorMessage, setErrorMessage] = useState('');
    const [chatUsername, setChatUsername] = useState(() => getCurrentUsername());
    const [currentUserProfile, setCurrentUserProfile] = useState(() => getCurrentUserProfile());
    const [messages, setMessages] = useState(() => loadChatHistoryByUser(getCurrentUsername(), WELCOME_MESSAGE));
    const [attachments, setAttachments] = useState([]);
    const [previewImageUrl, setPreviewImageUrl] = useState('');
    const [aiConfig, setAiConfig] = useState(() => readAIConfig());
    const [deepThinking, setDeepThinking] = useState(() => localStorage.getItem(DEEP_THINK_STORAGE_KEY) === '1');
    const [webSearchEnabled, setWebSearchEnabled] = useState(() => localStorage.getItem(WEB_SEARCH_STORAGE_KEY) === '1');
    const [windowPosition, setWindowPosition] = useState(() => {
        try {
            const raw = localStorage.getItem(POSITION_STORAGE_KEY);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            if (!Number.isFinite(parsed?.x) || !Number.isFinite(parsed?.y)) return null;
            return { x: parsed.x, y: parsed.y };
        } catch {
            return null;
        }
    });
    const [windowSize, setWindowSize] = useState(() => {
        try {
            const raw = localStorage.getItem(SIZE_STORAGE_KEY);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            if (!Number.isFinite(parsed?.width) || !Number.isFinite(parsed?.height)) return null;
            return { width: parsed.width, height: parsed.height };
        } catch {
            return null;
        }
    });
    const [triggerPosition, setTriggerPosition] = useState(() => {
        try {
            const raw = localStorage.getItem(TRIGGER_POSITION_STORAGE_KEY);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            if (!Number.isFinite(parsed?.x) || !Number.isFinite(parsed?.y)) return null;
            return { x: parsed.x, y: parsed.y };
        } catch {
            return null;
        }
    });

    const messageEndRef = useRef(null);
    const fileInputRef = useRef(null);
    const dragStateRef = useRef(null);
    const resizeStateRef = useRef(null);
    const triggerDragStateRef = useRef(null);
    const triggerDragMovedRef = useRef(false);
    const sendingProgressTimerRef = useRef(null);
    const historySyncTimerRef = useRef(null);
    const historyLoadSeqRef = useRef(0);
    const lastSavedServerHistoryHashRef = useRef('');

    const { apiKey, model, chatModel, reasonerModel, baseUrl, systemPrompt } = aiConfig;

    const normalModel = useMemo(
        () => String(chatModel || model || DEFAULT_AI_ASSISTANT_CONFIG.chatModel).trim() || DEFAULT_AI_ASSISTANT_CONFIG.chatModel,
        [chatModel, model]
    );
    const deepModel = useMemo(
        () => String(reasonerModel || DEFAULT_AI_ASSISTANT_CONFIG.reasonerModel).trim() || DEFAULT_AI_ASSISTANT_CONFIG.reasonerModel,
        [reasonerModel]
    );
    const currentModel = deepThinking ? deepModel : normalModel;
    const readyAttachments = useMemo(() => attachments.filter((item) => item.status === 'ready'), [attachments]);

    const normalizedBaseUrl = useMemo(() => {
        const trimmed = String(baseUrl || '').trim();
        return (trimmed || DEFAULT_AI_ASSISTANT_CONFIG.baseUrl).replace(/\/+$/, '');
    }, [baseUrl]);

    const clampSize = useCallback((width, height) => {
        if (typeof window === 'undefined') return { width, height };
        const maxWidth = Math.max(WINDOW_MIN_WIDTH, window.innerWidth - WINDOW_EDGE_GAP * 2);
        const maxHeight = Math.max(WINDOW_MIN_HEIGHT, window.innerHeight - WINDOW_EDGE_GAP * 2);
        return {
            width: Math.round(clamp(width, WINDOW_MIN_WIDTH, maxWidth)),
            height: Math.round(clamp(height, WINDOW_MIN_HEIGHT, maxHeight))
        };
    }, []);

    const clampPosition = useCallback((x, y, widthOverride, heightOverride) => {
        if (typeof window === 'undefined') return { x, y };
        const width = widthOverride || windowSize?.width || WINDOW_DEFAULT_WIDTH;
        const height = heightOverride || windowSize?.height || WINDOW_DEFAULT_HEIGHT;
        const maxX = Math.max(WINDOW_EDGE_GAP, window.innerWidth - width - WINDOW_EDGE_GAP);
        const maxY = Math.max(WINDOW_EDGE_GAP, window.innerHeight - height - WINDOW_EDGE_GAP);
        return {
            x: Math.round(clamp(x, WINDOW_EDGE_GAP, maxX)),
            y: Math.round(clamp(y, WINDOW_EDGE_GAP, maxY))
        };
    }, [windowSize?.height, windowSize?.width]);

    const clampTriggerPosition = useCallback((x, y) => {
        if (typeof window === 'undefined') return { x, y };
        const triggerSize = getTriggerSize();
        const maxX = Math.max(WINDOW_EDGE_GAP, window.innerWidth - triggerSize.width - WINDOW_EDGE_GAP);
        const maxY = Math.max(WINDOW_EDGE_GAP, window.innerHeight - triggerSize.height - WINDOW_EDGE_GAP);
        return {
            x: Math.round(clamp(x, WINDOW_EDGE_GAP, maxX)),
            y: Math.round(clamp(y, WINDOW_EDGE_GAP, maxY))
        };
    }, []);

    const syncAiConfigFromServer = useCallback(async () => {
        const username = String(localStorage.getItem('username') || '').trim();
        if (!username) return;
        try {
            const remoteConfig = await loadAIConfigFromServer(username);
            if (remoteConfig) {
                setAiConfig(remoteConfig);
            }
        } catch {
            // Keep local fallback when shared config is unavailable.
        }
    }, []);

    const syncChatHistoryFromStorage = useCallback(() => {
        const username = getCurrentUsername();
        setChatUsername((prev) => (prev === username ? prev : username));
        setCurrentUserProfile(getCurrentUserProfile());
    }, []);

    useEffect(() => {
        const sync = () => setAiConfig(readAIConfig());
        window.addEventListener('storage', sync);
        window.addEventListener('ai-config-updated', sync);
        return () => {
            window.removeEventListener('storage', sync);
            window.removeEventListener('ai-config-updated', sync);
        };
    }, []);

    useEffect(() => {
        syncChatHistoryFromStorage();
        window.addEventListener('storage', syncChatHistoryFromStorage);
        window.addEventListener('focus', syncChatHistoryFromStorage);
        return () => {
            window.removeEventListener('storage', syncChatHistoryFromStorage);
            window.removeEventListener('focus', syncChatHistoryFromStorage);
        };
    }, [syncChatHistoryFromStorage]);

    useEffect(() => {
        if (!chatUsername) {
            setMessages([WELCOME_MESSAGE]);
            lastSavedServerHistoryHashRef.current = '';
            return undefined;
        }

        const loadSeq = historyLoadSeqRef.current + 1;
        historyLoadSeqRef.current = loadSeq;

        const localHistory = loadChatHistoryByUser(chatUsername, WELCOME_MESSAGE);
        setMessages(localHistory);
        lastSavedServerHistoryHashRef.current = historyMessagesHash(localHistory);

        let canceled = false;
        const syncFromServer = async () => {
            try {
                const remoteHistory = await loadAIChatHistoryFromServer(chatUsername);
                if (canceled || historyLoadSeqRef.current !== loadSeq) return;

                const normalizedRemoteHistory = (Array.isArray(remoteHistory) ? remoteHistory : [])
                    .map(normalizePersistedMessage)
                    .filter(Boolean);

                if (normalizedRemoteHistory.length > 0) {
                    const shouldUseRemote = normalizedRemoteHistory.length >= localHistory.length || localHistory.length <= 1;
                    if (shouldUseRemote) {
                        setMessages(normalizedRemoteHistory);
                        saveChatHistoryByUser(chatUsername, normalizedRemoteHistory);
                        lastSavedServerHistoryHashRef.current = historyMessagesHash(normalizedRemoteHistory);
                    } else {
                        const savedHistory = await saveAIChatHistoryToServer(chatUsername, localHistory);
                        if (canceled || historyLoadSeqRef.current !== loadSeq) return;
                        saveChatHistoryByUser(chatUsername, savedHistory);
                        lastSavedServerHistoryHashRef.current = historyMessagesHash(savedHistory);
                    }
                    return;
                }

                if (localHistory.length > 1) {
                    const savedHistory = await saveAIChatHistoryToServer(chatUsername, localHistory);
                    if (canceled || historyLoadSeqRef.current !== loadSeq) return;
                    saveChatHistoryByUser(chatUsername, savedHistory);
                    lastSavedServerHistoryHashRef.current = historyMessagesHash(savedHistory);
                }
            } catch {
                // Keep local fallback when remote chat history is unavailable.
            }
        };

        syncFromServer();
        return () => {
            canceled = true;
        };
    }, [chatUsername]);

    useEffect(() => {
        syncAiConfigFromServer();
    }, [syncAiConfigFromServer]);

    useEffect(() => {
        if (isOpen) {
            syncAiConfigFromServer();
        }
    }, [isOpen, syncAiConfigFromServer]);

    useEffect(() => { localStorage.setItem(DEEP_THINK_STORAGE_KEY, deepThinking ? '1' : '0'); }, [deepThinking]);
    useEffect(() => { localStorage.setItem(WEB_SEARCH_STORAGE_KEY, webSearchEnabled ? '1' : '0'); }, [webSearchEnabled]);
    useEffect(() => { if (windowPosition) localStorage.setItem(POSITION_STORAGE_KEY, JSON.stringify(windowPosition)); }, [windowPosition]);
    useEffect(() => { if (windowSize) localStorage.setItem(SIZE_STORAGE_KEY, JSON.stringify(windowSize)); }, [windowSize]);
    useEffect(() => {
        if (!triggerPosition) return;
        localStorage.setItem(TRIGGER_POSITION_STORAGE_KEY, JSON.stringify(triggerPosition));
    }, [triggerPosition]);
    useEffect(() => {
        if (!chatUsername) return;
        saveChatHistoryByUser(chatUsername, messages);

        const currentHash = historyMessagesHash(messages);
        if (currentHash === lastSavedServerHistoryHashRef.current) {
            return;
        }

        if (historySyncTimerRef.current) {
            clearTimeout(historySyncTimerRef.current);
        }

        historySyncTimerRef.current = setTimeout(async () => {
            try {
                await saveAIChatHistoryToServer(chatUsername, messages);
                lastSavedServerHistoryHashRef.current = currentHash;
            } catch {
                // Keep local fallback when remote chat history is unavailable.
            }
        }, 800);

        return () => {
            if (historySyncTimerRef.current) {
                clearTimeout(historySyncTimerRef.current);
                historySyncTimerRef.current = null;
            }
        };
    }, [chatUsername, messages]);

    useEffect(() => () => {
        if (historySyncTimerRef.current) {
            clearTimeout(historySyncTimerRef.current);
            historySyncTimerRef.current = null;
        }
    }, []);

    useEffect(() => {
        if (!isSending) {
            if (sendingProgressTimerRef.current) {
                clearInterval(sendingProgressTimerRef.current);
                sendingProgressTimerRef.current = null;
            }
            setSendingProgress(0);
            setSendingStage('');
            return undefined;
        }

        const startedAt = Date.now();
        const updateProgress = () => {
            const elapsedSeconds = (Date.now() - startedAt) / 1000;
            let nextProgress = 8;
            if (elapsedSeconds < 2) {
                nextProgress = 8 + elapsedSeconds * 10;
            } else if (elapsedSeconds < 8) {
                nextProgress = 28 + (elapsedSeconds - 2) * 7;
            } else {
                nextProgress = 70 + (elapsedSeconds - 8) * 2.5;
            }

            const clampedProgress = Math.min(92, Math.max(8, Math.round(nextProgress)));
            setSendingProgress((prev) => Math.max(prev, clampedProgress));

            if (elapsedSeconds < 2.5) {
                setSendingStage('\u6b63\u5728\u7406\u89e3\u95ee\u9898...');
            } else if (elapsedSeconds < 6) {
                setSendingStage('\u6b63\u5728\u68c0\u7d22\u4e0a\u4e0b\u6587...');
            } else if (elapsedSeconds < 12) {
                setSendingStage('\u6b63\u5728\u7ec4\u7ec7\u56de\u7b54...');
            } else {
                setSendingStage('\u6b63\u5728\u6da6\u8272\u8f93\u51fa...');
            }
        };

        updateProgress();
        sendingProgressTimerRef.current = setInterval(updateProgress, 220);
        return () => {
            if (sendingProgressTimerRef.current) {
                clearInterval(sendingProgressTimerRef.current);
                sendingProgressTimerRef.current = null;
            }
        };
    }, [isSending]);

    useEffect(() => {
        if (isOpen) {
            messageEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, isOpen, isSending]);

    useEffect(() => {
        if (isOpen) {
            setIsTriggerDragging(false);
            triggerDragStateRef.current = null;
            triggerDragMovedRef.current = false;
        }
        if (!isOpen) {
            setIsDragging(false);
            setIsResizing(false);
            dragStateRef.current = null;
            resizeStateRef.current = null;
            return;
        }

        const initialSize = windowSize || clampSize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT);
        const initialPos = windowPosition
            ? clampPosition(windowPosition.x, windowPosition.y, initialSize.width, initialSize.height)
            : clampPosition(
                window.innerWidth - initialSize.width - WINDOW_EDGE_GAP,
                window.innerHeight - initialSize.height - WINDOW_EDGE_GAP,
                initialSize.width,
                initialSize.height
            );
        setWindowSize(initialSize);
            setWindowPosition(initialPos);
    }, [isOpen, windowPosition, windowSize, clampPosition, clampSize]);

    useEffect(() => {
        const onViewportResize = () => {
            setWindowSize((prev) => {
                if (!prev) return prev;
                const size = clampSize(prev.width, prev.height);
                setWindowPosition((oldPos) => {
                    if (!oldPos) return oldPos;
                    return clampPosition(oldPos.x, oldPos.y, size.width, size.height);
                });
                return size;
            });
            setTriggerPosition((prev) => {
                const base = prev || getDefaultTriggerPosition();
                return clampTriggerPosition(base.x, base.y);
            });
        };

        window.addEventListener('resize', onViewportResize);
        return () => window.removeEventListener('resize', onViewportResize);
    }, [clampSize, clampPosition, clampTriggerPosition]);

    useEffect(() => {
        if (!isDragging) return undefined;

        const handlePointerMove = (event) => {
            if (!dragStateRef.current) return;
            event.preventDefault();
            const x = event.clientX - dragStateRef.current.offsetX;
            const y = event.clientY - dragStateRef.current.offsetY;
            setWindowPosition(clampPosition(x, y));
        };

        const handlePointerUp = () => {
            dragStateRef.current = null;
            setIsDragging(false);
        };

        window.addEventListener('pointermove', handlePointerMove);
        window.addEventListener('pointerup', handlePointerUp);
        window.addEventListener('pointercancel', handlePointerUp);
        return () => {
            window.removeEventListener('pointermove', handlePointerMove);
            window.removeEventListener('pointerup', handlePointerUp);
            window.removeEventListener('pointercancel', handlePointerUp);
        };
    }, [isDragging, clampPosition]);

    useEffect(() => {
        if (!isTriggerDragging) return undefined;

        const handlePointerMove = (event) => {
            const state = triggerDragStateRef.current;
            if (!state) return;
            event.preventDefault();

            const movedDistance = Math.max(
                Math.abs(event.clientX - state.startX),
                Math.abs(event.clientY - state.startY)
            );
            if (movedDistance > 4) {
                triggerDragMovedRef.current = true;
            }

            const x = event.clientX - state.offsetX;
            const y = event.clientY - state.offsetY;
            setTriggerPosition(clampTriggerPosition(x, y));
        };

        const handlePointerUp = () => {
            triggerDragStateRef.current = null;
            setIsTriggerDragging(false);
        };

        window.addEventListener('pointermove', handlePointerMove);
        window.addEventListener('pointerup', handlePointerUp);
        window.addEventListener('pointercancel', handlePointerUp);
        return () => {
            window.removeEventListener('pointermove', handlePointerMove);
            window.removeEventListener('pointerup', handlePointerUp);
            window.removeEventListener('pointercancel', handlePointerUp);
        };
    }, [isTriggerDragging, clampTriggerPosition]);

    useEffect(() => {
        if (!isResizing) return undefined;

        const handlePointerMove = (event) => {
            const state = resizeStateRef.current;
            if (!state) return;
            event.preventDefault();

            const dx = event.clientX - state.startX;
            const dy = event.clientY - state.startY;

            let left = state.startLeft;
            let top = state.startTop;
            let right = state.startLeft + state.startWidth;
            let bottom = state.startTop + state.startHeight;

            if (state.direction.includes('e')) right += dx;
            if (state.direction.includes('w')) left += dx;
            if (state.direction.includes('s')) bottom += dy;
            if (state.direction.includes('n')) top += dy;

            const leftBound = WINDOW_EDGE_GAP;
            const topBound = WINDOW_EDGE_GAP;
            const rightBound = window.innerWidth - WINDOW_EDGE_GAP;
            const bottomBound = window.innerHeight - WINDOW_EDGE_GAP;

            if (state.direction.includes('w')) {
                left = clamp(left, leftBound, right - WINDOW_MIN_WIDTH);
            }
            if (state.direction.includes('e')) {
                right = clamp(right, left + WINDOW_MIN_WIDTH, rightBound);
            }
            if (state.direction.includes('n')) {
                top = clamp(top, topBound, bottom - WINDOW_MIN_HEIGHT);
            }
            if (state.direction.includes('s')) {
                bottom = clamp(bottom, top + WINDOW_MIN_HEIGHT, bottomBound);
            }

            let width = right - left;
            let height = bottom - top;
            const nextSize = clampSize(width, height);

            if (nextSize.width !== width) {
                if (state.direction.includes('w') && !state.direction.includes('e')) {
                    left = right - nextSize.width;
                } else {
                    right = left + nextSize.width;
                }
                width = nextSize.width;
            }

            if (nextSize.height !== height) {
                if (state.direction.includes('n') && !state.direction.includes('s')) {
                    top = bottom - nextSize.height;
                } else {
                    bottom = top + nextSize.height;
                }
                height = nextSize.height;
            }

            const nextPos = clampPosition(left, top, width, height);
            setWindowSize({ width, height });
            setWindowPosition(nextPos);
        };

        const handlePointerUp = () => {
            resizeStateRef.current = null;
            setIsResizing(false);
        };

        window.addEventListener('pointermove', handlePointerMove);
        window.addEventListener('pointerup', handlePointerUp);
        window.addEventListener('pointercancel', handlePointerUp);
        return () => {
            window.removeEventListener('pointermove', handlePointerMove);
            window.removeEventListener('pointerup', handlePointerUp);
            window.removeEventListener('pointercancel', handlePointerUp);
        };
    }, [isResizing, clampSize, clampPosition]);

    const handleDragStart = (event) => {
        if (event.button !== 0 || isResizing) return;
        if (event.target.closest('button, input, textarea, select, label')) return;
        const base = windowPosition || { x: WINDOW_EDGE_GAP, y: WINDOW_EDGE_GAP };
        dragStateRef.current = { offsetX: event.clientX - base.x, offsetY: event.clientY - base.y };
        setWindowPosition(base);
        setIsDragging(true);
        event.preventDefault();
    };

    const handleResizeStart = (direction, event) => {
        if (event.button !== 0 || isDragging) return;
        const baseSize = windowSize || { width: WINDOW_DEFAULT_WIDTH, height: WINDOW_DEFAULT_HEIGHT };
        const basePos = windowPosition || { x: WINDOW_EDGE_GAP, y: WINDOW_EDGE_GAP };
        resizeStateRef.current = {
            direction,
            startX: event.clientX,
            startY: event.clientY,
            startLeft: basePos.x,
            startTop: basePos.y,
            startWidth: baseSize.width,
            startHeight: baseSize.height
        };
        setWindowSize(baseSize);
        setWindowPosition(basePos);
        setIsResizing(true);
        event.preventDefault();
        event.stopPropagation();
    };

    const handleSelectFiles = async (event) => {
        const selected = Array.from(event.target.files || []);
        event.target.value = '';
        if (selected.length === 0) return;

        const remain = MAX_ATTACHMENTS - attachments.length;
        if (remain <= 0) {
            setErrorMessage(`\u6700\u591a\u53ef\u4e0a\u4f20 ${MAX_ATTACHMENTS} \u4e2a\u9644\u4ef6`);
            return;
        }

        setIsPreparingFiles(true);
        try {
            const parsed = await Promise.all(selected.slice(0, remain).map((file) => parseAttachment(file)));
            setAttachments((prev) => [...prev, ...parsed]);
            if (selected.length > remain) {
                setErrorMessage(`\u6700\u591a\u53ef\u4e0a\u4f20 ${MAX_ATTACHMENTS} \u4e2a\u9644\u4ef6\uff0c\u5df2\u5ffd\u7565\u591a\u4f59\u6587\u4ef6\u3002`);
            } else {
                setErrorMessage('');
            }
        } finally {
            setIsPreparingFiles(false);
        }
    };

    const removeAttachment = (id) => setAttachments((prev) => prev.filter((item) => item.id !== id));

    const handleTriggerPointerDown = (event) => {
        if (event.button !== 0) return;
        const base = triggerPosition || getDefaultTriggerPosition();
        const clampedBase = clampTriggerPosition(base.x, base.y);
        triggerDragMovedRef.current = false;
        triggerDragStateRef.current = {
            startX: event.clientX,
            startY: event.clientY,
            offsetX: event.clientX - clampedBase.x,
            offsetY: event.clientY - clampedBase.y
        };
        setTriggerPosition(clampedBase);
        setIsTriggerDragging(true);
        event.preventDefault();
    };

    const handleTriggerClick = () => {
        if (triggerDragMovedRef.current) {
            triggerDragMovedRef.current = false;
            return;
        }
        setIsOpen(true);
    };

    const fetchBackendAnswer = async ({ username, message, history, model, useWebSearch, autoWebSearch }) => {
        const response = await fetch(`${API_BASE_URL}/api/ai/chat-with-search`, {
            method: 'POST',
            headers: buildAIAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({
                username,
                message,
                history,
                model,
                use_web_search: Boolean(useWebSearch),
                auto_web_search: Boolean(useWebSearch && autoWebSearch),
                search_limit: SEARCH_RESULT_LIMIT
            })
        });

        const raw = await response.text();
        let payload = null;
        try {
            payload = raw ? JSON.parse(raw) : null;
        } catch {
            payload = null;
        }

        if (!response.ok) {
            const detail = payload?.detail || payload?.message || raw || `HTTP ${response.status}`;
            throw new Error(detail);
        }

        const answer = String(payload?.answer || '').trim();
        if (!answer) {
            throw new Error('\u540e\u7aef\u672a\u8fd4\u56de\u6709\u6548\u56de\u7b54');
        }

        const provider = String(payload?.search_provider || '').trim();
        const resolvedQuery = String(payload?.search_resolved_query || message || '').trim();
        const searchError = String(payload?.search_error || '').trim();
        const decisionNeedSearch = Boolean(payload?.search_decision?.need_web_search);
        const decisionReason = String(payload?.search_decision?.reason || '').trim();
        const resultsRaw = Array.isArray(payload?.search_results) ? payload.search_results.slice(0, SEARCH_RESULT_LIMIT) : [];
        const results = resultsRaw
            .map((item) => ({
                title: String(item?.title || '').trim(),
                url: String(item?.url || '').trim(),
                snippet: String(item?.snippet || '').trim()
            }))
            .filter((item) => item.url);

        return {
            answer,
            provider,
            resolvedQuery,
            searchError,
            decisionNeedSearch,
            decisionReason,
            results
        };
    };

    const fetchNetworkTime = async () => {
        const response = await fetch(`${API_BASE_URL}/api/ai/network-time`, {
            method: 'GET',
            headers: buildAIAuthHeaders()
        });
        const raw = await response.text();
        let payload = null;
        try {
            payload = raw ? JSON.parse(raw) : null;
        } catch {
            payload = null;
        }

        if (!response.ok) {
            const detail = payload?.detail || payload?.message || raw || `HTTP ${response.status}`;
            throw new Error(detail);
        }

        return payload || {};
    };

    const buildDateTimeAnswer = (timePayload, searchMeta) => {
        const networkIso = timePayload?.network_time?.local_iso || '';
        const systemIso = timePayload?.system_time?.local_iso || '';
        const finalIso = networkIso || systemIso;
        const formatted = formatTimeDisplay(finalIso) || finalIso || '\u672a\u77e5';

        const parts = [`\u5f53\u524d\u65f6\u95f4\uff1a${formatted}`];
        if (networkIso) {
            const source = String(timePayload?.network_time?.source || '').trim();
            parts.push(`\u8054\u7f51\u65f6\u95f4\u6765\u6e90\uff1a${source || 'HTTP Date Header'}`);
        } else {
            parts.push('\u8054\u7f51\u65f6\u95f4\u4e0d\u53ef\u7528\uff0c\u5df2\u56de\u9000\u5230\u670d\u52a1\u5668\u7cfb\u7edf\u65f6\u95f4\u3002');
        }

        const resultCount = Array.isArray(searchMeta?.results) ? searchMeta.results.length : 0;
        if (resultCount > 0) {
            parts.push('\u5df2\u6267\u884c\u8054\u7f51\u641c\u7d22\uff0c\u6765\u6e90\u94fe\u63a5\u89c1\u4e0b\u3002');
        }

        return parts.join('\n\n');
    };

    const sendMessage = async (presetQuestion) => {
        const text = String(presetQuestion ?? draft).trim();
        if (!text && readyAttachments.length === 0) return;
        if (isSending || isPreparingFiles) return;
        const hasLocalApiKey = Boolean(String(apiKey || '').trim());
        const username = String(chatUsername || getCurrentUsername() || '').trim();
        if (!hasLocalApiKey && !username) {
            setErrorMessage('\u672a\u8bc6\u522b\u5230\u5f53\u524d\u7528\u6237\uff0c\u65e0\u6cd5\u8c03\u7528\u540e\u7aef AI\u3002');
            return;
        }

        const displayText = text || '\u8bf7\u7ed3\u5408\u9644\u4ef6\u5185\u5bb9\u56de\u7b54\u3002';
        const attachmentContext = readyAttachments.slice(0, 3).map(buildAttachmentContext).join('\n\n');
        const dateTimeMode = webSearchEnabled && isDateTimeQuestion(displayText);
        const apiContent = [displayText, attachmentContext].filter(Boolean).join('\n\n');
        const userMessage = {
            role: 'user',
            content: displayText,
            apiContent,
            attachments: readyAttachments
        };

        const nextMessages = [...messages, userMessage];
        setMessages(nextMessages);
        setDraft('');
        setAttachments([]);
        setIsSending(true);
        setSendingProgress(8);
        setSendingStage('\u6b63\u5728\u7406\u89e3\u95ee\u9898...');

        try {
            const history = buildContextHistoryForModel(nextMessages);

            const promptParts = [String(systemPrompt || DEFAULT_AI_ASSISTANT_CONFIG.systemPrompt)];
            if (webSearchEnabled) {
                promptParts.push(
                    'If [WEB_SEARCH_CONTEXT_START]... [WEB_SEARCH_CONTEXT_END] appears, prioritize it in the answer. ' +
                    'Answer directly and do not add unrelated preface text or fabricate internal time.'
                );
            }
            if (webSearchEnabled) {
                promptParts.push('Return only the final answer body. Do not output internal notes or policy text.');
            }
            const finalPrompt = promptParts.join('\n');

            if (dateTimeMode) {
                try {
                    const timePayload = await fetchNetworkTime();
                    const deterministicAnswer = buildDateTimeAnswer(timePayload, { results: [] });
                    setMessages((prev) => [...prev, {
                        role: 'assistant',
                        content: deterministicAnswer,
                        searchResults: [],
                        searchProvider: '',
                        searchResolvedQuery: ''
                    }]);
                    setErrorMessage('');
                    return;
                } catch (timeError) {
                    const detail = timeError instanceof Error ? timeError.message : '\u8054\u7f51\u65f6\u95f4\u6821\u9a8c\u5931\u8d25';
                    setErrorMessage(`\u8054\u7f51\u65f6\u95f4\u6821\u9a8c\u5931\u8d25\uff0c\u5df2\u56de\u9000\u5230\u6a21\u578b\u56de\u7b54\uff1a${detail}`);
                }
            }

            const shouldTryBackend = Boolean(username) && !dateTimeMode && displayText.trim() && (webSearchEnabled || !hasLocalApiKey);
            if (shouldTryBackend) {
                try {
                    const backendHistory = history.slice(0, -1);
                    const backendPayload = await fetchBackendAnswer({
                        username,
                        message: displayText,
                        history: backendHistory,
                        model: currentModel,
                        useWebSearch: webSearchEnabled,
                        autoWebSearch: webSearchEnabled
                    });

                    setMessages((prev) => [...prev, {
                        role: 'assistant',
                        content: sanitizeAssistantText(backendPayload.answer),
                        searchResults: backendPayload.results,
                        searchProvider: backendPayload.provider,
                        searchResolvedQuery: backendPayload.resolvedQuery
                    }]);
                    if (backendPayload.searchError) {
                        setErrorMessage(`\u8054\u7f51\u641c\u7d22\u63d0\u793a\uff1a${backendPayload.searchError}`);
                    } else {
                        setErrorMessage('');
                    }
                    return;
                } catch (backendError) {
                    const detail = backendError instanceof Error ? backendError.message : '\u540e\u7aef AI \u8c03\u7528\u5931\u8d25';
                    if (!hasLocalApiKey) {
                        throw new Error(`\u540e\u7aef AI \u4e0d\u53ef\u7528\uff1a${detail}`);
                    }
                    if (webSearchEnabled) {
                        setErrorMessage(`\u8054\u7f51\u540e\u7aef\u4e0d\u53ef\u7528\uff0c\u5df2\u56de\u9000\u76f4\u8fde\u6a21\u5f0f\uff1a${detail}`);
                    } else {
                        setErrorMessage(`\u540e\u7aef\u4e0d\u53ef\u7528\uff0c\u5df2\u56de\u9000\u672c\u5730 API Key \u76f4\u8fde\u6a21\u5f0f\uff1a${detail}`);
                    }
                }
            }

            if (!hasLocalApiKey) {
                throw new Error('\u672a\u914d\u7f6e\u672c\u5730 API Key\uff0c\u4e14\u540e\u7aef AI \u4e0d\u53ef\u7528\u3002');
            }

            const response = await fetch(`${normalizedBaseUrl}/chat/completions`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${String(apiKey).trim()}`
                },
                body: JSON.stringify({
                    model: currentModel,
                    stream: false,
                    messages: [{ role: 'system', content: finalPrompt }, ...history]
                })
            });

            const raw = await response.text();
            let result = null;
            try {
                result = raw ? JSON.parse(raw) : null;
            } catch {
                result = null;
            }

            if (!response.ok) {
                const detail = result?.error?.message || result?.message || raw || `HTTP ${response.status}`;
                throw new Error(detail);
            }

            const answerRaw = result?.choices?.[0]?.message?.content?.trim();
            if (!answerRaw) {
                throw new Error('\u6a21\u578b\u672a\u8fd4\u56de\u6709\u6548\u5185\u5bb9');
            }

            setMessages((prev) => [...prev, {
                role: 'assistant',
                content: sanitizeAssistantText(answerRaw),
                searchResults: [],
                searchProvider: '',
                searchResolvedQuery: ''
            }]);
            setErrorMessage('');
        } catch (error) {
            const detail = error instanceof Error ? error.message : '\u8bf7\u6c42\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5';
            setErrorMessage(detail);
            setMessages((prev) => [...prev, { role: 'assistant', content: `\u62b1\u6b49\uff0c\u8bf7\u6c42\u5931\u8d25\uff1a${detail}` }]);
        } finally {
            setIsSending(false);
        }
    };

    const onInputKeyDown = (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    };

    const size = windowSize || { width: WINDOW_DEFAULT_WIDTH, height: WINDOW_DEFAULT_HEIGHT };
    const position = windowPosition || { x: WINDOW_EDGE_GAP, y: WINDOW_EDGE_GAP };
    const triggerPos = useMemo(() => {
        const base = triggerPosition || getDefaultTriggerPosition();
        return clampTriggerPosition(base.x, base.y);
    }, [triggerPosition, clampTriggerPosition]);

    const userAvatarClassName = `floating-ai-avatar user ${currentUserProfile.roleClass || 'role-student'}`;
    const userAvatarTitle = currentUserProfile.displayName || currentUserProfile.username || 'User';

    const renderAssistantAvatar = () => (
        <div className="floating-ai-avatar ai" aria-hidden="true">
            <img src="/fit-logo-from-user.jpg" alt="" />
        </div>
    );

    const renderUserAvatar = () => (
        <div className={userAvatarClassName} title={userAvatarTitle}>
            {currentUserProfile.avatarUrl ? (
                <img src={currentUserProfile.avatarUrl} alt={userAvatarTitle} />
            ) : (
                <span>{currentUserProfile.avatarInitial || 'U'}</span>
            )}
        </div>
    );

    return (
        <div className="floating-ai-shell">
            {!isOpen && (
                <button
                    className={`floating-ai-trigger ${isTriggerDragging ? 'dragging' : ''}`}
                    type="button"
                    style={{ left: `${triggerPos.x}px`, top: `${triggerPos.y}px` }}
                    onPointerDown={handleTriggerPointerDown}
                    onClick={handleTriggerClick}
                    aria-label={'\u6253\u5f00 AI \u52a9\u624b'}
                >
                    <img src="/fit-logo-from-user.jpg" alt={'\u5b66\u9662 Logo'} />
                    <span>{'AI\u52a9\u624b'}</span>
                </button>
            )}

            {isOpen && (
                <section
                    className={`floating-ai-window ${isResizing ? 'resizing' : ''}`}
                    style={{
                        left: `${position.x}px`,
                        top: `${position.y}px`,
                        width: `${size.width}px`,
                        height: `${size.height}px`
                    }}
                    aria-label={'AI \u52a9\u624b\u7a97\u53e3'}
                >
                    <header className={`floating-ai-header ${isDragging ? 'dragging' : ''}`} onPointerDown={handleDragStart}>
                        <div className="floating-ai-title">
                            <img src="/fit-logo-from-user.jpg" alt={'\u5b66\u9662 Logo'} />
                            <div>
                                <strong>{'\u798f\u5dde\u7406\u5de5\u5b66\u9662AI\u52a9\u624b'}</strong>
                                <p>{'AI \u7f16\u7a0b\u5b9e\u8bad\u52a9\u624b'}</p>
                            </div>
                        </div>
                        <div className="floating-ai-actions">
                            <button type="button" onClick={() => setIsOpen(false)}>{'\u5173\u95ed'}</button>
                        </div>
                    </header>

                    <div className="floating-ai-hero">
                        <h3>{'\u4f60\u597d\uff0c\u6211\u662f\u4f60\u7684 AI \u52a9\u624b'}</h3>
                        <div className="floating-ai-quick-list">
                            {QUICK_QUESTIONS.map((question) => (
                                <button
                                    key={question}
                                    type="button"
                                    onClick={() => sendMessage(question)}
                                    disabled={isSending || isPreparingFiles}
                                >
                                    {question}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="floating-ai-messages">
                        {messages.map((message, index) => {
                            const isUser = message.role === 'user';
                            const isAssistant = message.role === 'assistant';

                            return (
                                <article key={`${message.role}-${index}`} className={`floating-ai-message ${message.role}`}>
                                    {!isUser ? renderAssistantAvatar() : null}

                                    <div className="floating-ai-bubble">
                                        {renderMessageContent(message.content)}
                                        {isUser && Array.isArray(message.attachments) && message.attachments.length > 0 ? (
                                            <div className="floating-ai-message-files">
                                                {message.attachments.map((item) => (
                                                    <span key={item.id}>
                                                        {item.kind === 'image' ? '\u56fe\u7247' : '\u9644\u4ef6'}: {item.name}
                                                    </span>
                                                ))}
                                            </div>
                                        ) : null}
                                        {isAssistant && Array.isArray(message.searchResults) && message.searchResults.length > 0 ? (
                                            <div className="floating-ai-search-sources">
                                                <div className="floating-ai-search-title">
                                                    {'\u8054\u7f51\u6765\u6e90'}
                                                    {message.searchProvider ? `(${message.searchProvider})` : ''}
                                                </div>
                                                {message.searchResolvedQuery ? (
                                                    <p className="floating-ai-search-query">{'\u68c0\u7d22\u8bcd\uff1a'}{message.searchResolvedQuery}</p>
                                                ) : null}
                                                <ul>
                                                    {message.searchResults.map((item, sourceIndex) => (
                                                        <li key={`${item.url}-${sourceIndex}`}>
                                                            <a href={item.url} target="_blank" rel="noreferrer">
                                                                {item.title || item.url}
                                                            </a>
                                                        </li>
                                                    ))}
                                                </ul>
                                            </div>
                                        ) : null}
                                    </div>

                                    {isUser ? renderUserAvatar() : null}
                                </article>
                            );
                        })}
                        {isSending && (
                            <article className="floating-ai-message assistant">
                                {renderAssistantAvatar()}
                                <div className="floating-ai-bubble floating-ai-loading-bubble">
                                    <p className="floating-ai-loading-title">{sendingStage || '\u6b63\u5728\u751f\u6210\u56de\u7b54...'}</p>
                                    <div
                                        className="floating-ai-loading-track"
                                        role="progressbar"
                                        aria-valuemin={0}
                                        aria-valuemax={100}
                                        aria-valuenow={Math.max(0, Math.min(100, sendingProgress))}
                                    >
                                        <div
                                            className="floating-ai-loading-fill"
                                            style={{ width: `${Math.max(6, Math.min(100, sendingProgress))}%` }}
                                        />
                                    </div>
                                    <p className="floating-ai-loading-meta">{`${Math.max(1, Math.min(100, sendingProgress))}%`}</p>
                                </div>
                            </article>
                        )}
                        <div ref={messageEndRef} />
                    </div>

                    <footer className="floating-ai-input-wrap">
                        {attachments.length > 0 ? (
                            <div className="floating-ai-upload-strip">
                                {attachments.map((item) => (
                                    <div
                                        key={item.id}
                                        className={`floating-ai-upload-chip ${item.kind} ${item.status === 'error' ? 'error' : ''}`}
                                    >
                                        <button
                                            type="button"
                                            className="floating-ai-upload-chip-remove"
                                            onClick={() => removeAttachment(item.id)}
                                            aria-label={'\u79fb\u9664\u9644\u4ef6'}
                                        >
                                            x
                                        </button>
                                        {item.kind === 'image' && item.previewUrl ? (
                                            <button
                                                type="button"
                                                className="floating-ai-upload-chip-thumb"
                                                onClick={() => setPreviewImageUrl(item.previewUrl)}
                                                title={'\u67e5\u770b\u5927\u56fe'}
                                            >
                                                <img src={item.previewUrl} alt={item.name} />
                                            </button>
                                        ) : (
                                            <div className="floating-ai-upload-chip-icon">{kindLabel(item.kind).slice(0, 3)}</div>
                                        )}
                                        <div className="floating-ai-upload-chip-text">
                                            <div className="floating-ai-upload-chip-name" title={item.name}>{item.name}</div>
                                            <div className="floating-ai-upload-chip-meta">
                                                {item.status === 'error' ? item.error : kindLabel(item.kind)}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : null}

                        <textarea
                            value={draft}
                            onChange={(event) => setDraft(event.target.value)}
                            onKeyDown={onInputKeyDown}
                            placeholder={'\u8bf7\u8f93\u5165\u4f60\u7684\u95ee\u9898\uff0cShift + Enter \u6362\u884c'}
                            rows={3}
                            disabled={isSending || isPreparingFiles}
                        />

                        <div className="floating-ai-toolbar-row">
                            <div className="floating-ai-toolbar-left">
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    multiple
                                    className="floating-ai-file-input"
                                    accept="image/*,.txt,.md,.markdown,.json,.js,.jsx,.ts,.tsx,.py,.java,.c,.cpp,.h,.hpp,.css,.html,.xml,.yaml,.yml,.sql,.csv,.log,.ipynb,.pdf,.doc,.docx,.xlsx,.xls"
                                    onChange={handleSelectFiles}
                                />
                                <button
                                    type="button"
                                    className="floating-ai-clip-btn"
                                    onClick={() => fileInputRef.current?.click()}
                                    disabled={isSending || isPreparingFiles}
                                    aria-label={isPreparingFiles ? '\u5904\u7406\u4e2d' : '\u4e0a\u4f20\u6587\u4ef6'}
                                    title={isPreparingFiles ? '\u5904\u7406\u4e2d...' : '\u4e0a\u4f20\u6587\u4ef6/\u56fe\u7247'}
                                >
                                    <svg viewBox="0 0 24 24" aria-hidden="true">
                                        <path d="M8 12.5L14.1 6.4a3.2 3.2 0 114.5 4.5l-7.8 7.8a5.1 5.1 0 11-7.2-7.2l8-8" />
                                    </svg>
                                </button>

                                <button
                                    type="button"
                                    className={`floating-ai-mode-btn ${deepThinking ? 'active' : ''}`}
                                    onClick={() => setDeepThinking((prev) => !prev)}
                                    disabled={isSending}
                                    aria-pressed={deepThinking}
                                >
                                    <svg viewBox="0 0 24 24" aria-hidden="true">
                                        <circle cx="12" cy="12" r="6.5" />
                                        <circle cx="12" cy="3.5" r="1.3" />
                                        <circle cx="12" cy="20.5" r="1.3" />
                                        <circle cx="3.5" cy="12" r="1.3" />
                                        <circle cx="20.5" cy="12" r="1.3" />
                                    </svg>
                                    <span className="floating-ai-mode-label">{'\u6df1\u5ea6\u601d\u8003'}</span>
                                    <span className="floating-ai-mode-state">{deepThinking ? '\u5f00' : '\u5173'}</span>
                                </button>

                                <button
                                    type="button"
                                    className={`floating-ai-mode-btn ${webSearchEnabled ? 'active' : ''}`}
                                    onClick={() => setWebSearchEnabled((prev) => !prev)}
                                    disabled={isSending}
                                    title={'\u9700\u8981\u540e\u7aef\u8054\u7f51\u6743\u9650\u4ee5\u6267\u884c\u5b9e\u65f6\u641c\u7d22'}
                                    aria-pressed={webSearchEnabled}
                                >
                                    <svg viewBox="0 0 24 24" aria-hidden="true">
                                        <circle cx="12" cy="12" r="8.5" />
                                        <path d="M3.8 12h16.4" />
                                        <path d="M12 3.8a13.2 13.2 0 010 16.4" />
                                        <path d="M12 3.8a13.2 13.2 0 000 16.4" />
                                    </svg>
                                    <span className="floating-ai-mode-label">{'\u8054\u7f51\u641c\u7d22'}</span>
                                    <span className="floating-ai-mode-state">{webSearchEnabled ? '\u5f00' : '\u5173'}</span>
                                </button>
                            </div>

                            <button
                                type="button"
                                className="floating-ai-send-btn"
                                onClick={() => sendMessage()}
                                disabled={isSending || isPreparingFiles || (!draft.trim() && readyAttachments.length === 0)}
                                aria-label={'\u53d1\u9001'}
                            >
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                    <path d="M12 4l-6 6h4v10h4V10h4z" />
                                </svg>
                            </button>
                        </div>

                        {errorMessage && <p className="floating-ai-error">{errorMessage}</p>}
                    </footer>

                    <div className="floating-ai-resize-handle n" onPointerDown={(event) => handleResizeStart('n', event)} />
                    <div className="floating-ai-resize-handle e" onPointerDown={(event) => handleResizeStart('e', event)} />
                    <div className="floating-ai-resize-handle s" onPointerDown={(event) => handleResizeStart('s', event)} />
                    <div className="floating-ai-resize-handle w" onPointerDown={(event) => handleResizeStart('w', event)} />
                    <div className="floating-ai-resize-handle ne" onPointerDown={(event) => handleResizeStart('ne', event)} />
                    <div className="floating-ai-resize-handle se" onPointerDown={(event) => handleResizeStart('se', event)} />
                    <div className="floating-ai-resize-handle sw" onPointerDown={(event) => handleResizeStart('sw', event)} />
                    <div className="floating-ai-resize-handle nw" onPointerDown={(event) => handleResizeStart('nw', event)} />
                </section>
            )}

            {previewImageUrl ? (
                <div className="floating-ai-image-preview-mask" onClick={() => setPreviewImageUrl('')}>
                    <div className="floating-ai-image-preview-dialog" onClick={(event) => event.stopPropagation()}>
                        <button type="button" onClick={() => setPreviewImageUrl('')}>{'\u5173\u95ed'}</button>
                        <img src={previewImageUrl} alt={'\u9644\u4ef6\u9884\u89c8'} />
                    </div>
                </div>
            ) : null}
        </div>
    );
}

export default FloatingAIAssistant;

