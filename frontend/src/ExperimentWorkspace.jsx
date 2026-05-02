import React, { useEffect, useRef, useState } from 'react';
import Split from 'react-split';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { getWorkspaceLaunchInfo } from './jupyterAuth';
import './ExperimentWorkspace.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

const JUPYTER_UI_PATCH_INTERVAL_MS = 800;
const JUPYTER_UI_PATCH_MAX_ATTEMPTS = 60;
const CODE_SERVER_LOAD_TIMEOUT_MS = 8000;
const JUPYTER_AI_AVATAR_URL = '/fit-logo-from-user.jpg';
const AVATAR_LOAD_STATUS_BY_URL = new Map();
const INVALID_AVATAR_TOKENS = new Set(['', 'null', 'undefined', 'none', 'nan', '-', '--', '[object object]']);
const WORKSPACE_LABELS = {
    lab: 'JupyterLab',
    notebook: 'Notebook',
    code: 'VS Code',
};

function getAbsoluteBrowserUrl(rawUrl) {
    let value = String(rawUrl ?? '').trim();
    if (!value) return '';

    // Handle accidentally stringified values like '"...url..."'.
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith('\'') && value.endsWith('\''))) {
        value = value.slice(1, -1).trim();
    }

    if (INVALID_AVATAR_TOKENS.has(value.toLowerCase())) return '';

    // Handle JSON payloads stored into localStorage by mistake.
    if ((value.startsWith('{') && value.endsWith('}')) || (value.startsWith('[') && value.endsWith(']'))) {
        try {
            const parsed = JSON.parse(value);
            if (typeof parsed === 'string') return getAbsoluteBrowserUrl(parsed);
            if (parsed && typeof parsed === 'object') {
                const nested = parsed.avatar_url || parsed.avatarUrl || parsed.avatar || parsed.url || parsed.src;
                return getAbsoluteBrowserUrl(nested);
            }
        } catch (error) {
            return '';
        }
        return '';
    }

    if (/\s/.test(value) && !value.startsWith('data:image/')) return '';
    if (value.startsWith('data:image/')) return value;
    if (value.startsWith('blob:')) return value;
    if (value.startsWith('//')) return `${window.location.protocol}${value}`;
    if (value.startsWith('http://') || value.startsWith('https://')) return value;
    if (value.startsWith('/')) return `${window.location.origin}${value}`;

    // Normalize project-relative paths like uploads/avatar.png or ./uploads/a.png.
    if (value.startsWith('./') || value.startsWith('../') || value.includes('/')) {
        try {
            return new URL(value, `${window.location.origin}/`).href;
        } catch (error) {
            return '';
        }
    }

    // Reject obvious non-URL placeholders to avoid blank avatars.
    if (!value.includes('.') || /[{}[\]<>]/.test(value)) return '';

    return '';
}

function readHomepageUserAvatarUrl() {
    if (typeof window === 'undefined') return '';
    const candidateKeys = ['avatar_url', 'avatarUrl', 'avatar', 'userAvatar', 'profile_avatar', 'profileAvatar'];
    for (const key of candidateKeys) {
        const value = getAbsoluteBrowserUrl(localStorage.getItem(key));
        if (value) return value;
    }
    return '';
}

function getAvatarLoadStatus(url) {
    if (!url) return 'error';
    const cached = AVATAR_LOAD_STATUS_BY_URL.get(url);
    if (cached) return cached;
    if (typeof Image === 'undefined') return 'loaded';

    AVATAR_LOAD_STATUS_BY_URL.set(url, 'loading');
    const img = new Image();
    img.onload = () => {
        AVATAR_LOAD_STATUS_BY_URL.set(url, 'loaded');
    };
    img.onerror = () => {
        AVATAR_LOAD_STATUS_BY_URL.set(url, 'error');
    };
    img.src = url;
    return 'loading';
}

function hasJupyterAiPanelContent(doc) {
    if (!doc) return false;
    return Boolean(
        doc.querySelector('.jp-ai-ChatSettings-header')
        || doc.querySelector('.jp-ai-ChatSettings-welcome')
        || doc.querySelector('.jp-ai-rendermime-markdown')
        || doc.querySelector('[data-id="jupyter-ai::chat"]')
        || doc.querySelector('#jupyter-ai\\:\\:chat')
    );
}

