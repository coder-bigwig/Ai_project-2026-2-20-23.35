import React, { useEffect, useState } from 'react';
import './StudentPortal.css'; // Reusing styles for table and badges

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

function asNotebookText(value) {
    if (Array.isArray(value)) return value.join('');
    return value === undefined || value === null ? '' : String(value);
}

function renderNotebookOutputData(data, keyPrefix) {
    if (!data || typeof data !== 'object') return null;

    const imagePng = asNotebookText(data['image/png']).trim();
    if (imagePng) {
        return (
            <img
                key={`${keyPrefix}-img-png`}
                src={`data:image/png;base64,${imagePng}`}
                alt="可视化输出"
                style={{ maxWidth: '100%', border: '1px solid #e0e6ed', borderRadius: '4px', background: '#fff' }}
            />
        );
    }

    const imageJpeg = asNotebookText(data['image/jpeg']).trim();
    if (imageJpeg) {
        return (
            <img
                key={`${keyPrefix}-img-jpeg`}
                src={`data:image/jpeg;base64,${imageJpeg}`}
                alt="可视化输出"
                style={{ maxWidth: '100%', border: '1px solid #e0e6ed', borderRadius: '4px', background: '#fff' }}
            />
        );
    }

    const html = asNotebookText(data['text/html']).trim();
    if (html) {
        const htmlDoc = `<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;padding:8px;color:#303133;font-family:Arial,\\5FAE\\8F6F\\96C5\\9ED1,sans-serif;}table{border-collapse:collapse;max-width:100%;}th,td{border:1px solid #e0e6ed;padding:4px 8px;}img{max-width:100%;height:auto;}</style></head><body>${html}</body></html>`;
        return (
            <iframe
                key={`${keyPrefix}-html`}
                title={`${keyPrefix}-html-output`}
                sandbox=""
                srcDoc={htmlDoc}
                style={{ width: '100%', minHeight: '120px', border: '1px solid #e0e6ed', borderRadius: '4px', background: '#fff' }}
            />
        );
    }

    const plain = asNotebookText(data['text/plain']);
    if (plain) {
        return (
            <pre key={`${keyPrefix}-plain`} style={{ margin: 0, fontFamily: 'monospace', fontSize: '0.9rem', color: '#444', whiteSpace: 'pre-wrap' }}>
                {plain}
            </pre>
        );
    }

    return null;
}

function getPdfStatusStyle(status) {
    if (status === '已批阅') {
        return { background: '#e1f3d8', color: '#67c23a' };
    }
    if (status === '已查看') {
        return { background: '#ecf5ff', color: '#409eff' };
    }
    return { background: '#fdf6ec', color: '#e6a23c' };
}

function getPdfSummary(pdfList) {
    if (!pdfList || pdfList.length === 0) {
        return '-';
    }
    const reviewed = pdfList.filter((item) => item.review_status === '已批阅').length;
    const viewed = pdfList.filter((item) => item.review_status === '已查看').length;
    const unseen = pdfList.filter((item) => item.review_status === '未查看').length;
    return `未查看${unseen} / 已查看${viewed} / 已批阅${reviewed}`;
}

function getPdfBadgeStatus(pdfList) {
    if (!pdfList || pdfList.length === 0) {
        return '未查看';
    }
    if (pdfList.some((item) => item.review_status === '已批阅')) {
        return '已批阅';
    }
    if (pdfList.some((item) => item.review_status === '已查看')) {
        return '已查看';
    }
    return '未查看';
}

