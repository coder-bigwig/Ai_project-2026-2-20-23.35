const TOKEN_COOKIE_NAME = 'training_jhub_token';
const TOKEN_COOKIE_MAX_AGE_SECONDS = 43200;
const JUPYTER_COOKIE_PATH = '/jupyter/';

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