function isLikelyJupyterAiTab(node) {
    if (!node || typeof node.getAttribute !== 'function') return false;
    const dataId = String(node.getAttribute('data-id') || '').trim().toLowerCase();
    if (dataId === 'jupyter-ai::chat' || dataId === 'jupyter-ai::jupyternaut') return true;
    const label = [node.getAttribute('title'), node.getAttribute('aria-label'), node.id, node.textContent]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
    return label.includes('jupyter ai') || label.includes('jupyternaut');
}

function isTabActive(node) {
    const className = String(node?.className || '');
    return (
        className.includes('lm-mod-current')
        || className.includes('jp-mod-current')
        || className.includes('p-mod-current')
        || node?.getAttribute('aria-selected') === 'true'
    );
}

function tryOpenJupyterAiByDom(doc) {
    if (!doc) return false;
    const direct = doc.querySelector('[data-id="jupyter-ai::chat"], [data-id="jupyter-ai::jupyternaut"]');
    const candidates = direct
        ? [direct]
        : Array.from(doc.querySelectorAll('[role="tab"], .lm-TabBar-tab, .p-TabBar-tab, .jp-SideBar .jp-SideBar-tab'));
    const tab = candidates.find(isLikelyJupyterAiTab);
    if (!tab) return false;
    if (!isTabActive(tab)) {
        tab.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: doc.defaultView }));
    }
    return true;
}

function tryOpenJupyterAiByCommand(frameWindow) {
    if (!frameWindow) return false;

    const directCandidates = [
        frameWindow.jupyterapp,
        frameWindow.jupyterlab,
        frameWindow.__jupyterlab,
        frameWindow.app,
    ].filter(Boolean);

    const discoveredCandidates = [];
    try {
        for (const value of Object.values(frameWindow)) {
            if (!value || typeof value !== 'object') continue;
            const commands = value.commands;
            if (!commands || typeof commands.execute !== 'function') continue;
            discoveredCandidates.push(value);
            if (discoveredCandidates.length >= 6) break;
        }
    } catch (error) {
        // ignore cross-object enumeration issues
    }

    const candidates = [...new Set([...directCandidates, ...discoveredCandidates])];
    const commandIds = ['jupyter-ai::chat', 'jupyter-ai::jupyternaut', 'jupyter-ai:focus-chat-input'];

    for (const app of candidates) {
        const commands = app?.commands;
        if (!commands || typeof commands.execute !== 'function') continue;
        for (const commandId of commandIds) {
            try {
                if (typeof commands.hasCommand === 'function' && !commands.hasCommand(commandId)) continue;
                const result = commands.execute(commandId);
                if (result && typeof result.catch === 'function') result.catch(() => {});
                return true;
            } catch (error) {
                continue;
            }
        }
    }
    return false;
}

function tryFocusJupyterAiInput(frameWindow, doc) {
    try {
        const appCandidates = [frameWindow?.jupyterapp, frameWindow?.jupyterlab, frameWindow?.__jupyterlab, frameWindow?.app].filter(Boolean);
        for (const app of appCandidates) {
            const commands = app?.commands;
            if (!commands || typeof commands.execute !== 'function') continue;
            if (typeof commands.hasCommand === 'function' && !commands.hasCommand('jupyter-ai:focus-chat-input')) continue;
            const result = commands.execute('jupyter-ai:focus-chat-input');
            if (result && typeof result.catch === 'function') result.catch(() => {});
            return true;
        }
    } catch (error) {
        // ignore transient iframe readiness timing
    }
    const input = doc?.querySelector('textarea, input[type="text"]');
    if (input && typeof input.focus === 'function') {
        input.focus();
        return true;
    }
    return false;
}

