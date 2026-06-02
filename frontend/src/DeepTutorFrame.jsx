import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';
const DEEPTUTOR_TARGET = String(process.env.REACT_APP_DEEPTUTOR_URL || '/chat').replace(/\/+$/, '') || '/chat';

function readUsername() {
    return String(localStorage.getItem('username') || '').trim();
}

async function clearExistingDeepTutorSession(username) {
    await axios.post(
        `${API_BASE_URL}/api/deeptutor/logout`,
        {},
        {
            params: username ? { username } : undefined,
            withCredentials: true
        }
    );
}

async function createDeepTutorSession(username) {
    await axios.post(
        `${API_BASE_URL}/api/deeptutor/sso`,
        { username },
        { withCredentials: true }
    );
}

export function getDeepTutorErrorMessage(err) {
    const detail = err?.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) {
        return `DeepTutor login failed: ${detail.trim()}`;
    }
    return 'DeepTutor login failed. Please try again.';
}

function DeepTutorFrame() {
    const navigate = useNavigate();

    useEffect(() => {
        let cancelled = false;
        const username = readUsername();

        async function go() {
            if (!username) {
                navigate('/login', { replace: true });
                return;
            }

            try {
                await clearExistingDeepTutorSession(username);
                await createDeepTutorSession(username);
            } catch (err) {
                if (cancelled) return;
                console.error('DeepTutor SSO failed:', err);
                window.alert(getDeepTutorErrorMessage(err));
                navigate('/', { replace: true });
                return;
            }

            if (cancelled) return;
            const separator = DEEPTUTOR_TARGET.includes('?') ? '&' : '?';
            window.location.replace(`${DEEPTUTOR_TARGET}${separator}t=${Date.now()}`);
        }

        go();
        return () => { cancelled = true; };
    }, [navigate]);

    return null;
}

export default DeepTutorFrame;
