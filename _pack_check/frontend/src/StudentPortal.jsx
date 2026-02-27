// StudentPortal.jsx - 学生门户主界面

import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { persistJupyterTokenFromUrl } from './jupyterAuth';
import './StudentPortal.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';
const JUPYTERHUB_URL = process.env.REACT_APP_JUPYTERHUB_URL || 'http://localhost:8003';
const AI_URL = process.env.REACT_APP_AI_URL || 'http://localhost:8002';

// ==================== 主组件 ====================

function StudentPortal({ username, tab }) {
  const [experiments, setExperiments] = useState([]);
  const [myExperiments, setMyExperiments] = useState([]);
  const [activeTab, setActiveTab] = useState(tab || 'available');
  const [loading, setLoading] = useState(true);
  const [selectedExperiment, setSelectedExperiment] = useState(null);
  const [showAIChat, setShowAIChat] = useState(false);

  const studentId = username || 'student001'; // Use prop or fallback

  // ==================== 数据加载 ====================

  useEffect(() => {
    loadExperiments();
    loadMyExperiments();
  }, []);

  const loadExperiments = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/experiments`);
      setExperiments(response.data);
      setLoading(false);
    } catch (error) {
      console.error('加载实验失败:', error);
      setLoading(false);
    }
  };

  const loadMyExperiments = async () => {
    try {
      const response = await axios.get(
        `${API_BASE_URL}/api/student-experiments/my-experiments/${studentId}`
      );
      setMyExperiments(response.data);
    } catch (error) {
      console.error('加载我的实验失败:', error);
    }
  };

  // ==================== 实验操作 ====================

  const startExperiment = async (experimentId) => {
    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/student-experiments/start/${experimentId}`,
        null,
        { params: { student_id: studentId } }
      );

      // 打开JupyterLab
      const launchUrl = persistJupyterTokenFromUrl(response.data.jupyter_url);
      window.open(launchUrl, '_blank');

      // 刷新数据
      loadMyExperiments();
    } catch (error) {
      console.error('启动实验失败:', error);
      alert('启动实验失败，请重试');
    }
  };

  const continueExperiment = (studentExpId) => {
    window.open(JUPYTERHUB_URL, '_blank');
  };

  const submitExperiment = async (studentExpId, notebookContent) => {
    try {
      await axios.post(
        `${API_BASE_URL}/api/student-experiments/${studentExpId}/submit`,
        { notebook_content: notebookContent }
      );
      alert('实验已提交成功！');
      loadMyExperiments();
    } catch (error) {
      console.error('提交实验失败:', error);
      alert('提交失败，请重试');
    }
  };

  // ==================== 渲染组件 ====================

  return (
    <div className="student-portal">
      {/* 导航栏 */}
      <header className="portal-header">
        <h1>福州理工学院AI编程实践教学平台</h1>
        <nav>
          <button onClick={() => setActiveTab('available')}>
            可用实验
          </button>
          <button onClick={() => setActiveTab('my-experiments')}>
            我的实验
          </button>
          <button onClick={() => setShowAIChat(!showAIChat)}>
            🤖 AI助手
          </button>
        </nav>
        <div className="user-info">
          <span>学生: {studentId}</span>
        </div>
      </header>

      {/* 主内容区 */}
      <main className="portal-main">
        {activeTab === 'available' && (
          <ExperimentList
            experiments={experiments}
            loading={loading}
            onStart={startExperiment}
            onViewDetail={setSelectedExperiment}
          />
        )}

        {activeTab === 'my-experiments' && (
          <MyExperimentsList
            myExperiments={myExperiments}
            onContinue={continueExperiment}
            onSubmit={submitExperiment}
          />
        )}
      </main>

      {/* 实验详情弹窗 */}
      {selectedExperiment && (
        <ExperimentDetailModal
          experiment={selectedExperiment}
          onClose={() => setSelectedExperiment(null)}
          onStart={startExperiment}
        />
      )}

      {/* AI助手侧边栏 */}
      {showAIChat && (
        <AIAssistantPanel onClose={() => setShowAIChat(false)} />
      )}
    </div>
  );
}

// ==================== 实验列表组件 ====================

function ExperimentList({ experiments, loading, onStart, onViewDetail }) {
  const [filterDifficulty, setFilterDifficulty] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');

  const filteredExperiments = experiments.filter(exp => {
    const matchDifficulty = filterDifficulty === 'all' || exp.difficulty === filterDifficulty;
    const matchSearch = exp.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      exp.description.toLowerCase().includes(searchTerm.toLowerCase());
    return matchDifficulty && matchSearch;
  });

  if (loading) {
    return <div className="loading">加载中...</div>;
  }

  return (
    <div className="experiment-list">
      {/* 筛选和搜索 */}
      <div className="filters">
        <input
          type="text"
          placeholder="搜索实验..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="search-input"
        />
        <select
          value={filterDifficulty}
          onChange={(e) => setFilterDifficulty(e.target.value)}
          className="difficulty-filter"
        >
          <option value="all">所有难度</option>
          <option value="初级">初级</option>
          <option value="中级">中级</option>
          <option value="高级">高级</option>
        </select>
      </div>

      {/* 实验卡片 */}
      <div className="experiment-grid">
        {filteredExperiments.map(exp => (
          <ExperimentCard
            key={exp.id}
            experiment={exp}
            onStart={onStart}
            onViewDetail={onViewDetail}
          />
        ))}
      </div>

      {filteredExperiments.length === 0 && (
        <div className="no-results">没有找到符合条件的实验</div>
      )}
    </div>
  );
}

// ==================== 实验卡片组件 ====================

