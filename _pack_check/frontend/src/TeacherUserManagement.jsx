import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import './TeacherUserManagement.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

function formatDateTime(value) {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleString();
}

function TeacherUserManagement({ username, userRole }) {
    const isAdmin = userRole === 'admin';
    const [activePanel, setActivePanel] = useState(isAdmin ? 'teachers' : 'students');

    const [classes, setClasses] = useState([]);
    const [students, setStudents] = useState([]);
    const [admissionYearOptions, setAdmissionYearOptions] = useState([]);
    const [keyword, setKeyword] = useState('');
    const [classFilter, setClassFilter] = useState('');
    const [admissionYearFilter, setAdmissionYearFilter] = useState('');
    const [page, setPage] = useState(1);
    const [pageSize] = useState(20);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);

    const [teachers, setTeachers] = useState([]);
    const [teacherKeyword, setTeacherKeyword] = useState('');
    const [loadingTeachers, setLoadingTeachers] = useState(false);

    const [showClassModal, setShowClassModal] = useState(false);
    const [newClassName, setNewClassName] = useState('');
    const [selectedClassFile, setSelectedClassFile] = useState(null);
    const [classImportResult, setClassImportResult] = useState(null);

    const [showImportModal, setShowImportModal] = useState(false);
    const [selectedFile, setSelectedFile] = useState(null);
    const [importResult, setImportResult] = useState(null);

    const [showTeacherModal, setShowTeacherModal] = useState(false);
    const [newTeacherUsername, setNewTeacherUsername] = useState('');
    const [newTeacherRealName, setNewTeacherRealName] = useState('');

    const totalPages = useMemo(() => Math.max(1, Math.ceil(total / pageSize)), [total, pageSize]);

    const loadClasses = useCallback(async () => {
        try {
            const res = await axios.get(`${API_BASE_URL}/api/admin/classes`, {
                params: { teacher_username: username }
            });
            setClasses(res.data || []);
        } catch (error) {
            alert(error.response?.data?.detail || '加载班级失败');
        }
    }, [username]);

    const loadAdmissionYears = useCallback(async () => {
        try {
            const res = await axios.get(`${API_BASE_URL}/api/admin/students/admission-years`, {
                params: { teacher_username: username }
            });
            setAdmissionYearOptions(res.data || []);
        } catch (error) {
            setAdmissionYearOptions([]);
        }
    }, [username]);

    const loadStudents = useCallback(async ({ targetPage = 1, targetKeyword = '', targetClass = '', targetAdmissionYear = '' } = {}) => {
        setLoading(true);
        try {
            const res = await axios.get(`${API_BASE_URL}/api/admin/students`, {
                params: {
                    teacher_username: username,
                    keyword: targetKeyword,
                    class_name: targetClass,
                    admission_year: targetAdmissionYear,
                    page: targetPage,
                    page_size: pageSize
                }
            });
            setStudents(res.data.items || []);
            setTotal(res.data.total || 0);
            setPage(res.data.page || targetPage);
        } catch (error) {
            alert(error.response?.data?.detail || '加载学生失败');
        } finally {
            setLoading(false);
        }
    }, [pageSize, username]);

    const loadTeachers = useCallback(async () => {
        if (!isAdmin) return;
        setLoadingTeachers(true);
        try {
            const res = await axios.get(`${API_BASE_URL}/api/admin/teachers`, {
                params: { admin_username: username }
            });
            setTeachers(Array.isArray(res.data) ? res.data : []);
        } catch (error) {
            alert(error.response?.data?.detail || '加载教师失败');
            setTeachers([]);
        } finally {
            setLoadingTeachers(false);
        }
    }, [isAdmin, username]);

    useEffect(() => {
        loadClasses();
        loadAdmissionYears();
        loadStudents();
    }, [loadClasses, loadAdmissionYears, loadStudents]);

    useEffect(() => {
        if (isAdmin) {
            loadTeachers();
        } else {
            setActivePanel('students');
        }
    }, [isAdmin, loadTeachers]);

    const filteredTeachers = useMemo(() => {
        const kw = teacherKeyword.trim().toLowerCase();
        if (!kw) return teachers;
        return teachers.filter((item) => {
            const account = String(item.username || '').toLowerCase();
            const realName = String(item.real_name || '').toLowerCase();
            return account.includes(kw) || realName.includes(kw);
        });
    }, [teacherKeyword, teachers]);

    const handleSearch = () => loadStudents({
        targetPage: 1,
        targetKeyword: keyword,
        targetClass: classFilter,
        targetAdmissionYear: admissionYearFilter,
    });

    const handleResetSearch = () => {
        setKeyword('');
        setClassFilter('');
        setAdmissionYearFilter('');
        loadStudents();
    };

    const handleDownloadTemplate = async (format) => {
        try {
            const res = await axios.get(`${API_BASE_URL}/api/admin/students/template`, {
                params: { teacher_username: username, format },
                responseType: 'blob'
            });
            const blob = new Blob([res.data]);
            const url = window.URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = url;
            anchor.download = `student_import_template.${format}`;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            alert(error.response?.data?.detail || '下载模板失败');
        }
    };

    const handleDownloadClassTemplate = async (format) => {
        try {
            const res = await axios.get(`${API_BASE_URL}/api/admin/classes/template`, {
                params: { teacher_username: username, format },
                responseType: 'blob'
            });
            const blob = new Blob([res.data]);
            const url = window.URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = url;
            anchor.download = `class_import_template.${format}`;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            alert(error.response?.data?.detail || '下载班级模板失败');
        }
    };

    const handleCreateClass = async () => {
        const name = newClassName.trim();
        if (!name) {
            alert('请输入班级名称');
            return;
        }
        try {
            await axios.post(`${API_BASE_URL}/api/admin/classes`, { name, teacher_username: username });
            setNewClassName('');
            await loadClasses();
            alert('班级创建成功');
        } catch (error) {
            alert(error.response?.data?.detail || '创建班级失败');
        }
    };

    const handleDeleteClass = async (classId, className) => {
        if (!window.confirm(`确定删除班级 ${className} 吗？`)) return;
        try {
            await axios.delete(`${API_BASE_URL}/api/admin/classes/${classId}`, {
                params: { teacher_username: username }
            });
            await loadClasses();
            alert('班级删除成功');
        } catch (error) {
            alert(error.response?.data?.detail || '删除班级失败');
        }
    };

    const handleImportClasses = async () => {
        if (!selectedClassFile) {
            alert('请选择班级导入文件');
            return;
        }
        const formData = new FormData();
        formData.append('file', selectedClassFile);
        try {
            const res = await axios.post(`${API_BASE_URL}/api/admin/classes/import`, formData, {
                params: { teacher_username: username },
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            setClassImportResult(res.data);
            await loadClasses();
            await loadStudents({
                targetPage: 1,
                targetKeyword: keyword,
                targetClass: classFilter,
                targetAdmissionYear: admissionYearFilter,
            });
        } catch (error) {
            alert(error.response?.data?.detail || '班级导入失败');
        }
    };

    const handleImportStudents = async () => {
        if (!selectedFile) {
            alert('请选择要上传的文件');
            return;
        }
        const formData = new FormData();
        formData.append('file', selectedFile);
        try {
            const res = await axios.post(`${API_BASE_URL}/api/admin/students/import`, formData, {
                params: { teacher_username: username },
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            setImportResult(res.data);
            await loadStudents({
                targetPage: 1,
                targetKeyword: keyword,
                targetClass: classFilter,
                targetAdmissionYear: admissionYearFilter,
            });
            await loadClasses();
            await loadAdmissionYears();
        } catch (error) {
            alert(error.response?.data?.detail || '导入失败');
        }
    };

    const handleResetPassword = async (studentId) => {
        if (!window.confirm(`确认将 ${studentId} 的密码重置为 123456 吗？`)) return;
        try {
            await axios.post(`${API_BASE_URL}/api/admin/students/${studentId}/reset-password`, null, {
                params: { teacher_username: username }
            });
            alert('密码重置成功');
        } catch (error) {
            alert(error.response?.data?.detail || '重置密码失败');
        }
    };

    const handleDeleteStudent = async (studentId) => {
        if (!window.confirm(`确定删除学生 ${studentId} 吗？`)) return;
        try {
            await axios.delete(`${API_BASE_URL}/api/admin/students/${studentId}`, {
                params: { teacher_username: username }
            });
            await loadStudents({
                targetPage: page,
                targetKeyword: keyword,
                targetClass: classFilter,
                targetAdmissionYear: admissionYearFilter,
            });
            alert('删除学生成功');
        } catch (error) {
            alert(error.response?.data?.detail || '删除学生失败');
        }
    };

    const handleBatchDeleteStudentsByClass = async () => {
        if (!classFilter) {
            alert('请先选择班级');
            return;
        }
        if (!window.confirm(`确定批量删除班级 ${classFilter} 的全部学生吗？此操作不可恢复。`)) return;
        try {
            const res = await axios.delete(`${API_BASE_URL}/api/admin/students`, {
                params: {
                    teacher_username: username,
                    class_name: classFilter,
                }
            });
            await loadStudents({
                targetPage: 1,
                targetKeyword: keyword,
                targetClass: classFilter,
                targetAdmissionYear: admissionYearFilter,
            });
            await loadAdmissionYears();
            alert(`批量删除完成，已删除 ${res.data?.deleted_count ?? 0} 名学生`);
        } catch (error) {
            alert(error.response?.data?.detail || '批量删除学生失败');
        }
    };

    const handleCreateTeacher = async () => {
        const teacherUsername = newTeacherUsername.trim();
        const teacherRealName = newTeacherRealName.trim();
        if (!teacherUsername) {
            alert('请输入教师账号');
            return;
        }
        try {
            await axios.post(`${API_BASE_URL}/api/admin/teachers`, {
                admin_username: username,
                username: teacherUsername,
                real_name: teacherRealName,
            });
            setNewTeacherUsername('');
            setNewTeacherRealName('');
            setShowTeacherModal(false);
            await loadTeachers();
            alert('教师账号创建成功，初始密码为 123456');
        } catch (error) {
            alert(error.response?.data?.detail || '创建教师失败');
        }
    };

    const handleDeleteTeacher = async (teacherUsername) => {
        if (!window.confirm(`确定删除教师账号 ${teacherUsername} 吗？`)) return;
        try {
            await axios.delete(`${API_BASE_URL}/api/admin/teachers/${encodeURIComponent(teacherUsername)}`, {
                params: { admin_username: username }
            });
            await loadTeachers();
            alert('教师账号删除成功');
        } catch (error) {
            alert(error.response?.data?.detail || '删除教师失败');
        }
    };

    return (
        <div className="user-management">
            {isAdmin ? (
                <div className="user-role-switch">
                    <button
                        type="button"
                        className={activePanel === 'teachers' ? 'active' : ''}
                        onClick={() => setActivePanel('teachers')}
                    >
                        教师管理
                    </button>
                    <button
                        type="button"
                        className={activePanel === 'students' ? 'active' : ''}
                        onClick={() => setActivePanel('students')}
                    >
                        学生管理
                    </button>
                </div>
            ) : null}

            {activePanel === 'teachers' ? (
                <>
                    <div className="user-management-toolbar">
                        <h2>教师账号管理</h2>
                        <div className="user-management-actions">
                            <button onClick={loadTeachers}>刷新</button>
                            <button onClick={() => {
                                setNewTeacherUsername('');
                                setNewTeacherRealName('');
                                setShowTeacherModal(true);
                            }}>新增教师</button>
                        </div>
                    </div>

                    <div className="user-filters">
                        <input
                            type="text"
                            placeholder="搜索教师账号或姓名"
                            value={teacherKeyword}
                            onChange={(event) => setTeacherKeyword(event.target.value)}
                        />
                    </div>

                    <div className="user-table-wrap">
                        {loadingTeachers ? (
                            <div className="user-placeholder">加载中...</div>
                        ) : filteredTeachers.length === 0 ? (
                            <div className="user-placeholder">暂无教师数据</div>
                        ) : (
                            <table className="user-table">
                                <thead>
                                    <tr>
                                        <th>教师账号</th>
                                        <th>姓名</th>
                                        <th>来源</th>
                                        <th>创建人</th>
                                        <th>创建时间</th>
                                        <th>操作</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredTeachers.map((item) => (
                                        <tr key={item.username}>
                                            <td>{item.username}</td>
                                            <td>{item.real_name || '-'}</td>
                                            <td>{item.source === 'registry' ? '平台添加' : '环境变量'}</td>
                                            <td>{item.created_by || '-'}</td>
                                            <td>{formatDateTime(item.created_at)}</td>
                                            <td>
                                                {item.source === 'registry' ? (
                                                    <button
                                                        className="danger-btn"
                                                        onClick={() => handleDeleteTeacher(item.username)}
                                                    >
                                                        删除
                                                    </button>
                                                ) : (
                                                    <span className="user-static-tag">内置账号</span>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                </>
            ) : null}

            {activePanel === 'students' ? (
                <>
                    <div className="user-management-toolbar">
                        <h2>用户信息查看</h2>
                        <div className="user-management-actions">
                            <button onClick={() => handleDownloadTemplate('xlsx')}>下载模板(xlsx)</button>
                            <button onClick={() => handleDownloadTemplate('csv')}>下载模板(csv)</button>
                            <button onClick={() => {
                                setImportResult(null);
                                setSelectedFile(null);
                                setShowImportModal(true);
                            }}>学生信息导入</button>
                            <button onClick={() => {
                                setSelectedClassFile(null);
                                setClassImportResult(null);
                                setShowClassModal(true);
                            }}>班级管理</button>
                        </div>
                    </div>

                    <div className="user-filters">
                        <input
                            type="text"
                            placeholder="请输入学号或姓名"
                            value={keyword}
                            onChange={(e) => setKeyword(e.target.value)}
                        />
                        <select value={classFilter} onChange={(e) => setClassFilter(e.target.value)}>
                            <option value="">全部班级</option>
                            {classes.map((item) => (
                                <option key={item.id} value={item.name}>{item.name}</option>
                            ))}
                        </select>
                        <select value={admissionYearFilter} onChange={(e) => setAdmissionYearFilter(e.target.value)}>
                            <option value="">全部入学年级</option>
                            {admissionYearOptions.map((item) => (
                                <option key={item.value} value={item.value}>{item.label}</option>
                            ))}
                        </select>
                        <button onClick={handleSearch}>搜索</button>
                        <button onClick={handleResetSearch}>重置</button>
                        <button
                            className="danger-btn"
                            onClick={handleBatchDeleteStudentsByClass}
                            disabled={!classFilter || loading}
                            title={classFilter ? `删除班级 ${classFilter} 下全部学生` : '请先选择班级'}
                        >
                            按班级批量删除
                        </button>
                    </div>

                    <div className="user-table-wrap">
                        {loading ? (
                            <div className="user-placeholder">加载中...</div>
                        ) : students.length === 0 ? (
                            <div className="user-placeholder">暂无学生数据</div>
                        ) : (
                            <table className="user-table">
                                <thead>
                                    <tr>
                                        <th>用户名</th>
                                        <th>学号</th>
                                        <th>单位名称</th>
                                        <th>真实姓名</th>
                                        <th>入学年级</th>
                                        <th>所属班级</th>
                                        <th>用户类型</th>
                                        <th>操作</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {students.map((item) => (
                                        <tr key={item.student_id}>
                                            <td>{item.username}</td>
                                            <td>{item.student_id}</td>
                                            <td>{item.organization}</td>
                                            <td>{item.real_name}</td>
                                            <td>{item.admission_year_label || (item.admission_year ? `${item.admission_year}级` : '-')}</td>
                                            <td>{item.class_name}</td>
                                            <td>{item.role}</td>
                                            <td>
                                                <button onClick={() => handleResetPassword(item.student_id)}>重置密码</button>
                                                <button className="danger-btn" onClick={() => handleDeleteStudent(item.student_id)}>删除</button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>

                    <div className="user-pagination">
                        <span>共 {total} 条</span>
                        <button
                            disabled={page <= 1}
                            onClick={() => loadStudents({
                                targetPage: page - 1,
                                targetKeyword: keyword,
                                targetClass: classFilter,
                                targetAdmissionYear: admissionYearFilter,
                            })}
                        >
                            上一页
                        </button>
                        <span>{page} / {totalPages}</span>
                        <button
                            disabled={page >= totalPages}
                            onClick={() => loadStudents({
                                targetPage: page + 1,
                                targetKeyword: keyword,
                                targetClass: classFilter,
                                targetAdmissionYear: admissionYearFilter,
                            })}
                        >
                            下一页
                        </button>
                    </div>
                </>
            ) : null}
            {showClassModal && (
                <div className="user-modal-overlay" onClick={() => setShowClassModal(false)}>
                    <div className="user-modal" onClick={(e) => e.stopPropagation()}>
                        <h3>班级管理</h3>
                        <div className="class-create-row">
                            <input
                                type="text"
                                placeholder="输入班级名称"
                                value={newClassName}
                                onChange={(e) => setNewClassName(e.target.value)}
                            />
                            <button onClick={handleCreateClass}>新增班级</button>
                        </div>
                        <div className="class-import-panel">
                            <div className="class-import-header">
                                <span>批量导入格式：入学年级 / 专业 / 班级</span>
                                <div className="class-import-template-actions">
                                    <button onClick={() => handleDownloadClassTemplate('xlsx')}>下载班级模板(xlsx)</button>
                                    <button onClick={() => handleDownloadClassTemplate('csv')}>下载班级模板(csv)</button>
                                </div>
                            </div>
                            <div className="class-import-input-row">
                                <input type="file" accept=".xlsx,.csv" onChange={(e) => setSelectedClassFile(e.target.files?.[0] || null)} />
                                <button onClick={handleImportClasses}>上传并导入班级</button>
                            </div>
                            <div className="import-file-name">
                                {selectedClassFile ? `已选择: ${selectedClassFile.name}` : '未选择班级导入文件'}
                            </div>
                            {classImportResult && (
                                <div className="import-result">
                                    <p>总行数: {classImportResult.total_rows}</p>
                                    <p>成功: {classImportResult.success_count}</p>
                                    <p>跳过: {classImportResult.skipped_count}</p>
                                    <p>失败: {classImportResult.failed_count}</p>
                                </div>
                            )}
                        </div>
                        <div className="class-list">
                            {classes.length === 0 ? (
                                <div className="user-placeholder">暂无班级</div>
                            ) : (
                                <table className="user-table">
                                    <thead>
                                        <tr>
                                            <th>班级名称</th>
                                            <th>创建人</th>
                                            <th>创建时间</th>
                                            <th>操作</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {classes.map((item) => (
                                            <tr key={item.id}>
                                                <td>{item.name}</td>
                                                <td>{item.created_by}</td>
                                                <td>{new Date(item.created_at).toLocaleString()}</td>
                                                <td>
                                                    <button className="danger-btn" onClick={() => handleDeleteClass(item.id, item.name)}>删除</button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>
                        <div className="user-modal-actions">
                            <button onClick={() => setShowClassModal(false)}>关闭</button>
                        </div>
                    </div>
                </div>
            )}

            {showImportModal && (
                <div className="user-modal-overlay" onClick={() => setShowImportModal(false)}>
                    <div className="user-modal" onClick={(e) => e.stopPropagation()}>
                        <h3>学生信息导入</h3>
                        <input type="file" accept=".xlsx,.csv" onChange={(e) => setSelectedFile(e.target.files?.[0] || null)} />
                        <div className="import-file-name">
                            {selectedFile ? `已选择: ${selectedFile.name}` : '未选择文件'}
                        </div>
                        <div className="user-modal-actions">
                            <button onClick={() => setShowImportModal(false)}>取消</button>
                            <button onClick={handleImportStudents}>上传并导入</button>
                        </div>
                        {importResult && (
                            <div className="import-result">
                                <p>总行数: {importResult.total_rows}</p>
                                <p>成功: {importResult.success_count}</p>
                                <p>跳过: {importResult.skipped_count}</p>
                                <p>失败: {importResult.failed_count}</p>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {showTeacherModal && (
                <div className="user-modal-overlay" onClick={() => setShowTeacherModal(false)}>
                    <div className="user-modal teacher-modal" onClick={(event) => event.stopPropagation()}>
                        <h3>新增教师账号</h3>
                        <div className="class-create-row">
                            <input
                                type="text"
                                placeholder="教师账号，如 teacher_006"
                                value={newTeacherUsername}
                                onChange={(event) => setNewTeacherUsername(event.target.value)}
                            />
                        </div>
                        <div className="class-create-row">
                            <input
                                type="text"
                                placeholder="教师姓名（可选）"
                                value={newTeacherRealName}
                                onChange={(event) => setNewTeacherRealName(event.target.value)}
                            />
                        </div>
                        <div className="user-modal-actions">
                            <button onClick={() => setShowTeacherModal(false)}>取消</button>
                            <button onClick={handleCreateTeacher}>创建</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default TeacherUserManagement;
