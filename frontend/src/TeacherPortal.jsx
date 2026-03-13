// TeacherPortal.jsx - 教师门户主界面

import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './StudentPortal.css'; // 复用大部分样式

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

function TeacherPortal({ username, tab = 'experiments' }) {
    const [activeTab, setActiveTab] = useState(tab);
    const [experiments, setExperiments] = useState([]);
    const [submissions, setSubmissions] = useState([]);
    const [statistics, setStatistics] = useState(null);
    const [loading, setLoading] = useState(true);
    const [editingExperiment, setEditingExperiment] = useState(null);

    useEffect(() => {
        if (activeTab === 'experiments') loadExperiments();
        if (activeTab === 'submissions') loadSubmissions();
        if (activeTab === 'statistics') loadStatistics();
    }, [activeTab]);

    const loadExperiments = async () => {
        setLoading(true);
        try {
            const response = await axios.get(`${API_BASE_URL}/api/experiments`);
            setExperiments(response.data);
        } catch (error) {
            console.error('加载实验失败:', error);
        } finally {
            setLoading(false);
        }
    };

    const loadSubmissions = async () => {
        setLoading(true);
        try {
            // 模拟获取所有提交，实际API可能需要分页或筛选
            // 这里为了演示，获取所有实验的提交
            const exps = await axios.get(`${API_BASE_URL}/api/experiments`);
            let allSubmissions = [];
            for (const exp of exps.data) {
                try {
                    const subs = await axios.get(`${API_BASE_URL}/api/teacher/experiments/${exp.id}/submissions`);
                    allSubmissions = [...allSubmissions, ...subs.data];
                } catch (e) {
                    console.warn(`无法获取实验 ${exp.title} 的提交`);
                }
            }
            setSubmissions(allSubmissions);
        } catch (error) {
            console.error('加载提交失败:', error);
        } finally {
            setLoading(false);
        }
    };

    const loadStatistics = async () => {
        setLoading(true);
        try {
            const response = await axios.get(`${API_BASE_URL}/api/teacher/statistics`);
            setStatistics(response.data);
        } catch (error) {
            console.error('加载统计失败:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleDeleteExperiment = async (id) => {
        if (!window.confirm('确定要删除这个实验吗？')) return;
        try {
            await axios.delete(`${API_BASE_URL}/api/experiments/${id}`);
            loadExperiments();
        } catch (error) {
            console.error('删除失败:', error);
            alert('删除失败');
        }
    };

    const handleSaveExperiment = async (experimentData) => {
        try {
            if (experimentData.id) {
                await axios.put(`${API_BASE_URL}/api/experiments/${experimentData.id}`, experimentData);
            } else {
                await axios.post(`${API_BASE_URL}/api/experiments`, {
                    ...experimentData,
                    created_by: username
                });
            }
            setEditingExperiment(null);
            loadExperiments();
        } catch (error) {
            console.error('保存失败:', error);
            alert('保存失败，请检查输入');
        }
    };

    const handleGradeSubmission = async (id, score, comment) => {
        try {
            await axios.post(`${API_BASE_URL}/api/teacher/grade/${id}`, null, {
                params: { score, comment }
            });
            alert('评分成功');
            loadSubmissions();
        } catch (error) {
            console.error('评分失败:', error);
            alert('评分失败');
        }
    };

    return (
        <div className="teacher-portal">
            {/* 头部导航已在 App.js 中处理，这里只显示对应的内容 */}

            {/* 内容区域 */}
            <div className="portal-content">
                {activeTab === 'experiments' && (
                    <ExperimentManager
                        experiments={experiments}
                        loading={loading}
                        onEdit={setEditingExperiment}
                        onDelete={handleDeleteExperiment}
                        onCreate={() => setEditingExperiment({})}
                    />
                )}

                {activeTab === 'submissions' && (
                    <SubmissionReview
                        submissions={submissions}
                        loading={loading}
                        onGrade={handleGradeSubmission}
                    />
                )}

                {activeTab === 'statistics' && (
                    <Dashboard statistics={statistics} loading={loading} />
                )}
            </div>

            {editingExperiment && (
                <ExperimentEditorModal
                    experiment={editingExperiment}
                    onClose={() => setEditingExperiment(null)}
                    onSave={handleSaveExperiment}
                />
            )}
        </div>
    );
}

// ==================== 实验管理组件 ====================

function ExperimentManager({ experiments, loading, onEdit, onDelete, onCreate }) {
    if (loading) return <div className="loading">加载中...</div>;

    return (
        <div className="experiment-manager">
            <div className="section-header" style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
                <h2>实验管理</h2>
                <button className="btn btn-primary" onClick={onCreate}>
                    + 发布新实验
                </button>
            </div>

            <div className="experiments-table">
                <table>
                    <thead>
                        <tr>
                            <th>标题</th>
                            <th>难度</th>
                            <th>标签</th>
                            <th>资源配置</th>
                            <th>创建时间</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        {experiments.map(exp => (
                            <tr key={exp.id}>
                                <td>{exp.title}</td>
                                <td>
                                    <span className={`difficulty-badge ${exp.difficulty}`}>
                                        {exp.difficulty}
                                    </span>
                                </td>
                                <td>{exp.tags.join(', ')}</td>
                                <td>{exp.resources.cpu}核 / {exp.resources.memory}</td>
                                <td>{new Date(exp.created_at).toLocaleDateString()}</td>
                                <td>
                                    <div className="action-buttons" style={{ display: 'flex', gap: '8px' }}>
                                        <button className="btn btn-small btn-secondary" onClick={() => onEdit(exp)}>
                                            编辑
                                        </button>
                                        <button className="btn btn-small btn-danger"
                                            style={{ backgroundColor: 'var(--error-color)', color: 'white' }}
                                            onClick={() => onDelete(exp.id)}>
                                            删除
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                        {experiments.length === 0 && (
                            <tr>
                                <td colSpan="6" style={{ textAlign: 'center', padding: '2rem' }}>
                                    暂无实验，请点击右上角发布新实验
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

// ==================== 提交审阅组件 ====================

function SubmissionReview({ submissions, loading, onGrade }) {
    const [selectedSubmission, setSelectedSubmission] = useState(null);

    if (loading) return <div className="loading">加载中...</div>;

    return (
        <div className="submission-review">
            <h2>提交审阅</h2>

            <div className="experiments-table">
                <table>
                    <thead>
                        <tr>
                            <th>实验ID</th>
                            <th>学生ID</th>
                            <th>状态</th>
                            <th>提交时间</th>
                            <th>分数</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        {submissions.map(sub => (
                            <tr key={sub.id}>
                                <td>{sub.experiment_id}</td>
                                <td>{sub.student_id}</td>
                                <td>{sub.status}</td>
                                <td>{sub.submit_time ? new Date(sub.submit_time).toLocaleString() : '-'}</td>
                                <td>{sub.score !== null ? sub.score : '-'}</td>
                                <td>
                                    {sub.status === '已提交' || sub.status === '已评分' ? (
                                        <button
                                            className="btn btn-small"
                                            onClick={() => setSelectedSubmission(sub)}
                                        >
                                            {sub.status === '已评分' ? '重新评分' : '评分'}
                                        </button>
                                    ) : '-'}
                                </td>
                            </tr>
                        ))}
                        {submissions.length === 0 && (
                            <tr>
                                <td colSpan="6" style={{ textAlign: 'center', padding: '2rem' }}>
                                    暂无提交记录
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {selectedSubmission && (
                <GradingModal
                    submission={selectedSubmission}
                    onClose={() => setSelectedSubmission(null)}
                    onGrade={onGrade}
                />
            )}
        </div>
    );
}

// ==================== 仪表板组件 ====================

function Dashboard({ statistics, loading }) {
    if (loading || !statistics) return <div className="loading">加载统计数据...</div>;

    return (
        <div className="dashboard">
            <h2>数据统计概览</h2>

            <div className="stats-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '20px', marginBottom: '30px' }}>
                <div className="stat-card" style={{ padding: '20px', background: 'var(--bg-card)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-color)' }}>
                    <h3>总实验数</h3>
                    <p style={{ fontSize: '2.5rem', fontWeight: 'bold', color: 'var(--primary-color)' }}>
                        {statistics.total_experiments}
                    </p>
                </div>
                <div className="stat-card" style={{ padding: '20px', background: 'var(--bg-card)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-color)' }}>
                    <h3>总提交数</h3>
                    <p style={{ fontSize: '2.5rem', fontWeight: 'bold', color: 'var(--success-color)' }}>
                        {statistics.total_submissions}
                    </p>
                </div>
            </div>

            <div className="chart-container" style={{ padding: '20px', background: 'var(--bg-card)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-color)' }}>
                <h3>提交状态分布</h3>
                <div className="status-bars" style={{ marginTop: '20px' }}>
                    {Object.entries(statistics.status_distribution).map(([status, count]) => (
                        <div key={status} className="status-bar-item" style={{ marginBottom: '15px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
                                <span>{status}</span>
                                <span>{count}</span>
                            </div>
                            <div style={{ height: '10px', background: 'var(--bg-secondary)', borderRadius: '5px', overflow: 'hidden' }}>
                                <div style={{
                                    height: '100%',
                                    width: `${(count / statistics.total_submissions) * 100}%`,
                                    background: 'var(--primary-gradient)'
                                }}></div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

// ==================== 实验编辑弹窗 ====================

function ExperimentEditorModal({ experiment, onClose, onSave }) {
    const [formData, setFormData] = useState({
        title: '',
        description: '',
        difficulty: '初级',
        tags: '',
        notebook_path: 'notebooks/template.ipynb',
        resources: { cpu: 1.0, memory: '2G', storage: '1G' },
        ...experiment
    });

    // 如果tags是数组，转换为字符串
    useEffect(() => {
        if (Array.isArray(formData.tags)) {
            setFormData(prev => ({ ...prev, tags: prev.tags.join(', ') }));
        }
    }, []);

    const handleSubmit = (e) => {
        e.preventDefault();
        onSave({
            ...formData,
            tags: formData.tags.split(',').map(t => t.trim()).filter(Boolean)
        });
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h2>{experiment.id ? '编辑实验' : '发布新实验'}</h2>
                    <button className="close-btn" onClick={onClose}>×</button>
                </div>

                <form onSubmit={handleSubmit}>
                    <div className="modal-body">
                        <div className="form-group">
                            <label>实验标题</label>
                            <input
                                type="text"
                                value={formData.title}
                                onChange={e => setFormData({ ...formData, title: e.target.value })}
                                required
                            />
                        </div>

                        <div className="form-group">
                            <label>描述</label>
                            <textarea
                                value={formData.description}
                                onChange={e => setFormData({ ...formData, description: e.target.value })}
                                style={{
                                    width: '100%',
                                    padding: '10px',
                                    background: 'var(--bg-primary)',
                                    border: '1px solid var(--border-color)',
                                    color: 'var(--text-primary)',
                                    borderRadius: 'var(--radius-md)',
                                    minHeight: '100px'
                                }}
                                required
                            />
                        </div>

                        <div className="form-group" style={{ display: 'flex', gap: '20px' }}>
                            <div style={{ flex: 1 }}>
                                <label>难度</label>
                                <select
                                    value={formData.difficulty}
                                    onChange={e => setFormData({ ...formData, difficulty: e.target.value })}
                                    style={{ width: '100%', padding: '10px', background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }}
                                >
                                    <option value="初级">初级</option>
                                    <option value="中级">中级</option>
                                    <option value="高级">高级</option>
                                </select>
                            </div>
                            <div style={{ flex: 2 }}>
                                <label>标签 (逗号分隔)</label>
                                <input
                                    type="text"
                                    value={formData.tags}
                                    onChange={e => setFormData({ ...formData, tags: e.target.value })}
                                />
                            </div>
                        </div>

                        <div className="form-group">
                            <label>Notebook 路径</label>
                            <input
                                type="text"
                                value={formData.notebook_path}
                                onChange={e => setFormData({ ...formData, notebook_path: e.target.value })}
                            />
                        </div>
                    </div>

                    <div className="modal-footer">
                        <button type="button" className="btn btn-secondary" onClick={onClose}>取消</button>
                        <button type="submit" className="btn btn-primary">保存</button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// ==================== 评分弹窗 ====================

function GradingModal({ submission, onClose, onGrade }) {
    const [score, setScore] = useState(submission.score || 80);
    const [comment, setComment] = useState(submission.teacher_comment || '');

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '500px' }}>
                <div className="modal-header">
                    <h2>作业评分</h2>
                    <button className="close-btn" onClick={onClose}>×</button>
                </div>

                <div className="modal-body">
                    <div style={{ marginBottom: '20px', padding: '15px', background: 'var(--bg-primary)', borderRadius: 'var(--radius-md)' }}>
                        <p><strong>实验ID:</strong> {submission.experiment_id}</p>
                        <p><strong>学生ID:</strong> {submission.student_id}</p>
                        <p><strong>提交内容:</strong></p>
                        <pre style={{ maxHeight: '150px', overflow: 'auto', fontSize: '0.85rem', marginTop: '5px' }}>
                            {submission.notebook_content || '（内容略）'}
                        </pre>
                    </div>

                    <div className="form-group">
                        <label>分数 (0-100)</label>
                        <input
                            type="number"
                            min="0" max="100"
                            value={score}
                            onChange={e => setScore(Number(e.target.value))}
                        />
                    </div>

                    <div className="form-group">
                        <label>评语</label>
                        <textarea
                            value={comment}
                            onChange={e => setComment(e.target.value)}
                            placeholder="请输入评语..."
                            style={{
                                width: '100%',
                                padding: '10px',
                                background: 'var(--bg-primary)',
                                border: '1px solid var(--border-color)',
                                color: 'var(--text-primary)',
                                borderRadius: 'var(--radius-md)',
                                minHeight: '80px'
                            }}
                        />
                    </div>
                </div>

                <div className="modal-footer">
                    <button className="btn btn-secondary" onClick={onClose}>取消</button>
                    <button className="btn btn-primary" onClick={() => {
                        onGrade(submission.id, score, comment);
                        onClose();
                    }}>提交评分</button>
                </div>
            </div>
        </div>
    );
}

export default TeacherPortal;
