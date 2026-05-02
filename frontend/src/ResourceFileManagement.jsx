import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import ResourcePreviewContent from './ResourcePreviewContent';
import './ResourceFileManagement.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

const FILE_TYPE_OPTIONS = [
    { value: '', label: '请选择类型' },
    { value: 'pdf', label: 'pdf' },
    { value: 'doc', label: 'doc' },
    { value: 'docx', label: 'docx' },
    { value: 'xls', label: 'xls' },
    { value: 'xlsx', label: 'xlsx' },
    { value: 'md', label: 'md' },
    { value: 'txt', label: 'txt' },
];

function formatDate(value) {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`;
}

function ResourceFileManagement({ username }) {
    const [resources, setResources] = useState([]);
    const [totalCount, setTotalCount] = useState(0);
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [searchName, setSearchName] = useState('');
    const [searchType, setSearchType] = useState('');
    const [detailVisible, setDetailVisible] = useState(false);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailData, setDetailData] = useState(null);
    const fileInputRef = useRef(null);

    const loadResources = useCallback(async ({ name = '', fileType = '' } = {}) => {
        setLoading(true);
        try {
            const response = await axios.get(`${API_BASE_URL}/api/admin/resources`, {
                params: {
                    teacher_username: username,
                    name: name || undefined,
                    file_type: fileType || undefined,
                },
            });
            const payload = response.data || {};
            setResources(Array.isArray(payload.items) ? payload.items : []);
            setTotalCount(Number.isFinite(payload.total) ? payload.total : 0);
        } catch (error) {
            console.error('Failed to load resources:', error);
            alert(error.response?.data?.detail || '加载资源文件失败');
            setResources([]);
            setTotalCount(0);
        } finally {
            setLoading(false);
        }
    }, [username]);

    useEffect(() => {
        loadResources({ name: '', fileType: '' });
    }, [loadResources]);

    const openUpload = () => {
        fileInputRef.current?.click();
    };

    const handleUploadChange = async (event) => {
        const file = event.target.files?.[0];
        event.target.value = '';
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);
        setUploading(true);
        try {
            await axios.post(`${API_BASE_URL}/api/admin/resources/upload`, formData, {
                params: { teacher_username: username },
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            await loadResources({ name: searchName, fileType: searchType });
            alert('资源文件上传成功');
        } catch (error) {
            console.error('Failed to upload resource:', error);
            alert(error.response?.data?.detail || '资源文件上传失败');
        } finally {
            setUploading(false);
        }
    };

    const handleSearch = () => {
        loadResources({ name: searchName, fileType: searchType });
    };

    const handleDelete = async (item) => {
        if (!window.confirm(`确定删除文件 "${item.filename}" 吗？`)) return;
        try {
            await axios.delete(`${API_BASE_URL}/api/admin/resources/${item.id}`, {
                params: { teacher_username: username },
            });
            if (detailData?.id === item.id) {
                setDetailVisible(false);
                setDetailData(null);
            }
            await loadResources({ name: searchName, fileType: searchType });
            alert('资源文件已删除');
        } catch (error) {
            console.error('Failed to delete resource:', error);
            alert(error.response?.data?.detail || '删除资源文件失败');
        }
    };

    const handleViewDetail = async (item) => {
        setDetailVisible(true);
        setDetailLoading(true);
        setDetailData(null);
        try {
            const response = await axios.get(`${API_BASE_URL}/api/admin/resources/${item.id}`, {
                params: { teacher_username: username },
            });
            setDetailData(response.data || null);
        } catch (error) {
            console.error('Failed to load resource detail:', error);
            alert(error.response?.data?.detail || '加载资源详情失败');
            setDetailVisible(false);
        } finally {
            setDetailLoading(false);
        }
    };

    const closeDetail = () => {
        setDetailVisible(false);
        setDetailData(null);
    };

    return (
        <div className="resource-file-management">
            <div className="resource-toolbar">
                <button className="resource-upload-btn" onClick={openUpload} disabled={uploading}>
                    {uploading ? '上传中...' : '上传资源文件'}
                </button>
                <input
                    ref={fileInputRef}
                    type="file"
                    className="resource-file-input"
                    accept=".pdf,.doc,.docx,.md,.markdown,.txt,.csv,.json,.ppt,.pptx,.xls,.xlsx"
                    onChange={handleUploadChange}
                />
                <div className="resource-search-group">
                    <input
                        type="text"
                        placeholder="请输入名称"
                        value={searchName}
                        onChange={(event) => setSearchName(event.target.value)}
                    />
                    <select
                        value={searchType}
                        onChange={(event) => setSearchType(event.target.value)}
                    >
                        {FILE_TYPE_OPTIONS.map((option) => (
                            <option key={option.value || 'all'} value={option.value}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                    <button className="resource-search-btn" onClick={handleSearch}>
                        搜索
                    </button>
                    <span className="resource-count">云平台资源文件共 {totalCount} 个</span>
                </div>
            </div>

            <div className="resource-table-wrap">
                <table className="resource-table">
                    <thead>
                        <tr>
                            <th>文件名</th>
                            <th>类型</th>
                            <th>创建时间</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr>
                                <td colSpan="4" className="resource-empty-row">加载中...</td>
                            </tr>
                        ) : resources.length === 0 ? (
                            <tr>
                                <td colSpan="4" className="resource-empty-row">暂无资源文件</td>
                            </tr>
                        ) : (
                            resources.map((item) => (
                                <tr key={item.id}>
                                    <td>{item.filename}</td>
                                    <td>{item.file_type || '-'}</td>
                                    <td>{formatDate(item.created_at)}</td>
                                    <td>
                                        <button className="resource-link-btn detail" onClick={() => handleViewDetail(item)}>
                                            详情
                                        </button>
                                        <button className="resource-link-btn delete" onClick={() => handleDelete(item)}>
                                            删除
                                        </button>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {detailVisible && (
                <div className="resource-modal-mask" onClick={closeDetail}>
                    <div className="resource-modal" onClick={(event) => event.stopPropagation()}>
                        <div className="resource-modal-header">
                            <h3>{detailData?.filename || '资源文件详情'}</h3>
                            <button onClick={closeDetail}>关闭</button>
                        </div>
                        <div className="resource-modal-body">
                            {detailLoading ? (
                                <div className="resource-preview-empty">详情加载中...</div>
                            ) : (
                                <ResourcePreviewContent
                                    detailData={detailData}
                                    accessQueryKey="teacher_username"
                                    accessQueryValue={username}
                                    loadingText="正在加载预览..."
                                    emptyText="暂无可预览内容"
                                    unsupportedText="当前文件类型不支持在线预览，请点击下载后查看。"
                                />
                            )}
                        </div>
                        {!detailLoading && detailData && (
                            <div className="resource-modal-footer">
                                <a
                                    href={`${API_BASE_URL}${detailData.download_url}?teacher_username=${encodeURIComponent(username)}`}
                                    target="_blank"
                                    rel="noreferrer"
                                >
                                    下载文件
                                </a>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

export default ResourceFileManagement;