function TeacherReview({ username, submissions, loading, onGrade }) {
    const [selectedSubmission, setSelectedSubmission] = useState(null);

    if (loading) return <div className="loading">加载中...</div>;

    return (
        <div className="submission-review">
            <div className="section-header">
                <h2>提交审阅</h2>
                <div className="refresh-btn-wrapper" style={{ float: 'right' }}>
                    {/* Optional: Add a refresh button here if needed */}
                </div>
            </div>

            <div className="experiments-table">
                <table>
                    <thead>
                        <tr>
                            <th>实验ID</th>
                            <th>学生ID</th>
                            <th>状态</th>
                            <th>提交时间</th>
                            <th>PDF</th>
                            <th>分数</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        {submissions.map(sub => {
                            const pdfAttachments = sub.pdf_attachments || [];
                            const badgeStatus = getPdfBadgeStatus(pdfAttachments);
                            const summaryText = getPdfSummary(pdfAttachments);
                            return (
                            <tr key={sub.id}>
                                <td>{sub.experiment_id}</td>
                                <td>{sub.student_id}</td>
                                <td>
                                    <span className={`status-badge ${sub.status === '已评分' ? 'success' : 'warning'}`}>
                                        {sub.status}
                                    </span>
                                </td>
                                <td>{sub.submit_time ? new Date(sub.submit_time).toLocaleString() : '-'}</td>
                                <td>
                                    {pdfAttachments.length > 0 ? (
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                            <span
                                                style={{
                                                    display: 'inline-block',
                                                    width: 'fit-content',
                                                    padding: '2px 8px',
                                                    borderRadius: '12px',
                                                    fontSize: '12px',
                                                    ...getPdfStatusStyle(badgeStatus)
                                                }}
                                            >
                                                {summaryText}
                                            </span>
                                            <a
                                                href={`${API_BASE_URL}/api/student-submissions/${pdfAttachments[0].id}/download?teacher_username=${encodeURIComponent(username)}`}
                                                target="_blank"
                                                rel="noreferrer"
                                            >
                                                查看PDF ({pdfAttachments.length})
                                            </a>
                                        </div>
                                    ) : '-'}
                                </td>
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
                        );})}
                        {submissions.length === 0 && (
                            <tr>
                                <td colSpan="7" style={{ textAlign: 'center', padding: '2rem' }}>
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
                    username={username}
                />
            )}
        </div>
    );
}

