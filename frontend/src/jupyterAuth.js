const TOKEN_COOKIE_NAME = 'training_jhub_token';
const TOKEN_COOKIE_MAX_AGE_SECONDS = 43200;
const JUPYTER_COOKIE_PATH = '/jupyter/';
const WORKSPACE_KEYS = ['lab', 'notebook', 'code'];

export function openPendingWorkspaceWindow(title = 'Opening workspace...') {
    try {
        const popup = window.open('', '_blank');
        if (popup && popup.document) {
            popup.document.title = title;
            popup.document.body.innerHTML = '<p style="font-family: sans-serif; padding: 16px;">正在打开工作区...</p>';
        }
        return popup;
    } catch (error) {
        return null;
    }
}

export function navigatePendingWorkspaceWindow(popup, rawUrl) {
    const url = String(rawUrl || '').trim();
    if (!url) {
        if (popup && !popup.closed) popup.close();
        return false;
    }

    if (popup && !popup.closed) {
        popup.location.replace(url);
        return true;
    }

    const opened = window.open(url, '_blank', 'noopener,noreferrer');
    return Boolean(opened);
}

export function closePendingWorkspaceWindow(popup) {
    if (popup && !popup.closed) {
        popup.close();
    }
}

export function persistJupyterTokenFromUrl(rawUrl) {
    if (!rawUrl) {
        return rawUrl;
    }

    try {
        const parsedUrl = new URL(rawUrl, window.location.origin);
        const token = parsedUrl.searchParams.get('token');

        if (!token) {
            return rawUrl;
        }

        document.cookie = `${TOKEN_COOKIE_NAME}=${encodeURIComponent(token)}; Path=${JUPYTER_COOKIE_PATH}; Max-Age=${TOKEN_COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
    } catch (error) {
        // Ignore parsing errors and keep the original URL flow.
    }

    return rawUrl;
}

function normalizeWorkspaceKey(value) {
    const normalized = String(value || '').trim().toLowerCase();
    return WORKSPACE_KEYS.includes(normalized) ? normalized : '';
}

export function getWorkspaceLaunchInfo(payload, preferredWorkspace = '') {
    const rawWorkspaceUrls = payload && typeof payload.workspace_urls === 'object' && payload.workspace_urls
        ? payload.workspace_urls
        : {};
    const workspaceUrls = {};

    WORKSPACE_KEYS.forEach((key) => {
        const value = persistJupyterTokenFromUrl(rawWorkspaceUrls[key] || '');
        if (value) {
            workspaceUrls[key] = value;
        }
    });

    const legacyJupyterUrl = persistJupyterTokenFromUrl(payload?.jupyter_url || '');
    if (!workspaceUrls.lab && legacyJupyterUrl) {
        workspaceUrls.lab = legacyJupyterUrl;
    }

    const availableWorkspaces = (Array.isArray(payload?.available_workspaces) ? payload.available_workspaces : WORKSPACE_KEYS)
        .map((item) => normalizeWorkspaceKey(item))
        .filter((item, index, values) => item && values.indexOf(item) === index && workspaceUrls[item]);

    if (availableWorkspaces.length === 0) {
        WORKSPACE_KEYS.forEach((key) => {
            if (workspaceUrls[key] && !availableWorkspaces.includes(key)) {
                availableWorkspaces.push(key);
            }
        });
    }

    const requestedWorkspace = normalizeWorkspaceKey(preferredWorkspace);
    const defaultWorkspace = normalizeWorkspaceKey(payload?.default_workspace_ui) || 'lab';
    const resolvedWorkspace = [requestedWorkspace, defaultWorkspace, 'lab', 'notebook', 'code']
        .find((key) => key && workspaceUrls[key])
        || '';

    return {
        workspaceUrls,
        availableWorkspaces,
        defaultWorkspace: resolvedWorkspace || defaultWorkspace,
        selectedWorkspace: resolvedWorkspace,
        selectedUrl: resolvedWorkspace ? workspaceUrls[resolvedWorkspace] : (legacyJupyterUrl || ''),
    };
}
