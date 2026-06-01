import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import ResourcePreviewContent from './ResourcePreviewContent';
import './ResourceFileManagement.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

const FILE_TYPE_OPTIONS = [
    { value: '', label: '全部类型' },
    { value: 'pdf', label: 'pdf' },
    { value: 'doc', label: 'doc' },
    { value: 'docx', label: 'docx' },
    { value: 'xls', label: 'xls' },
    { value: 'xlsx', label: 'xlsx' },
    { value: 'ppt', label: 'ppt' },
    { value: 'pptx', label: 'pptx' },
    { value: 'md', label: 'md' },
    { value: 'txt', label: 'txt' },
];

const FILE_TYPE_CLASS_MAP = {
    xls: 'excel',
    xlsx: 'excel',
    csv: 'excel',
    doc: 'word',
    docx: 'word',
    pdf: 'pdf',
    ppt: 'ppt',
    pptx: 'ppt',
    png: 'image',
    jpg: 'image',
    jpeg: 'image',
    gif: 'image',
    webp: 'image',
    md: 'text',
    markdown: 'text',
    txt: 'text',
    json: 'text',
    zip: 'archive',
    rar: 'archive',
    '7z': 'archive',
};

const FILE_TYPE_LABEL_MAP = {
    excel: 'X',
    word: 'W',
    pdf: 'PDF',
    ppt: 'P',
    image: 'IMG',
    text: 'TXT',
    archive: 'ZIP',
    file: 'FILE',
};

function sortFolders(items) {
    return [...items].sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime());
}

function formatExplorerDate(value) {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const currentYear = new Date().getFullYear();
    if (date.getFullYear() === currentYear) {
        return `${month}-${day} ${hours}:${minutes}`;
    }
    return `${date.getFullYear()}-${month}-${day} ${hours}:${minutes}`;
}

function formatFileSize(size) {
    const value = Number(size);
    if (!Number.isFinite(value) || value < 0) return '-';
    if (value === 0) return '0B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let amount = value;
    let unitIndex = 0;
    while (amount >= 1024 && unitIndex < units.length - 1) {
        amount /= 1024;
        unitIndex += 1;
    }
    if (unitIndex === 0) return `${Math.round(amount)}B`;
    return `${amount.toFixed(1)}${units[unitIndex]}`;
}

function getFileExtension(filename) {
    const match = String(filename || '').trim().toLowerCase().match(/\.([a-z0-9]+)$/);
    return match ? match[1] : '';
}

function getFileIcon(fileType, filename) {
    const normalized = String(fileType || getFileExtension(filename) || '').trim().toLowerCase();
    const iconType = FILE_TYPE_CLASS_MAP[normalized] || 'file';
    return {
        className: `resource-file-icon ${iconType}`,
        label: FILE_TYPE_LABEL_MAP[iconType] || FILE_TYPE_LABEL_MAP.file,
    };
}

function getExplorerRowTime(row) {
    const value = row?.type === 'folder'
        ? row.folder?.created_at
        : row?.type === 'course'
            ? row.course?.updated_at || row.course?.created_at
            : row?.resource?.created_at;
    const time = new Date(value || 0).getTime();
    return Number.isFinite(time) ? time : 0;
}

function isAdminUser(username, userRole) {
    const role = String(userRole || '').trim().toLowerCase();
    const account = String(username || '').trim().toLowerCase();
    return role === 'admin' || account === 'admin' || account === 'fit_admin';
}

function getErrorMessage(error, fallback) {
    return error?.response?.data?.detail || fallback;
}

function normalizeFolderName(value) {
    return String(value || '').trim().toLowerCase();
}

function getCourseResourceFolderName(course) {
    return String(course?.name || '').trim() || '课程资料';
}