function ensureJupyterAiChatStyles(doc) {
    if (!doc || !doc.head) return false;

    const styleId = 'fit-jupyter-ai-chat-theme';
    let styleNode = doc.getElementById(styleId);
    if (!styleNode) {
        styleNode = doc.createElement('style');
        styleNode.id = styleId;
        doc.head.appendChild(styleNode);
    }

    const css = `
#jupyter-ai\\:\\:chat .fit-jai-message {
  border-radius: 16px;
  margin: 6px 0;
}

#jupyter-ai\\:\\:chat .fit-jai-message > .MuiBox-root:first-child {
  margin-bottom: 8px;
}

#jupyter-ai\\:\\:chat .jp-ai-rendermime-markdown {
  border-radius: 14px;
  border: 1px solid rgba(25, 50, 90, 0.12);
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  box-shadow: 0 4px 14px rgba(17, 35, 67, 0.06);
  padding: 10px 12px;
}

#jupyter-ai\\:\\:chat .fit-jai-message.fit-jai-ai > .jp-ai-rendermime-markdown {
  background: linear-gradient(180deg, #fff8f8 0%, #fff2f3 100%);
  border-color: rgba(164, 37, 60, 0.18);
  box-shadow: 0 4px 14px rgba(164, 37, 60, 0.08);
}

#jupyter-ai\\:\\:chat .fit-jai-message.fit-jai-user > .jp-ai-rendermime-markdown {
  background: linear-gradient(180deg, #eef6ff 0%, #e7f2ff 100%);
  border-color: rgba(35, 94, 170, 0.22);
  box-shadow: 0 4px 14px rgba(35, 94, 170, 0.08);
}

#jupyter-ai\\:\\:chat .fit-jai-avatar {
  width: 28px !important;
  height: 28px !important;
  border-radius: 999px !important;
  overflow: hidden;
  background-color: #ffffff !important;
  border: 1.5px solid rgba(164, 37, 60, 0.22);
  box-shadow: 0 2px 6px rgba(17, 35, 67, 0.10);
}

#jupyter-ai\\:\\:chat .fit-jai-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

#jupyter-ai\\:\\:chat .fit-jai-avatar.fit-jai-avatar-ai {
  border-color: rgba(164, 37, 60, 0.28);
}

#jupyter-ai\\:\\:chat .fit-jai-avatar.fit-jai-avatar-user {
  border-color: rgba(35, 94, 170, 0.28);
}

#jupyter-ai\\:\\:chat .fit-jai-avatar.fit-jai-avatar-custom {
  background-position: center !important;
  background-size: cover !important;
  background-repeat: no-repeat !important;
}

#jupyter-ai\\:\\:chat .fit-jai-avatar.fit-jai-avatar-custom.fit-jai-avatar-loaded .MuiTypography-root {
  display: none !important;
}

#jupyter-ai\\:\\:chat .fit-jai-avatar.fit-jai-avatar-ai.fit-jai-avatar-loaded img {
  opacity: 0 !important;
}

#jupyter-ai\\:\\:chat .jp-ai-rendermime-markdown p:last-child,
#jupyter-ai\\:\\:chat .jp-ai-rendermime-markdown ul:last-child,
#jupyter-ai\\:\\:chat .jp-ai-rendermime-markdown ol:last-child,
#jupyter-ai\\:\\:chat .jp-ai-rendermime-markdown pre:last-child {
  margin-bottom: 0;
}

#jupyter-ai\\:\\:chat .jp-ai-rendermime-markdown pre {
  border-radius: 10px;
  border: 1px solid rgba(17, 35, 67, 0.08);
}

#jupyter-ai\\:\\:chat .jp-ai-rendermime-markdown code {
  border-radius: 6px;
}
`;

    if (styleNode.textContent !== css) {
        styleNode.textContent = css;
    }
    return true;
}

function applyJupyterAiChatAvatarTheme(doc) {
    const root = doc?.querySelector('#jupyter-ai\\:\\:chat');
    if (!root) return false;

    const aiAvatarUrl = getAbsoluteBrowserUrl(JUPYTER_AI_AVATAR_URL);
    const userAvatarUrl = readHomepageUserAvatarUrl();
    let touched = false;

    const bubbles = Array.from(root.querySelectorAll('.jp-ai-rendermime-markdown'));
    bubbles.forEach((bubble) => {
        const row = bubble.parentElement;
        if (!row) return;

        row.classList.add('fit-jai-message');
        const avatar = row.querySelector('.MuiAvatar-root');
        if (!avatar) return;

        const hasAgentImg = Boolean(avatar.querySelector('img'));
        row.classList.toggle('fit-jai-ai', hasAgentImg);
        row.classList.toggle('fit-jai-user', !hasAgentImg);

        avatar.classList.add('fit-jai-avatar');
        avatar.classList.toggle('fit-jai-avatar-ai', hasAgentImg);
        avatar.classList.toggle('fit-jai-avatar-user', !hasAgentImg);

        const customAvatarUrl = hasAgentImg ? aiAvatarUrl : userAvatarUrl;
        if (customAvatarUrl) {
            avatar.classList.add('fit-jai-avatar-custom');
            const status = getAvatarLoadStatus(customAvatarUrl);
            if (status === 'loaded') {
                avatar.classList.add('fit-jai-avatar-loaded');
                avatar.style.backgroundImage = `url("${customAvatarUrl}")`;
                touched = true;
            } else {
                avatar.classList.remove('fit-jai-avatar-loaded');
                avatar.style.removeProperty('background-image');
            }
        } else {
            avatar.classList.remove('fit-jai-avatar-custom');
            avatar.classList.remove('fit-jai-avatar-loaded');
            avatar.style.removeProperty('background-image');
            // Restore fallback initial avatar when no valid homepage avatar is available.
            if (!hasAgentImg) {
                const label = avatar.querySelector('.MuiTypography-root');
                if (label) {
                    label.style.display = '';
                }
            }
        }
    });

    return touched || bubbles.length > 0;
}