function GradingModal({ submission, onClose, onGrade, username }) {
    const [score, setScore] = useState(submission.score || 80);
    const [comment, setComment] = useState(submission.teacher_comment || '');
    const [pdfList, setPdfList] = useState(submission.pdf_attachments || []);
    const [selectedPdfId, setSelectedPdfId] = useState(
        submission.pdf_attachments && submission.pdf_attachments.length > 0
            ? submission.pdf_attachments[0].id
            : null
    );
    const [annotationText, setAnnotationText] = useState('');
    const [annotationSaving, setAnnotationSaving] = useState(false);

    const selectedPdf = pdfList.find((item) => item.id === selectedPdfId) || null;
    const selectedPdfUrl = selectedPdfId
        ? `${API_BASE_URL}/api/student-submissions/${selectedPdfId}/download?teacher_username=${encodeURIComponent(username)}`
        : null;

    const replacePdfItem = (updatedItem) => {
        setPdfList((prev) => prev.map((item) => (item.id === updatedItem.id ? updatedItem : item)));
    };

    const markPdfViewed = async (pdfId) => {
        if (!pdfId || !username) {
            return;
        }
        try {
            const res = await fetch(
                `${API_BASE_URL}/api/student-submissions/${pdfId}/view?teacher_username=${encodeURIComponent(username)}`,
                { method: 'POST' }
            );
            if (!res.ok) {
                return;
            }
            const updated = await res.json();
            replacePdfItem(updated);
        } catch (error) {
            console.error('标记PDF已查看失败:', error);
        }
    };

    useEffect(() => {
        if (selectedPdfId) {
            markPdfViewed(selectedPdfId);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedPdfId]);

    const handleSelectPdf = (pdfId) => {
        setSelectedPdfId(pdfId);
    };

    const handleAddAnnotation = async () => {
        const content = annotationText.trim();
        if (!selectedPdfId || !content) {
            alert('请先选择PDF并输入批注内容');
            return;
        }
        setAnnotationSaving(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/student-submissions/${selectedPdfId}/annotations`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    teacher_username: username,
                    content
                })
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || '保存批注失败');
            }
            replacePdfItem(data);
            setAnnotationText('');
        } catch (error) {
            alert(error.message || '保存批注失败');
        } finally {
            setAnnotationSaving(false);
        }
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '1000px', color: '#303133' }}>
                <div className="modal-header">
                    <h2>作业评分</h2>
                    <button className="close-btn" onClick={onClose}>×</button>
                </div>

                <div className="modal-body">
                    <div style={{ marginBottom: '20px', padding: '15px', background: '#f7f9fc', border: '1px solid #e5e9f2', borderRadius: '8px' }}>
                        <p><strong>实验ID:</strong> {submission.experiment_id}</p>
                        <p><strong>学生ID:</strong> {submission.student_id}</p>
                        <p><strong>PDF报告:</strong></p>
                        {pdfList.length > 0 ? (
                            <>
                                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', margin: '8px 0 12px 0' }}>
                                    {pdfList.map((item) => (
                                        <button
                                            key={item.id}
                                            type="button"
                                            onClick={() => handleSelectPdf(item.id)}
                                            style={{
                                                padding: '6px 10px',
                                                borderRadius: '6px',
                                                border: selectedPdfId === item.id ? '1px solid #409eff' : '1px solid #dcdfe6',
                                                background: selectedPdfId === item.id ? '#ecf5ff' : '#fff',
                                                color: '#303133',
                                                cursor: 'pointer'
                                            }}
                                        >
                                            {item.filename} ({item.review_status || '未查看'})
                                        </button>
                                    ))}
                                </div>
                                {selectedPdf && (
                                    <div style={{ marginBottom: '8px' }}>
                                        <span style={{
                                            display: 'inline-block',
                                            padding: '2px 8px',
                                            borderRadius: '12px',
                                            fontSize: '12px',
                                            ...getPdfStatusStyle(selectedPdf.review_status)
                                        }}>
                                            {selectedPdf.review_status}
                                        </span>
                                    </div>
                                )}
                                {selectedPdfUrl && (
                                    <div style={{ marginBottom: '14px', background: '#fff', border: '1px solid #dcdfe6', borderRadius: '6px' }}>
                                        <div style={{ padding: '8px 10px', borderBottom: '1px solid #ebeef5', display: 'flex', justifyContent: 'space-between' }}>
                                            <span style={{ fontSize: '13px', color: '#606266' }}>PDF预览</span>
                                            <a href={selectedPdfUrl} target="_blank" rel="noreferrer">新窗口打开</a>
                                        </div>
                                        <iframe
                                            title="submission-pdf-preview"
                                            src={selectedPdfUrl}
                                            style={{ width: '100%', height: '320px', border: 'none' }}
                                        />
                                    </div>
                                )}

                                <div style={{ marginBottom: '14px', background: '#fff', border: '1px solid #dcdfe6', borderRadius: '6px', padding: '10px' }}>
                                    <p style={{ marginBottom: '8px' }}><strong>PDF批注</strong></p>
                                    {selectedPdf && selectedPdf.annotations && selectedPdf.annotations.length > 0 ? (
                                        <ul style={{ margin: '0 0 10px 0', paddingLeft: '18px' }}>
                                            {selectedPdf.annotations.map((ann) => (
                                                <li key={ann.id} style={{ marginBottom: '6px' }}>
                                                    <span style={{ color: '#909399', marginRight: '6px' }}>
                                                        [{new Date(ann.created_at).toLocaleString()} {ann.teacher_username}]
                                                    </span>
                                                    <span>{ann.content}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    ) : (
                                        <p style={{ color: '#909399', margin: '0 0 10px 0' }}>暂无批注</p>
                                    )}
                                    <div style={{ display: 'flex', gap: '8px' }}>
                                        <input
                                            type="text"
                                            placeholder="输入批注内容..."
                                            value={annotationText}
                                            onChange={(e) => setAnnotationText(e.target.value)}
                                            style={{ flex: 1, padding: '8px 10px', border: '1px solid #dcdfe6', borderRadius: '6px' }}
                                        />
                                        <button
                                            type="button"
                                            onClick={handleAddAnnotation}
                                            disabled={annotationSaving || !selectedPdfId}
                                            style={{
                                                padding: '8px 12px',
                                                border: 'none',
                                                borderRadius: '6px',
                                                background: '#409eff',
                                                color: '#fff',
                                                cursor: 'pointer'
                                            }}
                                        >
                                            {annotationSaving ? '保存中...' : '添加批注'}
                                        </button>
                                    </div>
                                </div>
                            </>
                        ) : (
                            <p style={{ color: '#909399', marginBottom: '12px' }}>未上传PDF报告</p>
                        )}
                        <p><strong>提交内容:</strong></p>
                        <div
                            className="notebook-viewer"
                            style={{ maxHeight: '420px', overflow: 'auto', border: '1px solid #ddd', padding: '10px', background: '#fff' }}
                        >
                            <NotebookRenderer content={submission.notebook_content} />
                        </div>
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
                                background: '#fff',
                                border: '1px solid #dcdfe6',
                                color: '#303133',
                                borderRadius: '6px',
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

function NotebookRenderer({ content }) {
    if (!content) return <div style={{ color: '#909399' }}>无内容</div>;

    let notebook;
    try {
        // If content is already an object, use it; otherwise parse string
        notebook = typeof content === 'string' ? JSON.parse(content) : content;
    } catch (e) {
        // Fallback for non-JSON content (e.g. error messages or plain text)
        return <pre style={{ whiteSpace: 'pre-wrap', fontSize: '13px', color: '#303133' }}>{content}</pre>;
    }

    if (!notebook.cells || !Array.isArray(notebook.cells)) {
        return (
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: '13px', color: '#303133' }}>
                {typeof content === 'string' ? content : JSON.stringify(content, null, 2)}
            </pre>
        );
    }

    return (
        <div className="notebook-cells">
            {notebook.cells.map((cell, index) => (
                <div key={index} className="cell mb-4" style={{ marginBottom: '16px' }}>
                    {/* Input/Source */}
                    <div className="cell-input" style={{ background: '#f5f5f5', padding: '8px', borderRadius: '4px', border: '1px solid #e0e0e0' }}>
                        <div style={{ fontSize: '0.75rem', color: '#666', marginBottom: '4px', fontFamily: 'monospace' }}>
                            [{cell.cell_type === 'code' ? (cell.execution_count || ' ') : ''}]:
                        </div>
                        {cell.cell_type === 'markdown' ? (
                            // Simple markdown rendering (just joining lines)
                            <div className="markdown-body" style={{ padding: '4px' }}>
                                {Array.isArray(cell.source) ? cell.source.join('').split('\n').map((line, i) => (
                                    <p key={i} style={{ margin: '4px 0' }}>{line}</p>
                                )) : cell.source}
                            </div>
                        ) : (
                            <pre style={{ margin: 0, fontFamily: 'Consolas, monospace', fontSize: '0.9rem', color: '#333' }}>
                                {Array.isArray(cell.source) ? cell.source.join('') : cell.source}
                            </pre>
                        )}
                    </div>

                    {/* Outputs for code cells */}
                    {cell.cell_type === 'code' && cell.outputs && cell.outputs.length > 0 && (
                        <div className="cell-output" style={{ marginTop: '4px', paddingLeft: '8px' }}>
                            {cell.outputs.map((output, outIndex) => (
                                <div key={outIndex} style={{ marginBottom: '6px' }}>
                                    {output.output_type === 'stream' && (
                                        <pre style={{ margin: 0, fontFamily: 'monospace', fontSize: '0.9rem', color: '#444' }}>
                                            {asNotebookText(output.text)}
                                        </pre>
                                    )}
                                    {(output.output_type === 'execute_result' || output.output_type === 'display_data')
                                        ? renderNotebookOutputData(output.data, `cell-${index}-out-${outIndex}`)
                                        : null}
                                    {/* Handle error tracebacks */}
                                    {output.output_type === 'error' && (
                                        <pre style={{ margin: 0, fontFamily: 'monospace', fontSize: '0.9rem', color: '#d32f2f', whiteSpace: 'pre-wrap' }}>
                                            {Array.isArray(output.traceback) ? output.traceback.join('\n') : asNotebookText(output.traceback)}
                                        </pre>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
}

export default TeacherReview;