function ResourceFileManagement({ username, userRole, initialCourseId = '', initialCourseOpenKey = 0 }) {
    const isAdmin = isAdminUser(username, userRole);
    const [folders, setFolders] = useState([]);
    const [teachers, setTeachers] = useState([]);
    const [courses, setCourses] = useState([]);
    const [selectedCourseId, setSelectedCourseId] = useState('');
    const [selectedFolderId, setSelectedFolderId] = useState('');
    const [pendingCourseFolderOpenId, setPendingCourseFolderOpenId] = useState('');
    const [ownerFilter, setOwnerFilter] = useState('');
    const [resources, setResources] = useState([]);
    const [totalCount, setTotalCount] = useState(0);
    const [foldersLoading, setFoldersLoading] = useState(false);
    const [coursesLoading, setCoursesLoading] = useState(false);
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [searchName, setSearchName] = useState('');
    const [searchType, setSearchType] = useState('');
    const [selectedRowIds, setSelectedRowIds] = useState([]);
    const [detailVisible, setDetailVisible] = useState(false);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailData, setDetailData] = useState(null);
    const fileInputRef = useRef(null);
    const resourceRequestVersionRef = useRef(0);
    const initialCourseEffectHasRunRef = useRef(false);

    const clearResourceList = useCallback(() => {
        resourceRequestVersionRef.current += 1;
        setResources([]);
        setTotalCount(0);
    }, []);

    const selectedFolder = useMemo(
        () => folders.find((item) => item.id === selectedFolderId) || null,
        [folders, selectedFolderId],
    );

    const selectedCourse = useMemo(
        () => courses.find((item) => String(item?.id || '') === String(selectedCourseId || '')) || null,
        [courses, selectedCourseId],
    );

    const courseTitle = selectedCourse?.name || '课程资料';

    const ownerOptions = useMemo(() => {
        const map = new Map();
        teachers.forEach((item) => {
            const account = String(item?.username || '').trim();
            if (!account) return;
            map.set(account, item?.real_name && item.real_name !== account ? `${account}（${item.real_name}）` : account);
        });
        folders.forEach((item) => {
            const account = String(item?.owner_username || '').trim();
            if (account && !map.has(account)) map.set(account, account);
        });
        courses.forEach((item) => {
            const account = String(item?.created_by || '').trim();
            if (account && !map.has(account)) map.set(account, account);
        });
        return Array.from(map.entries()).map(([value, label]) => ({ value, label }));
    }, [courses, folders, teachers]);

    const visibleCourses = useMemo(() => {
        if (selectedCourseId || selectedFolderId || searchType) return [];
        const keyword = searchName.trim().toLowerCase();
        return courses.filter((course) => {
            if (isAdmin && ownerFilter && String(course?.created_by || '').trim() !== ownerFilter) return false;
            if (!keyword) return true;
            return `${course?.name || ''} ${course?.description || ''} ${course?.created_by || ''}`.toLowerCase().includes(keyword);
        });
    }, [courses, isAdmin, ownerFilter, searchName, searchType, selectedCourseId, selectedFolderId]);

    const visibleFolders = useMemo(() => {
        if (selectedFolderId || searchType) return [];
        const keyword = searchName.trim().toLowerCase();
        if (!keyword) return folders;
        return folders.filter((folder) => String(folder.name || '').toLowerCase().includes(keyword));
    }, [folders, searchName, searchType, selectedFolderId]);

    const explorerRows = useMemo(() => {
        const rows = [
            ...visibleCourses.map((course) => ({
                key: `course:${course.id}`,
                type: 'course',
                course,
            })),
            ...visibleFolders.map((folder) => ({
                key: `folder:${folder.id}`,
                type: 'folder',
                folder,
            })),
            ...resources.map((resource) => ({
                key: `file:${resource.id}`,
                type: 'file',
                resource,
            })),
        ];
        rows.sort((a, b) => getExplorerRowTime(b) - getExplorerRowTime(a));
        return rows;
    }, [resources, visibleCourses, visibleFolders]);

    const visibleRowIds = useMemo(
        () => explorerRows.filter((row) => row.type !== 'course').map((row) => row.key),
        [explorerRows],
    );
    const selectedRowSet = useMemo(() => new Set(selectedRowIds), [selectedRowIds]);
    const allRowsSelected = visibleRowIds.length > 0 && visibleRowIds.every((id) => selectedRowSet.has(id));
    const selectedFiles = useMemo(
        () => resources.filter((item) => selectedRowSet.has(`file:${item.id}`)),
        [resources, selectedRowSet],
    );
    const selectedFolders = useMemo(
        () => visibleFolders.filter((item) => selectedRowSet.has(`folder:${item.id}`)),
        [selectedRowSet, visibleFolders],
    );

    const loadTeachers = useCallback(async () => {
        if (!isAdmin || !username) return;
        try {
            const response = await axios.get(`${API_BASE_URL}/api/admin/teachers`, {
                params: { admin_username: username },
            });
            setTeachers(Array.isArray(response.data) ? response.data : []);
        } catch (error) {
            console.error('Failed to load teachers:', error);
            setTeachers([]);
        }
    }, [isAdmin, username]);

    const loadCourses = useCallback(async () => {
        if (!username) return;
        setCoursesLoading(true);
        try {
            const response = await axios.get(`${API_BASE_URL}/api/teacher/courses`, {
                params: { teacher_username: username },
            });
            const items = Array.isArray(response.data) ? response.data : [];
            setCourses(items);
        } catch (error) {
            console.error('Failed to load courses:', error);
            setCourses([]);
        } finally {
            setCoursesLoading(false);
        }
    }, [username]);

    const loadFolders = useCallback(async () => {
        if (!username) return;
        setFoldersLoading(true);
        try {
            const response = selectedCourseId
                ? await axios.get(`${API_BASE_URL}/api/teacher/courses/${selectedCourseId}/resource-folders`, {
                    params: { teacher_username: username },
                })
                : await axios.get(`${API_BASE_URL}/api/admin/resource-folders`, {
                    params: {
                        teacher_username: username,
                        owner_username: isAdmin ? (ownerFilter || undefined) : undefined,
                    },
                });
            const items = Array.isArray(response.data?.items) ? response.data.items : [];
            setFolders(items);
            setSelectedFolderId((current) => (current && items.some((item) => item.id === current) ? current : ''));
        } catch (error) {
            console.error('Failed to load resource folders:', error);
            alert(getErrorMessage(error, '加载资源文件夹失败'));
            setFolders([]);
            setSelectedFolderId('');
        } finally {
            setFoldersLoading(false);
        }
    }, [isAdmin, ownerFilter, selectedCourseId, username]);

    const loadResources = useCallback(async ({ name = searchName, fileType = searchType } = {}) => {
        if (!username) return;
        const requestVersion = resourceRequestVersionRef.current + 1;
        resourceRequestVersionRef.current = requestVersion;
        const requestCourseId = selectedCourseId;
        const requestFolderId = selectedFolderId;
        setLoading(true);
        try {
            const response = requestCourseId
                ? await axios.get(`${API_BASE_URL}/api/teacher/courses/${requestCourseId}/resources`, {
                    params: {
                        teacher_username: username,
                        name: name || undefined,
                        file_type: fileType || undefined,
                        folder_id: requestFolderId || undefined,
                    },
                })
                : await axios.get(`${API_BASE_URL}/api/admin/resources`, {
                    params: {
                        teacher_username: username,
                        name: name || undefined,
                        file_type: fileType || undefined,
                        folder_id: requestFolderId || undefined,
                        owner_username: isAdmin ? (ownerFilter || undefined) : undefined,
                    },
                });
            if (resourceRequestVersionRef.current !== requestVersion) return;
            const payload = response.data || {};
            setResources(Array.isArray(payload.items) ? payload.items : []);
            setTotalCount(Number.isFinite(payload.total) ? payload.total : 0);
        } catch (error) {
            if (resourceRequestVersionRef.current !== requestVersion) return;
            console.error('Failed to load resources:', error);
            alert(getErrorMessage(error, '加载资源文件失败'));
            setResources([]);
            setTotalCount(0);
        } finally {
            if (resourceRequestVersionRef.current === requestVersion) {
                setLoading(false);
            }
        }
    }, [isAdmin, ownerFilter, searchName, searchType, selectedCourseId, selectedFolderId, username]);

    const ensureCourseNamedFolder = useCallback(async (course) => {
        const courseId = String(course?.id || '').trim();
        const folderName = getCourseResourceFolderName(course);
        if (!courseId || !username) return;

        clearResourceList();
        setFoldersLoading(true);
        setSelectedFolderId('');
        setSelectedRowIds([]);
        try {
            const loadCourseFolders = async () => {
                const response = await axios.get(`${API_BASE_URL}/api/teacher/courses/${courseId}/resource-folders`, {
                    params: { teacher_username: username },
                });
                return Array.isArray(response.data?.items) ? response.data.items : [];
            };

            let items = await loadCourseFolders();
            let targetFolder = items.find((item) => normalizeFolderName(item.name) === normalizeFolderName(folderName));
            if (!targetFolder) {
                try {
                    const createResponse = await axios.post(`${API_BASE_URL}/api/teacher/courses/${courseId}/resource-folders`, {
                        teacher_username: username,
                        name: folderName,
                    });
                    targetFolder = createResponse.data || null;
                    if (targetFolder?.id) {
                        items = sortFolders([targetFolder, ...items.filter((item) => item.id !== targetFolder.id)]);
                    }
                } catch (error) {
                    if (error?.response?.status !== 409) {
                        throw error;
                    }
                    items = await loadCourseFolders();
                    targetFolder = items.find((item) => normalizeFolderName(item.name) === normalizeFolderName(folderName));
                }
            }

            setSelectedCourseId(courseId);
            setFolders(items);
            if (targetFolder?.id) {
                setSelectedFolderId(targetFolder.id);
            }
        } catch (error) {
            console.error('Failed to ensure course resource folder:', error);
            setSelectedCourseId(courseId);
            alert(getErrorMessage(error, '打开课程资料文件夹失败'));
        } finally {
            setFoldersLoading(false);
        }
    }, [clearResourceList, username]);

    useEffect(() => {
        loadTeachers();
    }, [loadTeachers]);

    useEffect(() => {
        loadCourses();
    }, [loadCourses]);

    useEffect(() => {
        loadFolders();
    }, [loadFolders]);

    useEffect(() => {
        loadResources({ name: searchName, fileType: searchType });
    }, [loadResources, searchName, searchType]);

    useEffect(() => {
        const targetCourseId = String(initialCourseId || '').trim();
        if (!targetCourseId) {
            const isAlreadyAtResourceRoot = !selectedCourseId && !selectedFolderId && !pendingCourseFolderOpenId;
            if (!initialCourseEffectHasRunRef.current) {
                initialCourseEffectHasRunRef.current = true;
                return;
            }
            initialCourseEffectHasRunRef.current = true;
            if (isAlreadyAtResourceRoot) {
                return;
            }
            setSelectedCourseId('');
            setSelectedFolderId('');
            setSelectedRowIds([]);
            setPendingCourseFolderOpenId('');
            clearResourceList();
            return;
        }
        initialCourseEffectHasRunRef.current = true;
        setPendingCourseFolderOpenId(targetCourseId);
        // This effect intentionally reacts only to parent open requests.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [clearResourceList, initialCourseId, initialCourseOpenKey]);

    useEffect(() => {
        if (!pendingCourseFolderOpenId || coursesLoading) return;
        const course = courses.find((item) => String(item?.id || '') === String(pendingCourseFolderOpenId));
        if (!course) {
            if (courses.length > 0) {
                setPendingCourseFolderOpenId('');
            }
            return;
        }
        setPendingCourseFolderOpenId('');
        ensureCourseNamedFolder(course);
    }, [courses, coursesLoading, ensureCourseNamedFolder, pendingCourseFolderOpenId]);

    useEffect(() => {
        if (!selectedCourseId || coursesLoading || courses.length === 0) return;
        if (!courses.some((item) => String(item?.id || '') === String(selectedCourseId))) {
            clearResourceList();
            setSelectedCourseId('');
            setSelectedFolderId('');
        }
    }, [clearResourceList, courses, coursesLoading, selectedCourseId]);

    useEffect(() => {
        setSelectedRowIds([]);
    }, [ownerFilter, searchName, searchType, selectedCourseId, selectedFolderId]);

    const refreshAll = async (event) => {
        event?.preventDefault?.();
        event?.stopPropagation?.();
        await loadCourses();
        await loadFolders();
        await loadResources({ name: searchName, fileType: searchType });
    };

    const openCourse = async (course) => {
        if (!course?.id) return;
        await ensureCourseNamedFolder(course);
    };

    const closeCourse = () => {
        clearResourceList();
        setSelectedCourseId('');
        setSelectedFolderId('');
        setDetailVisible(false);
        setDetailData(null);
        setSelectedRowIds([]);
    };

    const openFolder = (folder) => {
        clearResourceList();
        setSelectedFolderId(folder.id);
    };

    const createFolder = async () => {
        if (selectedFolderId) {
            alert('文件夹只支持在根目录创建');
            return;
        }
        const name = window.prompt('请输入文件夹名称');
        if (!name || !name.trim()) return;
        let owner = ownerFilter;
        if (!selectedCourseId && isAdmin && !owner) {
            owner = window.prompt('请输入所属老师账号');
            if (!owner || !owner.trim()) return;
        }
        const now = new Date().toISOString();
        const pendingId = `pending-${Date.now()}`;
        const pendingFolder = {
            id: pendingId,
            name: name.trim(),
            owner_username: selectedCourse?.created_by || (isAdmin ? owner.trim() : username),
            created_by: username,
            course_id: selectedCourseId || null,
            created_at: now,
            updated_at: now,
            resource_count: 0,
            is_default: false,
            pending: true,
        };
        setSelectedFolderId('');
        setFolders((current) => sortFolders([pendingFolder, ...current]));
        try {
            const response = selectedCourseId
                ? await axios.post(`${API_BASE_URL}/api/teacher/courses/${selectedCourseId}/resource-folders`, {
                    teacher_username: username,
                    name: name.trim(),
                })
                : await axios.post(`${API_BASE_URL}/api/admin/resource-folders`, {
                    teacher_username: username,
                    owner_username: isAdmin ? owner.trim() : undefined,
                    name: name.trim(),
                });
            const createdFolder = response.data || null;
            if (createdFolder?.id) {
                setFolders((current) => sortFolders(current.map((item) => (
                    item.id === pendingId ? createdFolder : item
                ))));
            } else {
                await loadFolders();
            }
        } catch (error) {
            setFolders((current) => current.filter((item) => item.id !== pendingId));
            console.error('Failed to create folder:', error);
            alert(getErrorMessage(error, '创建文件夹失败'));
        }
    };

    const renameFolder = async (folder) => {
        if (!folder) return;
        const name = window.prompt('请输入新的文件夹名称', folder.name);
        if (!name || !name.trim() || name.trim() === folder.name) return;
        try {
            if (selectedCourseId) {
                await axios.patch(`${API_BASE_URL}/api/teacher/courses/${selectedCourseId}/resource-folders/${folder.id}`, {
                    teacher_username: username,
                    name: name.trim(),
                });
            } else {
                await axios.patch(`${API_BASE_URL}/api/admin/resource-folders/${folder.id}`, {
                    teacher_username: username,
                    name: name.trim(),
                });
            }
            await refreshAll();
        } catch (error) {
            console.error('Failed to rename folder:', error);
            alert(getErrorMessage(error, '重命名文件夹失败'));
        }
    };

    const deleteFolder = async (folder) => {
        if (!folder) return;
        if (!window.confirm(`确定删除文件夹“${folder.name}”吗？`)) return;
        try {
            if (selectedCourseId) {
                await axios.delete(`${API_BASE_URL}/api/teacher/courses/${selectedCourseId}/resource-folders/${folder.id}`, {
                    params: { teacher_username: username },
                });
            } else {
                await axios.delete(`${API_BASE_URL}/api/admin/resource-folders/${folder.id}`, {
                    params: { teacher_username: username },
                });
            }
            if (selectedFolderId === folder.id) setSelectedFolderId('');
            await refreshAll();
            alert('文件夹已删除');
        } catch (error) {
            console.error('Failed to delete folder:', error);
            alert(getErrorMessage(error, '删除文件夹失败'));
        }
    };

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
            if (selectedCourseId) {
                await axios.post(`${API_BASE_URL}/api/teacher/courses/${selectedCourseId}/resources/upload`, formData, {
                    params: {
                        teacher_username: username,
                        folder_id: selectedFolderId || undefined,
                    },
                    headers: { 'Content-Type': 'multipart/form-data' },
                });
            } else {
                await axios.post(`${API_BASE_URL}/api/admin/resources/upload`, formData, {
                    params: {
                        teacher_username: username,
                        folder_id: selectedFolderId || undefined,
                        owner_username: isAdmin ? (ownerFilter || undefined) : undefined,
                    },
                    headers: { 'Content-Type': 'multipart/form-data' },
                });
            }
            await refreshAll();
            alert('资源文件上传成功');
        } catch (error) {
            console.error('Failed to upload resource:', error);
            alert(getErrorMessage(error, '资源文件上传失败'));
        } finally {
            setUploading(false);
        }
    };

    const handleDelete = async (item) => {
        if (!window.confirm(`确定删除文件“${item.filename}”吗？`)) return;
        try {
            if (selectedCourseId) {
                await axios.delete(`${API_BASE_URL}/api/teacher/courses/${selectedCourseId}/resources/${item.id}`, {
                    params: { teacher_username: username },
                });
            } else {
                await axios.delete(`${API_BASE_URL}/api/admin/resources/${item.id}`, {
                    params: { teacher_username: username },
                });
            }
            if (detailData?.id === item.id) {
                setDetailVisible(false);
                setDetailData(null);
            }
            await refreshAll();
            alert('资源文件已删除');
        } catch (error) {
            console.error('Failed to delete resource:', error);
            alert(getErrorMessage(error, '删除资源文件失败'));
        }
    };

    const handleBatchDelete = async () => {
        const fileCount = selectedFiles.length;
        const folderCount = selectedFolders.length;
        if (!fileCount && !folderCount) return;
        if (!window.confirm(`确定删除选中的 ${folderCount} 个文件夹、${fileCount} 个文件吗？`)) return;
        const errors = [];
        for (const item of selectedFiles) {
            try {
                if (selectedCourseId) {
                    await axios.delete(`${API_BASE_URL}/api/teacher/courses/${selectedCourseId}/resources/${item.id}`, {
                        params: { teacher_username: username },
                    });
                } else {
                    await axios.delete(`${API_BASE_URL}/api/admin/resources/${item.id}`, {
                        params: { teacher_username: username },
                    });
                }
            } catch (error) {
                errors.push(`${item.filename}：${getErrorMessage(error, '删除失败')}`);
            }
        }
        for (const folder of selectedFolders) {
            try {
                if (selectedCourseId) {
                    await axios.delete(`${API_BASE_URL}/api/teacher/courses/${selectedCourseId}/resource-folders/${folder.id}`, {
                        params: { teacher_username: username },
                    });
                } else {
                    await axios.delete(`${API_BASE_URL}/api/admin/resource-folders/${folder.id}`, {
                        params: { teacher_username: username },
                    });
                }
            } catch (error) {
                errors.push(`${folder.name}：${getErrorMessage(error, '删除失败')}`);
            }
        }
        setSelectedRowIds([]);
        await refreshAll();
        if (errors.length) {
            alert(`部分项目删除失败：\n${errors.join('\n')}`);
        } else {
            alert('选中项目已删除');
        }
    };

    const handleViewDetail = async (item) => {
        setDetailVisible(true);
        setDetailLoading(true);
        setDetailData(null);
        try {
            const response = selectedCourseId
                ? await axios.get(`${API_BASE_URL}/api/teacher/courses/${selectedCourseId}/resources/${item.id}`, {
                    params: { teacher_username: username },
                })
                : await axios.get(`${API_BASE_URL}/api/admin/resources/${item.id}`, {
                    params: { teacher_username: username },
                });
            setDetailData(response.data || null);
        } catch (error) {
            console.error('Failed to load resource detail:', error);
            alert(getErrorMessage(error, '加载资源详情失败'));
            setDetailVisible(false);
        } finally {
            setDetailLoading(false);
        }
    };

    const closeDetail = () => {
        setDetailVisible(false);
        setDetailData(null);
    };

    const toggleRowSelection = (rowId) => {
        setSelectedRowIds((current) => (
            current.includes(rowId)
                ? current.filter((item) => item !== rowId)
                : [...current, rowId]
        ));
    };

    const toggleAllSelection = () => {
        setSelectedRowIds((current) => {
            if (allRowsSelected) {
                return current.filter((id) => !visibleRowIds.includes(id));
            }
            return Array.from(new Set([...current, ...visibleRowIds]));
        });
    };

    const renderOwnerMeta = (ownerUsername) => {
        if (!isAdmin || !ownerUsername) return null;
        return <span className="resource-owner-meta">{ownerUsername}</span>;
    };

    const renderCourseRow = (course) => {
        const rowId = `course:${course.id}`;
        const totalExperiments = Number(course?.experiment_count ?? (Array.isArray(course?.experiments) ? course.experiments.length : 0));
        return (
            <tr key={rowId} className="resource-explorer-row folder-row course-row">
                <td className="resource-check-cell" />
                <td className="resource-name-cell">
                    <div className="resource-name-cell-inner">
                        <button className="resource-name-button" type="button" onClick={() => openCourse(course)}>
                            <span className="resource-folder-icon explorer-folder-icon course-folder-icon" aria-hidden="true" />
                            <span className="resource-name-text">
                                <span className="resource-primary-name">{course.name || '未命名课程'}</span>
                                <span className="resource-secondary-meta">
                                    {renderOwnerMeta(course.created_by)}
                                    <span>课程资料</span>
                                    <span>{totalExperiments} 个实验</span>
                                </span>
                            </span>
                        </button>
                        <div className="resource-row-actions">
                            <button type="button" onClick={() => openCourse(course)}>打开</button>
                        </div>
                    </div>
                </td>
                <td className="resource-size-cell">--</td>
                <td className="resource-date-cell">{formatExplorerDate(course.updated_at || course.created_at)}</td>
            </tr>
        );
    };

    const renderFolderRow = (folder) => {
        const rowId = `folder:${folder.id}`;
        return (
            <tr key={rowId} className="resource-explorer-row folder-row">
                <td className="resource-check-cell">
                    <input
                        type="checkbox"
                        aria-label={`选择文件夹 ${folder.name}`}
                        checked={selectedRowSet.has(rowId)}
                        onChange={() => toggleRowSelection(rowId)}
                    />
                </td>
                <td className="resource-name-cell">
                    <div className="resource-name-cell-inner">
                        <button className="resource-name-button" type="button" onClick={() => openFolder(folder)}>
                            <span className="resource-folder-icon explorer-folder-icon" aria-hidden="true" />
                            <span className="resource-name-text">
                                <span className="resource-primary-name">{folder.name}</span>
                                <span className="resource-secondary-meta">
                                    {renderOwnerMeta(folder.owner_username)}
                                    <span>{folder.resource_count || 0} 个文件</span>
                                </span>
                            </span>
                        </button>
                        <div className="resource-row-actions">
                            <button type="button" onClick={() => openFolder(folder)}>打开</button>
                            <button type="button" onClick={() => renameFolder(folder)}>重命名</button>
                            <button className="danger" type="button" onClick={() => deleteFolder(folder)}>删除</button>
                        </div>
                    </div>
                </td>
                <td className="resource-size-cell">--</td>
                <td className="resource-date-cell">{formatExplorerDate(folder.created_at)}</td>
            </tr>
        );
    };

    const renderFileRow = (item) => {
        const rowId = `file:${item.id}`;
        const icon = getFileIcon(item.file_type, item.filename);
        const downloadUrl = item.download_url
            ? `${API_BASE_URL}${item.download_url}?teacher_username=${encodeURIComponent(username)}`
            : '';
        return (
            <tr key={rowId} className="resource-explorer-row file-row">
                <td className="resource-check-cell">
                    <input
                        type="checkbox"
                        aria-label={`选择文件 ${item.filename}`}
                        checked={selectedRowSet.has(rowId)}
                        onChange={() => toggleRowSelection(rowId)}
                    />
                </td>
                <td className="resource-name-cell">
                    <div className="resource-name-cell-inner">
                        <button className="resource-name-button" type="button" onClick={() => handleViewDetail(item)}>
                            <span className={icon.className} aria-hidden="true">{icon.label}</span>
                            <span className="resource-name-text">
                                <span className="resource-primary-name">{item.filename}</span>
                                <span className="resource-secondary-meta">
                                    {renderOwnerMeta(item.owner_username || item.created_by)}
                                    {item.folder_name ? <span>{item.folder_name}</span> : null}
                                    {item.file_type ? <span>{item.file_type}</span> : null}
                                </span>
                            </span>
                        </button>
                        <div className="resource-row-actions">
                            <button type="button" onClick={() => handleViewDetail(item)}>详情</button>
                            {downloadUrl ? (
                                <a href={downloadUrl} target="_blank" rel="noreferrer">下载</a>
                            ) : null}
                            <button className="danger" type="button" onClick={() => handleDelete(item)}>删除</button>
                        </div>
                    </div>
                </td>
                <td className="resource-size-cell">{formatFileSize(item.size)}</td>
                <td className="resource-date-cell">{formatExplorerDate(item.created_at)}</td>
            </tr>
        );
    };

    return (
        <div className="resource-file-management">
            <div className="resource-compact-bar">
                {isAdmin ? (
                    <label>
                        老师筛选
                        <select
                            value={ownerFilter}
                            onChange={(event) => {
                                clearResourceList();
                                setOwnerFilter(event.target.value);
                                setSelectedCourseId('');
                                setSelectedFolderId('');
                            }}
                        >
                            <option value="">全部老师</option>
                            {ownerOptions.map((item) => (
                                <option key={item.value} value={item.value}>{item.label}</option>
                            ))}
                        </select>
                    </label>
                ) : (
                    <span className="resource-scope-label">{selectedCourseId ? `课程资料：${courseTitle}` : '我的资源文件'}</span>
                )}
                <button className="resource-refresh-btn" type="button" onClick={refreshAll}>
                    刷新
                </button>
            </div>

            <section className="resource-content-pane">
                {selectedCourseId || selectedFolder ? (
                    <div className="resource-path-bar">
                        {selectedCourseId ? (
                            <>
                                <button type="button" onClick={closeCourse}>
                                    返回资源根目录
                                </button>
                                <strong>{courseTitle}</strong>
                            </>
                        ) : null}
                        {selectedCourseId && selectedFolder ? <span>/</span> : null}
                        {selectedFolder ? (
                            <>
                            <button type="button" onClick={() => setSelectedFolderId('')}>
                                {selectedCourseId ? '返回课程资料' : '返回'}
                            </button>
                            <strong>{selectedFolder.name}</strong>
                            </>
                        ) : null}
                    </div>
                ) : null}

                <div className="resource-toolbar">
                    <div className="resource-toolbar-left">
                        <button
                            className="resource-new-folder-btn"
                            type="button"
                            onClick={createFolder}
                            disabled={Boolean(selectedFolderId)}
                            title={selectedFolderId ? '文件夹只支持在根目录创建' : '新建文件夹'}
                        >
                            新建文件夹
                        </button>
                        <button
                            className="resource-upload-btn"
                            type="button"
                            onClick={openUpload}
                            disabled={uploading}
                            title={selectedFolderId ? `上传到：${selectedFolder?.name || '当前文件夹'}` : `上传到：${selectedCourseId ? courseTitle : '当前目录'}`}
                        >
                            {uploading ? '上传中...' : '上传资源文件'}
                        </button>
                        <input
                            ref={fileInputRef}
                            type="file"
                            className="resource-file-input"
                            accept=".pdf,.doc,.docx,.md,.markdown,.txt,.csv,.json,.ppt,.pptx,.xls,.xlsx,.zip,.rar,.7z,.png,.jpg,.jpeg,.gif,.webp"
                            onChange={handleUploadChange}
                        />
                    </div>
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
                        <button className="resource-search-btn" type="button" onClick={() => loadResources()}>
                            搜索
                        </button>
                    </div>
                </div>

                <div className="resource-list-summary">
                    {foldersLoading || coursesLoading
                        ? '加载中...'
                        : selectedFolder
                            ? `文件 ${totalCount} 个`
                            : selectedCourseId
                                ? `文件夹 ${visibleFolders.length} 个 / 文件 ${totalCount} 个`
                                : `课程 ${visibleCourses.length} 个 / 文件夹 ${visibleFolders.length} 个 / 文件 ${totalCount} 个`}
                </div>

                {selectedRowIds.length > 0 ? (
                    <div className="resource-selection-bar">
                        <span>已选择 {selectedRowIds.length} 项</span>
                        <button type="button" onClick={() => setSelectedRowIds([])}>取消选择</button>
                        <button className="danger" type="button" onClick={handleBatchDelete}>批量删除</button>
                    </div>
                ) : null}

                <div className="resource-table-wrap">
                    <table className="resource-table resource-explorer-table">
                        <thead>
                            <tr>
                                <th className="resource-check-cell">
                                    <input
                                        type="checkbox"
                                        aria-label="选择全部"
                                        checked={allRowsSelected}
                                        disabled={visibleRowIds.length === 0}
                                        onChange={toggleAllSelection}
                                    />
                                </th>
                                <th>文件名</th>
                                <th className="resource-size-cell">大小</th>
                                <th className="resource-date-cell">创建日期</th>
                            </tr>
                        </thead>
                        <tbody>
                            {foldersLoading || coursesLoading || loading ? (
                                <tr>
                                    <td colSpan={4} className="resource-empty-row">加载中...</td>
                                </tr>
                            ) : explorerRows.length === 0 ? (
                                <tr>
                                    <td colSpan={4} className="resource-empty-row">暂无资源文件</td>
                                </tr>
                            ) : (
                                explorerRows.map((row) => (
                                    row.type === 'course'
                                        ? renderCourseRow(row.course)
                                        : row.type === 'folder'
                                        ? renderFolderRow(row.folder)
                                        : renderFileRow(row.resource)
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </section>

            {detailVisible ? (
                <div className="resource-modal-mask" onClick={closeDetail}>
                    <div className="resource-modal" onClick={(event) => event.stopPropagation()}>
                        <div className="resource-modal-header">
                            <h3>{detailData?.filename || '资源文件详情'}</h3>
                            <button type="button" onClick={closeDetail}>关闭</button>
                        </div>
                        <div className="resource-modal-body">
                            {detailLoading ? (
                                <div className="resource-preview-empty">详情加载中...</div>
                            ) : detailData ? (
                                <>
                                    <div className="resource-detail-meta">
                                        {selectedCourseId ? <span>课程：{courseTitle}</span> : null}
                                        <span>文件夹：{detailData.folder_name || selectedFolder?.name || '-'}</span>
                                        <span>所属老师：{detailData.owner_username || detailData.created_by || '-'}</span>
                                        <span>类型：{detailData.file_type || '-'}</span>
                                        <span>大小：{formatFileSize(detailData.size)}</span>
                                    </div>
                                    <ResourcePreviewContent
                                        detailData={detailData}
                                        accessQueryKey="teacher_username"
                                        accessQueryValue={username}
                                        loadingText="预览加载中..."
                                        emptyText="暂无可预览内容"
                                        unsupportedText="当前文件类型不支持在线预览，请下载查看。"
                                    />
                                </>
                            ) : (
                                <div className="resource-preview-empty">暂无详情</div>
                            )}
                        </div>
                        {detailData ? (
                            <div className="resource-modal-footer">
                                <a
                                    href={`${API_BASE_URL}${detailData.download_url}?teacher_username=${encodeURIComponent(username)}`}
                                    target="_blank"
                                    rel="noreferrer"
                                >
                                    下载文件
                                </a>
                            </div>
                        ) : null}
                    </div>
                </div>
            ) : null}
        </div>
    );
}

export default ResourceFileManagement;