function dismissJupyterNewsPrompt(doc) {
    if (!doc) return false;
    const containers = Array.from(doc.querySelectorAll('div, section, aside, [role="dialog"], [role="alertdialog"]'));
    const target = containers.find((node) => {
        const raw = String(node?.textContent || '').trim();
        if (!raw) return false;
        const lower = raw.toLowerCase();
        return lower.includes('jupyter') && (lower.includes('news') || raw.includes('\u65b0\u95fb'));
    });
    if (!target) return false;
    const buttons = Array.from(target.querySelectorAll('button, [role="button"]'));
    const denyBtn = buttons.find((btn) => {
        const label = String(btn.textContent || '').trim().toLowerCase();
        return label === 'no' || label === 'not now' || label === 'no thanks' || label === '\u5426';
    });
    const closeBtn = buttons.find((btn) => {
        const label = [btn.getAttribute('aria-label'), btn.getAttribute('title'), btn.textContent]
            .filter(Boolean)
            .join(' ')
            .toLowerCase();
        return label === 'x' || label.includes('close') || label.includes('\u5173\u95ed');
    });
    const action = denyBtn || closeBtn;
    if (!action) return false;
    action.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: doc.defaultView }));
    return true;
}

function isPdfDocument(doc) {
    const fileName = String(doc?.fileName || '').toLowerCase();
    const fileType = String(doc?.fileType || '').toLowerCase();
    return fileName.endsWith('.pdf') || fileType === 'application/pdf';
}

function isPptxDocument(doc) {
    const fileName = String(doc?.fileName || '').toLowerCase();
    const fileType = String(doc?.fileType || '').toLowerCase();
    return (
        fileName.endsWith('.pptx')
        || fileType === 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    );
}

function isPptDocument(doc) {
    const fileName = String(doc?.fileName || '').toLowerCase();
    const fileType = String(doc?.fileType || '').toLowerCase();
    return fileName.endsWith('.ppt') || fileType === 'application/vnd.ms-powerpoint';
}

function isMarkdownDocument(doc) {
    const fileName = String(doc?.fileName || '').toLowerCase();
    const fileType = String(doc?.fileType || '').toLowerCase();
    return (
        fileName.endsWith('.md')
        || fileName.endsWith('.markdown')
        || fileType === 'text/markdown'
        || fileType === 'text/x-markdown'
    );
}

function isTextDocument(doc) {
    const fileName = String(doc?.fileName || '').toLowerCase();
    const fileType = String(doc?.fileType || '').toLowerCase();
    if (isMarkdownDocument(doc)) return true;
    if (fileName.endsWith('.txt') || fileName.endsWith('.csv') || fileName.endsWith('.json')) return true;
    if (fileType === 'application/json') return true;
    return fileType.startsWith('text/');
}

function getDocPreviewPriority(doc) {
    if (isPdfDocument(doc)) return 0;
    if (isPptxDocument(doc)) return 1;
    if (isPptDocument(doc)) return 2;
    if (isTextDocument(doc)) return 3;
    return 4;
}

function getFileExtension(fileName) {
    const normalized = String(fileName || '').trim();
    const match = normalized.match(/\.[^.]+$/);
    return match ? match[0].toLowerCase() : '';
}

function getAttachmentDisplayName(fileName, experimentTitle, index) {
    const extension = getFileExtension(fileName);
    const normalizedTitle = String(experimentTitle || '').trim();
    const baseName = normalizedTitle || `\u5b9e\u9a8c\u6587\u6863${index + 1}`;

    if (extension === '.pdf') {
        return `${baseName}\uff08\u9884\u89c8\uff09${extension}`;
    }
    if (extension === '.doc' || extension === '.docx') {
        return `${baseName}\uff08\u9644\u4ef6\uff09${extension}`;
    }
    return extension ? `${baseName}${extension}` : baseName;
}

function getAbsoluteUri(uri) {
    if (!uri) return uri;
    if (uri.startsWith('http://') || uri.startsWith('https://')) return uri;
    return `${window.location.origin}${uri}`;
}