function ExperimentCard({ experiment, onStart, onViewDetail }) {
  const difficultyColors = {
    '初级': '#52c41a',
    '中级': '#faad14',
    '高级': '#f5222d'
  };

  return (
    <div className="experiment-card">
      <div className="card-header">
        <h3>{experiment.title}</h3>
        <span
          className="difficulty-badge"
          style={{ backgroundColor: difficultyColors[experiment.difficulty] }}
        >
          {experiment.difficulty}
        </span>
      </div>

      <p className="card-description">{experiment.description}</p>

      <div className="card-tags">
        {experiment.tags.map(tag => (
          <span key={tag} className="tag">{tag}</span>
        ))}
      </div>

      <div className="card-footer">
        <button
          className="btn btn-primary"
          onClick={() => onStart(experiment.id)}
        >
          开始实验
        </button>
        <button
          className="btn btn-secondary"
          onClick={() => onViewDetail(experiment)}
        >
          查看详情
        </button>
      </div>
    </div>
  );
}

// ==================== 我的实验列表组件 ====================

function MyExperimentsList({ myExperiments, onContinue, onSubmit }) {
  const statusColors = {
    '未开始': '#d9d9d9',
    '进行中': '#1890ff',
    '已提交': '#52c41a',
    '已评分': '#722ed1'
  };

  return (
    <div className="my-experiments">
      <h2>我的实验</h2>

      {myExperiments.length === 0 ? (
        <div className="empty-state">
          <p>还没有开始任何实验</p>
          <button onClick={() => window.location.reload()}>
            查看可用实验
          </button>
        </div>
      ) : (
        <div className="experiments-table">
          <table>
            <thead>
              <tr>
                <th>实验名称</th>
                <th>状态</th>
                <th>开始时间</th>
                <th>提交时间</th>
                <th>分数</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {myExperiments.map(exp => (
                <tr key={exp.id}>
                  <td>{exp.experiment_id}</td>
                  <td>
                    <span
                      className="status-badge"
                      style={{ backgroundColor: statusColors[exp.status] }}
                    >
                      {exp.status}
                    </span>
                  </td>
                  <td>{exp.start_time ? new Date(exp.start_time).toLocaleString() : '-'}</td>
                  <td>{exp.submit_time ? new Date(exp.submit_time).toLocaleString() : '-'}</td>
                  <td>{exp.score !== null ? `${exp.score}分` : '-'}</td>
                  <td>
                    {exp.status === '进行中' && (
                      <>
                        <button
                          className="btn btn-small"
                          onClick={() => onContinue(exp.id)}
                        >
                          继续实验
                        </button>
                        <button
                          className="btn btn-small"
                          style={{ marginLeft: '8px', backgroundColor: '#52c41a', color: 'white', border: 'none' }}
                          onClick={() => {
                            if (window.confirm('确认提交实验吗？提交后将无法修改。')) {
                              onSubmit(exp.id, 'Notebook content placeholder');
                            }
                          }}
                        >
                          提交
                        </button>
                      </>
                    )}
                    {exp.status === '已评分' && exp.ai_feedback && (
                      <button
                        className="btn btn-small"
                        onClick={() => alert(exp.ai_feedback)}
                      >
                        查看反馈
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ==================== 实验详情弹窗 ====================

function ExperimentDetailModal({ experiment, onClose, onStart }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{experiment.title}</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          <section>
            <h3>实验描述</h3>
            <p>{experiment.description}</p>
          </section>

          <section>
            <h3>难度级别</h3>
            <p>{experiment.difficulty}</p>
          </section>

          <section>
            <h3>资源配置</h3>
            <ul>
              <li>CPU: {experiment.resources.cpu} 核</li>
              <li>内存: {experiment.resources.memory}</li>
              <li>存储: {experiment.resources.storage}</li>
            </ul>
          </section>

          {experiment.deadline && (
            <section>
              <h3>截止时间</h3>
              <p>{new Date(experiment.deadline).toLocaleString()}</p>
            </section>
          )}

          <section>
            <h3>标签</h3>
            <div className="tags">
              {experiment.tags.map(tag => (
                <span key={tag} className="tag">{tag}</span>
              ))}
            </div>
          </section>
        </div>

        <div className="modal-footer">
          <button className="btn btn-primary" onClick={() => {
            onStart(experiment.id);
            onClose();
          }}>
            开始实验
          </button>
          <button className="btn btn-secondary" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}

// ==================== AI助手面板 ====================

function AIAssistantPanel({ onClose }) {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: '你好！我是AI编程助手，有什么可以帮你的吗？' }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const sendMessage = async () => {
    if (!inputMessage.trim()) return;

    const userMessage = { role: 'user', content: inputMessage };
    setMessages([...messages, userMessage]);
    setInputMessage('');
    setLoading(true);

    try {
      const response = await axios.post(
        `${AI_URL}/api/chat`,
        {
          message: inputMessage,
          history: messages
        }
      );

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: response.data.answer
      }]);
    } catch (error) {
      console.error('AI助手错误:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '抱歉，我遇到了一些问题，请稍后再试。'
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ai-assistant-panel">
      <div className="panel-header">
        <h3>🤖 AI编程助手</h3>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>

      <div className="chat-messages">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            <div className="message-content">{msg.content}</div>
          </div>
        ))}
        {loading && (
          <div className="message assistant">
            <div className="typing-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        )}
      </div>

      <div className="chat-input">
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="输入你的问题..."
          disabled={loading}
        />
        <button
          onClick={sendMessage}
          disabled={loading || !inputMessage.trim()}
        >
          发送
        </button>
      </div>
    </div>
  );
}

export default StudentPortal;
