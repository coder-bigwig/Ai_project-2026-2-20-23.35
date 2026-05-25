import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './DeepTutorFrame.css';

const DEEPTUTOR_URL = process.env.REACT_APP_DEEPTUTOR_URL || '/chat';

function DeepTutorFrame() {
  const navigate = useNavigate();
  const targetUrl = String(DEEPTUTOR_URL || '').replace(/\/+$/, '') || '/chat';

  useEffect(() => {
    const separator = targetUrl.includes('?') ? '&' : '?';
    window.location.replace(`${targetUrl}${separator}t=${Date.now()}`);
  }, [targetUrl]);

  return (
    <div className="deeptutor-launch-shell">
      <div className="deeptutor-launch-card">
        <h1>DeepTutor AI导师</h1>
        <p>正在打开 DeepTutor 独立学习空间。</p>
        <div className="deeptutor-launch-actions">
          <button type="button" className="deeptutor-frame-btn primary" onClick={() => window.location.assign(targetUrl)}>
            立即打开
          </button>
          <button type="button" className="deeptutor-frame-btn" onClick={() => navigate('/')}>
            返回平台
          </button>
        </div>
        <span>{targetUrl}</span>
      </div>
    </div>
  );
}

export default DeepTutorFrame;