function withJupyterWorkspaceReset(rawUrl) {
    if (!rawUrl) return rawUrl;
    try {
        const parsed = new URL(rawUrl, window.location.origin);
        if (!parsed.pathname.includes('/lab')) {
            return parsed.toString();
        }
        if (!parsed.searchParams.has('reset')) {
            parsed.searchParams.set('reset', '1');
        }
        return parsed.toString();
    } catch (error) {
        return rawUrl;
    }
}

function UnsupportedPreview({ uri, fileName }) {
    return (
        <div className="no-preview">
            <div className="file-icon">📄</div>
            <h3>{fileName}</h3>
            <p>该文件暂不支持在线预览，请下载后查看。</p>
            <a href={uri} className="download-btn" download>
                下载查看
            </a>
        </div>
    );
}

function PptxPreview({ uri, fileName }) {
    const hostRef = useRef(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        let cancelled = false;
        const hostElement = hostRef.current;

        const renderPptx = async () => {
            setLoading(true);
            setError('');

            if (!hostElement) return;
            hostElement.innerHTML = '';

            try {
                const [{ init }, response] = await Promise.all([
                    import('pptx-preview'),
                    axios.get(uri, { responseType: 'arraybuffer' })
                ]);

                if (cancelled) return;

                const width = Math.max(hostElement.clientWidth - 24, 640);
                const height = Math.max(Math.round(width * 9 / 16), 360);
                const previewer = init(hostElement, { width, height });
                await previewer.preview(response.data);
            } catch (previewError) {
                console.error('Failed to preview pptx:', previewError);
                if (!cancelled) {
                    setError('PPTX 预览失败，请下载后查看。');
                }
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        };

        renderPptx();
        return () => {
            cancelled = true;
            if (hostElement) {
                hostElement.innerHTML = '';
            }
        };
    }, [uri]);

    if (error) {
        return (
            <div className="no-preview">
                <div className="file-icon">📊</div>
                <h3>{fileName}</h3>
                <p>{error}</p>
                <a href={uri} className="download-btn" download>
                    下载查看
                </a>
            </div>
        );
    }

    return (
        <div className="ppt-preview-wrapper">
            {loading ? <div className="loading-pane">正在加载课件...</div> : null}
            <div ref={hostRef} className="ppt-preview-host" style={{ display: loading ? 'none' : 'block' }} />
        </div>
    );
}

function OfficePptPreview({ uri, fileName }) {
    const absoluteUri = getAbsoluteUri(uri);
    const officeEmbedUri = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(absoluteUri)}`;

    return (
        <div className="ppt-preview-wrapper">
            <iframe src={officeEmbedUri} title={fileName} className="ppt-office-iframe" frameBorder="0" />
            <div className="ppt-preview-tip">
                若预览失败，请直接下载查看。
                <a href={uri} download>下载文件</a>
            </div>
        </div>
    );
}

function TextDocumentPreview({ uri, fileName }) {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [content, setContent] = useState('');

    useEffect(() => {
        let cancelled = false;

        const loadText = async () => {
            setLoading(true);
            setError('');
            setContent('');
            try {
                const response = await axios.get(uri, { responseType: 'text' });
                if (cancelled) return;
                const text = typeof response.data === 'string'
                    ? response.data
                    : JSON.stringify(response.data, null, 2);
                setContent(text || '');
            } catch (loadError) {
                console.error('Failed to load text preview:', loadError);
                if (!cancelled) {
                    setError('文本预览加载失败，请下载后查看。');
                }
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        };

        loadText();
        return () => {
            cancelled = true;
        };
    }, [uri]);

    if (loading) {
        return <div className="loading-pane">正在加载文档...</div>;
    }

    if (error) {
        return <UnsupportedPreview uri={uri} fileName={fileName} />;
    }

    return <pre className="workspace-text-preview">{content || '暂无内容'}</pre>;
}

function ExperimentWorkspace() {
    const { experimentId } = useParams();
    const navigate = useNavigate();
    const jupyterIframeRef = useRef(null);
    const jupyterUiPatchTimerRef = useRef(null);
    const jupyterUiPatchAttemptsRef = useRef(0);
    const workspaceLoadTimeoutRef = useRef(null);
    const labResetUrlsRef = useRef(new Set());
    const [experiment, setExperiment] = useState(null);
    const [docs, setDocs] = useState([]);
    const [activeDocIndex, setActiveDocIndex] = useState(0);
    const [, setStudentExp] = useState(null);
    const [workspaceUrls, setWorkspaceUrls] = useState({});
    const [availableWorkspaces, setAvailableWorkspaces] = useState([]);
    const [activeWorkspace, setActiveWorkspace] = useState('lab');
    const [workspaceUrl, setWorkspaceUrl] = useState('');
    const [showCodeServerFallback, setShowCodeServerFallback] = useState(false);
    const username = String(localStorage.getItem('username') || '').trim();
    const userRole = String(localStorage.getItem('userRole') || '').trim().toLowerCase();
    const isTeacherOrAdmin = userRole === 'teacher' || userRole === 'admin';
    const isJupyterWorkspace = activeWorkspace === 'lab' || activeWorkspace === 'notebook';


    const clearJupyterUiPatchTimer = () => {
        if (jupyterUiPatchTimerRef.current) {
            window.clearInterval(jupyterUiPatchTimerRef.current);
            jupyterUiPatchTimerRef.current = null;
        }
    };

    const clearWorkspaceLoadTimeout = () => {
        if (workspaceLoadTimeoutRef.current) {
            window.clearTimeout(workspaceLoadTimeoutRef.current);
            workspaceLoadTimeoutRef.current = null;
        }
    };

    const resolveWorkspaceIframeUrl = (rawUrl, workspaceKey) => {
        if (!rawUrl) return '';
        if (workspaceKey !== 'lab') {
            return rawUrl;
        }
        if (labResetUrlsRef.current.has(rawUrl)) {
            return rawUrl;
        }
        labResetUrlsRef.current.add(rawUrl);
        return withJupyterWorkspaceReset(rawUrl);
    };

    const applyWorkspaceResponse = (payload, preferredWorkspace = '') => {
        const launch = getWorkspaceLaunchInfo(payload, preferredWorkspace);
        const nextWorkspaceUrls = {};

        Object.entries(launch.workspaceUrls || {}).forEach(([key, value]) => {
            if (value) {
                nextWorkspaceUrls[key] = value;
            }
        });

        const nextAvailableWorkspaces = (launch.availableWorkspaces || [])
            .filter((key) => nextWorkspaceUrls[key]);
        const nextActiveWorkspace = nextWorkspaceUrls[launch.defaultWorkspace]
            ? launch.defaultWorkspace
            : (nextAvailableWorkspaces[0] || '');

        setWorkspaceUrls(nextWorkspaceUrls);
        setAvailableWorkspaces(nextAvailableWorkspaces);
        setActiveWorkspace(nextActiveWorkspace || 'lab');
        setWorkspaceUrl(
            nextActiveWorkspace
                ? resolveWorkspaceIframeUrl(nextWorkspaceUrls[nextActiveWorkspace], nextActiveWorkspace)
                : ''
        );
        setShowCodeServerFallback(false);
    };

    const handleResourceLaunchError = async (error, retryFn) => {
        const detail = error?.response?.data?.detail;
        const code = detail && typeof detail === 'object' ? detail.code : '';
        if (code === 'RESOURCE_LIMIT_REACHED') {
            alert(detail.message || '当前实验环境人数较多，请稍后再试');
            return null;
        }
        if (code === 'RESTART_REQUIRED') {
            const required = detail.required_quota || {};
            const summary = required.cpu_limit && required.memory_limit
                ? `${required.cpu_limit} CPU / ${required.memory_limit} 内存`
                : '更高资源';
            const ok = window.confirm(`当前实验需要 ${summary}，需要重启实验环境后进入。请先保存 Notebook，再继续。`);
            if (!ok) return null;
            return retryFn(true);
        }
        throw error;
    };

    const patchJupyterUiOnce = () => {
        if (!isJupyterWorkspace) return false;
        const iframe = jupyterIframeRef.current;
        const frameWindow = iframe?.contentWindow;
        const doc = iframe?.contentDocument;
        if (!frameWindow || !doc) return false;

        ensureJupyterAiChatStyles(doc);
        applyJupyterAiChatAvatarTheme(doc);
        dismissJupyterNewsPrompt(doc);

        const panelReady = hasJupyterAiPanelContent(doc);
        if (!panelReady) {
            if (!tryOpenJupyterAiByCommand(frameWindow)) {
                tryOpenJupyterAiByDom(doc);
            }
        } else {
            tryFocusJupyterAiInput(frameWindow, doc);
        }
        return hasJupyterAiPanelContent(doc);
    };

    const handleWorkspaceIframeLoad = () => {
        clearWorkspaceLoadTimeout();
        setShowCodeServerFallback(false);
        clearJupyterUiPatchTimer();
        jupyterUiPatchAttemptsRef.current = 0;

        if (!isJupyterWorkspace) {
            return;
        }

        const tick = () => {
            jupyterUiPatchAttemptsRef.current += 1;
            let panelReady = false;
            try {
                panelReady = patchJupyterUiOnce();
            } catch (error) {
                // ignore transient iframe readiness timing
            }

            if (panelReady && jupyterUiPatchAttemptsRef.current >= 4) {
                clearJupyterUiPatchTimer();
                return;
            }
            if (jupyterUiPatchAttemptsRef.current >= JUPYTER_UI_PATCH_MAX_ATTEMPTS) {
                clearJupyterUiPatchTimer();
            }
        };

        tick();
        jupyterUiPatchTimerRef.current = window.setInterval(tick, JUPYTER_UI_PATCH_INTERVAL_MS);
    };

    useEffect(() => {
        if (!username) {
            alert('请先登录');
            navigate('/');
            return;
        }
        loadData();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [experimentId, username]);

    useEffect(() => {
        clearJupyterUiPatchTimer();
        jupyterUiPatchAttemptsRef.current = 0;
        return () => {
            clearJupyterUiPatchTimer();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [workspaceUrl, isJupyterWorkspace]);

    useEffect(() => {
        const rawUrl = workspaceUrls[activeWorkspace] || '';
        const nextUrl = resolveWorkspaceIframeUrl(rawUrl, activeWorkspace);
        setWorkspaceUrl(nextUrl);
        setShowCodeServerFallback(false);
        clearWorkspaceLoadTimeout();

        if (activeWorkspace === 'code' && nextUrl) {
            workspaceLoadTimeoutRef.current = window.setTimeout(() => {
                setShowCodeServerFallback(true);
            }, CODE_SERVER_LOAD_TIMEOUT_MS);
        }

        return () => {
            clearWorkspaceLoadTimeout();
        };
    }, [activeWorkspace, workspaceUrls]);

    const loadData = async () => {
        try {
            const expRes = await axios.get(`${API_BASE_URL}/api/experiments/${experimentId}`);
            setExperiment(expRes.data);

            const attRes = await axios.get(`${API_BASE_URL}/api/experiments/${experimentId}/attachments`);
            const fetchedAttachments = attRes.data || [];

            if (fetchedAttachments.length > 0) {
                const formattedDocs = fetchedAttachments
                    .map((att, index) => ({
                        uri: `/api/attachments/${att.id}/download`,
                        fileName: att.filename,
                        displayName: getAttachmentDisplayName(att.filename, expRes.data?.title, index),
                        fileType: att.content_type,
                    }))
                    .sort((a, b) => getDocPreviewPriority(a) - getDocPreviewPriority(b));

                setDocs(formattedDocs);
                setActiveDocIndex(0);
            } else {
                setDocs([]);
                setActiveDocIndex(0);
            }

            if (isTeacherOrAdmin) {
                const fetchHubLaunch = (forceRestart = false) => axios.get(
                    `${API_BASE_URL}/api/jupyterhub/auto-login-url`,
                    { params: { username, experiment_id: experimentId, force_restart: forceRestart } }
                );
                let hubResp = null;
                try {
                    hubResp = await fetchHubLaunch(false);
                } catch (launchError) {
                    hubResp = await handleResourceLaunchError(launchError, fetchHubLaunch);
                    if (!hubResp) return;
                }
                applyWorkspaceResponse(hubResp?.data);
                return;
            }

            const fetchStudentLaunch = (forceRestart = false) => axios.post(
                `${API_BASE_URL}/api/student-experiments/start/${experimentId}`,
                null,
                { params: { student_id: username, force_restart: forceRestart } }
            );
            let startRes = null;
            try {
                startRes = await fetchStudentLaunch(false);
            } catch (launchError) {
                startRes = await handleResourceLaunchError(launchError, fetchStudentLaunch);
                if (!startRes) return;
            }
            applyWorkspaceResponse(startRes.data);

            if (startRes.data.student_experiment_id) {
                try {
                    const detailRes = await axios.get(
                        `${API_BASE_URL}/api/student-experiments/${startRes.data.student_experiment_id}`
                    );
                    setStudentExp(detailRes.data);
                } catch (detailErr) {
                    console.warn('Failed to load student experiment detail:', detailErr);
                }
            }
        } catch (error) {
            console.error('Failed to load workspace data:', error);
            const detail = error?.response?.data?.detail;
            alert(detail ? `加载实验数据失败：${detail}` : '加载实验数据失败');
        }
    };

    const handleBackToCourseList = () => {
        if (isTeacherOrAdmin) {
            navigate('/');
            return;
        }
        navigate('/');
    };

    const openActiveWorkspaceInNewTab = () => {
        const targetUrl = workspaceUrls[activeWorkspace] || workspaceUrl;
        if (!targetUrl) return;
        window.open(targetUrl, '_blank', 'noopener,noreferrer');
    };

    return (
        <div className="workspace-container">
            <div className="workspace-header">
                <button onClick={handleBackToCourseList} className="back-btn">← 返回</button>
                <h2>{experiment?.title}</h2>
                <div className="workspace-info">
                    {availableWorkspaces.length > 1 ? (
                        <div className="workspace-switcher" role="tablist" aria-label="工作区切换">
                            {availableWorkspaces.map((workspaceKey) => (
                                <button
                                    key={workspaceKey}
                                    type="button"
                                    className={`workspace-switch-btn ${activeWorkspace === workspaceKey ? 'active' : ''}`}
                                    onClick={() => setActiveWorkspace(workspaceKey)}
                                >
                                    {WORKSPACE_LABELS[workspaceKey] || workspaceKey}
                                </button>
                            ))}
                        </div>
                    ) : null}
                    <span>{username}</span>
                </div>
            </div>

            <Split
                className="workspace-split"
                sizes={[40, 60]}
                minSize={300}
                expandToMin={false}
                gutterSize={10}
                gutterAlign="center"
                snapOffset={30}
                dragInterval={1}
                direction="horizontal"
                cursor="col-resize"
            >
                <div className="left-pane">
                    {docs.length > 0 ? (
                        <div
                            className="doc-container"
                            style={{
                                height: '100%',
                                display: 'flex',
                                flexDirection: 'column',
                                minHeight: 0
                            }}
                        >
                            {docs.length > 1 ? (
                                <div className="doc-tabs">
                                    {docs.map((doc, index) => (
                                        <button
                                            key={doc.uri}
                                            className={`doc-tab-btn ${index === activeDocIndex ? 'active' : ''}`}
                                            onClick={() => setActiveDocIndex(index)}
                                        >
                                            {doc.displayName || doc.fileName}
                                        </button>
                                    ))}
                                </div>
                            ) : null}

                            {docs.map((doc, index) => (
                                <div
                                    key={doc.uri}
                                    style={{
                                        flex: 1,
                                        minHeight: 0,
                                        display: index === activeDocIndex ? 'block' : 'none'
                                    }}
                                >
                                    {isPdfDocument(doc) ? (
                                        <iframe
                                            src={doc.uri}
                                            title={doc.displayName || doc.fileName}
                                            style={{ width: '100%', height: '100%', border: 'none' }}
                                        />
                                    ) : isPptxDocument(doc) ? (
                                        <PptxPreview uri={doc.uri} fileName={doc.displayName || doc.fileName} />
                                    ) : isPptDocument(doc) ? (
                                        <OfficePptPreview uri={doc.uri} fileName={doc.displayName || doc.fileName} />
                                    ) : isTextDocument(doc) ? (
                                        <TextDocumentPreview uri={doc.uri} fileName={doc.displayName || doc.fileName} />
                                    ) : (
                                        <UnsupportedPreview uri={doc.uri} fileName={doc.displayName || doc.fileName} />
                                    )}
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="no-doc">
                            <h3>实验指导书</h3>
                            <p>本实验暂时无附件资料。</p>
                            {experiment?.description ? (
                                <div className="text-description">
                                    <h4>描述：</h4>
                                    <p>{experiment.description}</p>
                                </div>
                            ) : null}
                        </div>
                    )}
                </div>

                <div className="right-pane">
                    {workspaceUrl ? (
                        <>
                            <iframe
                                ref={jupyterIframeRef}
                                src={workspaceUrl}
                                title={WORKSPACE_LABELS[activeWorkspace] || 'Workspace'}
                                className="jupyter-iframe"
                                allow="clipboard-read; clipboard-write"
                                onLoad={handleWorkspaceIframeLoad}
                            />
                            {showCodeServerFallback && activeWorkspace === 'code' ? (
                                <div className="workspace-fallback-banner">
                                    <span>VS Code 嵌入加载较慢或被浏览器拦截时，可直接在新标签页打开。</span>
                                    <button type="button" onClick={openActiveWorkspaceInNewTab}>
                                        在新标签页打开 VS Code
                                    </button>
                                </div>
                            ) : null}
                        </>
                    ) : (
                        <div className="loading-pane">正在加载实验环境...</div>
                    )}
                </div>
            </Split>
        </div>
    );
}

export default ExperimentWorkspace;
