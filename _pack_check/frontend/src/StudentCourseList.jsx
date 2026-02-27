import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import ResourcePreviewContent from './ResourcePreviewContent';
import './StudentCourseList.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';
const SELECTED_COURSE_CACHE_KEY = 'studentSelectedCourseKey';

const TEXT = {
    platformTitle: '福州理工学院AI编程实践教学平台',
    platformSubTitle: 'FUZHOU INSTITUTE OF TECHNOLOGY · AI PROGRAMMING PRACTICE TEACHING PLATFORM',
    logout: '\u9000\u51fa',
    namePrefix: '\u59d3\u540d',
    classPrefix: '\u73ed\u7ea7',
    studentIdPrefix: '\u5b66\u53f7',
    unknownClass: '\u672a\u7ed1\u5b9a\u73ed\u7ea7',
    moduleLabel: '\u8bfe\u7a0b\u5e93',
    resourceModuleLabel: '\u5e73\u53f0\u8d44\u6e90',
    profileModuleLabel: '\u4e2a\u4eba\u4e2d\u5fc3',
    sidebarTitle: '\u6a21\u5757',
    breadcrumbCurrent: '\u8bfe\u7a0b\u5e93',
    resourceBreadcrumbCurrent: '\u6559\u5b66\u4e0e\u5b9e\u9a8c\u8d44\u6e90',
    profileBreadcrumbCurrent: '\u4e2a\u4eba\u4e2d\u5fc3',
    loading: '\u6b63\u5728\u52a0\u8f7d\u8bfe\u7a0b\u5217\u8868...',
    empty: '\u5f53\u524d\u6682\u65e0\u53ef\u7528\u8bfe\u7a0b',
    chooseCourse: '\u8fdb\u5165\u8bfe\u7a0b',
    backToCourseLibrary: '\u8fd4\u56de\u8bfe\u7a0b\u5e93',
    courseCountPrefix: '\u5b9e\u9a8c\u6570\uff1a',
    courseUntitled: '\u672a\u547d\u540d\u8bfe\u7a0b',
    inProgressCountPrefix: '\u8fdb\u884c\u4e2d\uff1a',
    completedCountPrefix: '\u5df2\u5b8c\u6210\uff1a',
    noDescription: '\u6682\u65e0\u63cf\u8ff0',
    teacherPrefix: '\u6388\u8bfe\u8001\u5e08\uff1a',
    unknownTeacher: '\u672a\u77e5',
    openExperiment: '\u6253\u5f00\u5b9e\u9a8c',
    uploadPdf: '\u5b9e\u9a8c\u62a5\u544a PDF\uff08\u53ef\u9009\uff09',
    submitHomework: '\u63d0\u4ea4\u4f5c\u4e1a',
    confirmSubmit: '\u786e\u8ba4\u63d0\u4ea4\u5b9e\u9a8c\u5417\uff1f\u63d0\u4ea4\u524d\u8bf7\u5148\u5728 JupyterLab \u4fdd\u5b58\u597d\u6587\u4ef6\u3002',
    submitSuccess: '\u5b9e\u9a8c\u63d0\u4ea4\u6210\u529f\u3002',
    submitSuccessWithPdf: '\u5b9e\u9a8c\u548c PDF \u62a5\u544a\u5df2\u63d0\u4ea4\u3002',
    loadError: '\u52a0\u8f7d\u5b9e\u9a8c\u5217\u8868\u5931\u8d25\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5\u3002',
    startError: '\u542f\u52a8\u5b9e\u9a8c\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5\u3002',
    submitErrorPrefix: '\u63d0\u4ea4\u5931\u8d25: ',
    scorePrefix: '\u5f97\u5206\uff1a',
    viewAttachment: '\u67e5\u770b\u9644\u4ef6',
    hideAttachment: '\u9690\u85cf\u9644\u4ef6',
    noAttachment: '\u6682\u65e0\u9644\u4ef6',
    download: '\u4e0b\u8f7d',
    resourceNamePlaceholder: '\u8bf7\u8f93\u5165\u540d\u79f0',
    resourceTypePlaceholder: '\u8bf7\u9009\u62e9\u7c7b\u578b',
    resourceSearch: '\u641c\u7d22',
    resourceTotalPrefix: '\u5e73\u53f0\u8d44\u6e90\u6587\u4ef6\u5171',
    resourceTotalSuffix: '\u4e2a',
    resourceLoading: '\u6b63\u5728\u52a0\u8f7d\u8d44\u6e90\u5217\u8868...',
    resourceEmpty: '\u6682\u65e0\u53ef\u7528\u8d44\u6e90',
    resourceLoadError: '\u52a0\u8f7d\u8d44\u6e90\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002',
    resourceDetailError: '\u52a0\u8f7d\u8d44\u6e90\u8be6\u60c5\u5931\u8d25',
    resourceFileName: '\u6587\u4ef6\u540d',
    resourceFileType: '\u7c7b\u578b',
    resourceCreatedAt: '\u521b\u5efa\u65f6\u95f4',
    operation: '\u64cd\u4f5c',
    detail: '\u8be6\u60c5',
    close: '\u5173\u95ed',
    unsupportedPreview: '\u5f53\u524d\u6587\u4ef6\u7c7b\u578b\u4e0d\u652f\u6301\u5728\u7ebf\u9884\u89c8\uff0c\u8bf7\u4e0b\u8f7d\u67e5\u770b\u3002',
    noPreviewContent: '\u6682\u65e0\u53ef\u9884\u89c8\u5185\u5bb9',
    statusNotStarted: '\u672a\u5f00\u59cb',
    statusInProgress: '\u8fdb\u884c\u4e2d',
    statusSubmitted: '\u5df2\u63d0\u4ea4',
    statusGraded: '\u5df2\u8bc4\u5206',
    majorPrefix: '\u4e13\u4e1a',
    admissionYearPrefix: '\u5165\u5b66\u5e74\u4efd',
    profileInfoTitle: '\u4e2a\u4eba\u4fe1\u606f',
    profilePasswordTitle: '\u4fee\u6539\u5bc6\u7801',
    currentPassword: '\u5f53\u524d\u5bc6\u7801',
    newPassword: '\u65b0\u5bc6\u7801',
    confirmPassword: '\u786e\u8ba4\u65b0\u5bc6\u7801',
    passwordLengthHint: '\u5bc6\u7801\u4e0d\u5c11\u4e8e 6 \u4f4d',
    savePassword: '\u786e\u8ba4\u4fee\u6539',
    profileLoadError: '\u52a0\u8f7d\u4e2a\u4eba\u4fe1\u606f\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002',
    profileLoading: '\u6b63\u5728\u52a0\u8f7d\u4e2a\u4eba\u4fe1\u606f...',
    passwordMismatch: '\u4e24\u6b21\u8f93\u5165\u7684\u65b0\u5bc6\u7801\u4e0d\u4e00\u81f4',
    passwordTooShort: '\u65b0\u5bc6\u7801\u957f\u5ea6\u4e0d\u80fd\u5c11\u4e8e 6 \u4f4d',
    passwordChangeSuccess: '\u5bc6\u7801\u4fee\u6539\u6210\u529f',
    passwordChangeErrorPrefix: '\u4fee\u6539\u5bc6\u7801\u5931\u8d25\uff1a',
    profileNotAvailable: '\u6682\u65e0\u4e2a\u4eba\u4fe1\u606f'
};

const RESOURCE_TYPE_OPTIONS = [
    { value: '', label: '\u8bf7\u9009\u62e9\u7c7b\u578b' },
    { value: 'pdf', label: 'pdf' },
    { value: 'doc', label: 'doc' },
    { value: 'docx', label: 'docx' },
    { value: 'xls', label: 'xls' },
    { value: 'xlsx', label: 'xlsx' },
    { value: 'md', label: 'md' },
    { value: 'txt', label: 'txt' }
];

function formatDateTime(value) {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`;
}

function normalizeStatus(item) {
    if (item?.score !== null && item?.score !== undefined) {
        return 'graded';
    }
    if (item?.submit_time) {
        return 'submitted';
    }
    if (item?.student_exp_id) {
        return 'in-progress';
    }

    const rawStatus = String(item?.status || '').toLowerCase();
    if (rawStatus.includes('graded')) {
        return 'graded';
    }
    if (rawStatus.includes('submit')) {
        return 'submitted';
    }
    if (rawStatus.includes('progress')) {
        return 'in-progress';
    }
    return 'not-started';
}

function getStatusMeta(item) {
    const key = normalizeStatus(item);
    const map = {
        'not-started': { text: TEXT.statusNotStarted, className: 'status-not-started' },
        'in-progress': { text: TEXT.statusInProgress, className: 'status-in-progress' },
        submitted: { text: TEXT.statusSubmitted, className: 'status-submitted' },
        graded: { text: TEXT.statusGraded, className: 'status-graded' }
    };

    return { key, ...(map[key] || map['not-started']) };
}

function buildCourseKeywordText(course) {
    const title = String(course?.title || '').toLowerCase();
    const description = String(course?.description || '').toLowerCase();
    const tags = Array.isArray(course?.tags) ? course.tags.join(' ').toLowerCase() : '';
    return `${title} ${description} ${tags}`;
}

function getCourseIconMeta(course) {
    const text = buildCourseKeywordText(course);

    if (text.includes('vision') || text.includes('autodrive') || text.includes('\u81ea\u52a8\u9a7e\u9a76') || text.includes('\u89c6\u89c9')) {
        return { label: 'CV', themeClass: 'theme-vision' };
    }
    if (text.includes('matplotlib') || text.includes('\u53ef\u89c6\u5316') || text.includes('\u56fe\u8868')) {
        return { label: 'PLT', themeClass: 'theme-plot' };
    }
    if (text.includes('pandas')) {
        return { label: 'PD', themeClass: 'theme-pandas' };
    }
    if (text.includes('numpy')) {
        return { label: 'NP', themeClass: 'theme-numpy' };
    }
    if (text.includes('scikit') || text.includes('machine learning') || text.includes('\u673a\u5668\u5b66\u4e60')) {
        return { label: 'ML', themeClass: 'theme-ml' };
    }
    if (text.includes('python')) {
        return { label: 'PY', themeClass: 'theme-python' };
    }
    return { label: 'LAB', themeClass: 'theme-generic' };
}

function getTeacherName(course) {
    const teacherName = String(course?.created_by || '').trim();
    return teacherName || TEXT.unknownTeacher;
}

function StudentCourseList({ username, onLogout }) {
    const navigate = useNavigate();
    const [coursesWithStatus, setCoursesWithStatus] = useState([]);
    const [loading, setLoading] = useState(true);
    const [pdfFiles, setPdfFiles] = useState({});
    const [activeModule, setActiveModule] = useState('courses');
    const [selectedCourseKey, setSelectedCourseKey] = useState(
        () => sessionStorage.getItem(SELECTED_COURSE_CACHE_KEY) || ''
    );
    const [profile, setProfile] = useState(() => ({
        real_name: localStorage.getItem('real_name') || '',
        class_name: localStorage.getItem('class_name') || '',
        student_id: localStorage.getItem('student_id') || username || '',
        major: localStorage.getItem('major') || '',
        admission_year: localStorage.getItem('admission_year') || ''
    }));
    const realName = profile.real_name || username || '';
    const studentClass = profile.class_name || '';
    const studentId = profile.student_id || username || '';
    const classDisplay = studentClass || TEXT.unknownClass;
    const moduleLabel = activeModule === 'courses'
        ? TEXT.moduleLabel
        : activeModule === 'resources'
            ? TEXT.resourceModuleLabel
            : TEXT.profileModuleLabel;
    const breadcrumbLabel = activeModule === 'courses'
        ? TEXT.breadcrumbCurrent
        : activeModule === 'resources'
            ? TEXT.resourceBreadcrumbCurrent
            : TEXT.profileBreadcrumbCurrent;

    useEffect(() => {
        loadCoursesWithStatus();
        loadStudentProfileIfNeeded();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const groupedCourses = useMemo(() => {
        const groups = new Map();

        coursesWithStatus.forEach((item) => {
            const course = item?.course || {};
            const rawCourseId = String(course.course_id || '').trim();
            const rawCourseName = String(course.course_name || '').trim();
            const fallbackName = String(course.title || '').trim() || TEXT.courseUntitled;
            const courseName = rawCourseName || fallbackName;
            const key = rawCourseId ? `id:${rawCourseId}` : `name:${courseName.toLowerCase()}`;

            if (!groups.has(key)) {
                groups.set(key, {
                    key,
                    courseId: rawCourseId,
                    courseName,
                    description: String(course.description || '').trim(),
                    teacherName: getTeacherName(course),
                    tags: [],
                    experiments: [],
                });
            }

            const group = groups.get(key);
            group.experiments.push(item);

            const tags = Array.isArray(course.tags) ? course.tags : [];
            tags.forEach((tag) => {
                if (!group.tags.includes(tag)) {
                    group.tags.push(tag);
                }
            });

            const description = String(course.description || '').trim();
            if (!group.description && description) {
                group.description = description;
            }

            if (group.teacherName === TEXT.unknownTeacher) {
                group.teacherName = getTeacherName(course);
            }
        });

        return Array.from(groups.values()).sort((a, b) => a.courseName.localeCompare(b.courseName, 'zh-Hans-CN'));
    }, [coursesWithStatus]);

    const selectedCourse = useMemo(
        () => groupedCourses.find((item) => item.key === selectedCourseKey) || null,
        [groupedCourses, selectedCourseKey]
    );

    const selectedCourseExperiments = selectedCourse?.experiments || [];

    useEffect(() => {
        if (selectedCourseKey) {
            sessionStorage.setItem(SELECTED_COURSE_CACHE_KEY, selectedCourseKey);
            return;
        }
        sessionStorage.removeItem(SELECTED_COURSE_CACHE_KEY);
    }, [selectedCourseKey]);

    const loadCoursesWithStatus = async () => {
        setLoading(true);
        try {
            const response = await axios.get(
                `${API_BASE_URL}/api/student/courses-with-status?student_id=${username}`
            );
            setCoursesWithStatus(response.data || []);
        } catch (error) {
            console.error('Failed to load courses:', error);
            alert(TEXT.loadError);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (!selectedCourseKey) {
            return;
        }
        if (!groupedCourses.some((item) => item.key === selectedCourseKey)) {
            setSelectedCourseKey('');
            sessionStorage.removeItem(SELECTED_COURSE_CACHE_KEY);
        }
    }, [groupedCourses, selectedCourseKey]);

    const loadStudentProfileIfNeeded = async () => {
        if (!username) {
            return;
        }
        if (profile.real_name && profile.class_name && profile.major && profile.admission_year) {
            return;
        }
        try {
            const response = await axios.get(
                `${API_BASE_URL}/api/student/profile?student_id=${username}`
            );
            const data = response.data || {};
            const nextProfile = {
                real_name: data.real_name || '',
                class_name: data.class_name || '',
                student_id: data.student_id || username,
                major: data.major || data.organization || '',
                admission_year: data.admission_year || ''
            };
            setProfile(nextProfile);
            if (nextProfile.real_name) {
                localStorage.setItem('real_name', nextProfile.real_name);
            }
            if (nextProfile.class_name) {
                localStorage.setItem('class_name', nextProfile.class_name);
            }
            if (nextProfile.student_id) {
                localStorage.setItem('student_id', nextProfile.student_id);
            }
            if (nextProfile.major) {
                localStorage.setItem('major', nextProfile.major);
            }
            if (nextProfile.admission_year) {
                localStorage.setItem('admission_year', nextProfile.admission_year);
            }
        } catch (error) {
            console.error('Failed to load student profile:', error);
        }
    };

    const startOrContinueCourse = async (courseData) => {
        try {
            if (!courseData.student_exp_id) {
                await axios.post(
                    `${API_BASE_URL}/api/student-experiments/start/${courseData.course.id}?student_id=${username}`
                );
            }
            navigate(`/workspace/${courseData.course.id}`);
        } catch (error) {
            console.error('Failed to start experiment:', error);
            alert(TEXT.startError);
        }
    };

    const handlePdfFileChange = (studentExpId, file) => {
        setPdfFiles((prev) => ({
            ...prev,
            [studentExpId]: file || null
        }));
    };

    const submitExperiment = async (studentExpId) => {
        if (!window.confirm(TEXT.confirmSubmit)) {
            return;
        }

        try {
            await axios.post(
                `${API_BASE_URL}/api/student-experiments/${studentExpId}/submit`,
                { notebook_content: '' }
            );

            const selectedPdf = pdfFiles[studentExpId];
            if (selectedPdf) {
                const formData = new FormData();
                formData.append('file', selectedPdf);
                await axios.post(
                    `${API_BASE_URL}/api/student-experiments/${studentExpId}/pdf`,
                    formData,
                    { headers: { 'Content-Type': 'multipart/form-data' } }
                );
            }

            setPdfFiles((prev) => {
                const next = { ...prev };
                delete next[studentExpId];
                return next;
            });

            alert(selectedPdf ? TEXT.submitSuccessWithPdf : TEXT.submitSuccess);
            loadCoursesWithStatus();
        } catch (error) {
            console.error('Submit failed:', error);
            alert(`${TEXT.submitErrorPrefix}${error.response?.data?.detail || error.message}`);
        }
    };

    const handleLogout = () => {
        if (typeof onLogout === 'function') {
            onLogout();
            navigate('/login', { replace: true });
            return;
        }

        [
            'username',
            'userRole',
            'isLoggedIn',
            'real_name',
            'class_name',
            'student_id',
            'organization'
        ].forEach((key) => localStorage.removeItem(key));
        window.location.reload();
    };

    const handleProfileUpdated = useCallback((nextProfile) => {
        setProfile((prev) => ({ ...prev, ...nextProfile }));
    }, []);

    return (
        <div className="lab-page-shell">
            <header className="lab-topbar">
                <div className="lab-brand-block">
                    <div className="lab-brand-text">
                        <h1>{TEXT.platformTitle}</h1>
                        <p>{TEXT.platformSubTitle}</p>
                    </div>
                </div>

                <div className="lab-user-block">
                    <span className="lab-user-avatar">{(realName || username || 'U').slice(0, 1).toUpperCase()}</span>
                    <div className="lab-user-text">
                        <span className="lab-user-name">{`${TEXT.namePrefix}\uff1a${realName || username}`}</span>
                        <span className="lab-user-meta">{`${TEXT.classPrefix}\uff1a${classDisplay}  ${TEXT.studentIdPrefix}\uff1a${studentId}`}</span>
                    </div>
                    <button type="button" className="lab-logout-btn" onClick={handleLogout}>
                        {TEXT.logout}
                    </button>
                </div>
            </header>

            <div className="lab-main-layout">
                <aside className="lab-sidebar">
                    <div className="lab-sidebar-title">{TEXT.sidebarTitle}</div>
                    <button
                        type="button"
                        className={`lab-menu-item ${activeModule === 'profile' ? 'active' : ''}`}
                        onClick={() => setActiveModule('profile')}
                        aria-current={activeModule === 'profile' ? 'page' : undefined}
                    >
                        <span className="lab-menu-icon">
                            <ProfileModuleIcon />
                        </span>
                        <span>{TEXT.profileModuleLabel}</span>
                    </button>
                    <button
                        type="button"
                        className={`lab-menu-item ${activeModule === 'courses' ? 'active' : ''}`}
                        onClick={() => setActiveModule('courses')}
                        aria-current={activeModule === 'courses' ? 'page' : undefined}
                    >
                        <span className="lab-menu-icon">
                            <LabModuleIcon />
                        </span>
                        <span>{TEXT.moduleLabel}</span>
                    </button>
                    <button
                        type="button"
                        className={`lab-menu-item ${activeModule === 'resources' ? 'active' : ''}`}
                        onClick={() => setActiveModule('resources')}
                        aria-current={activeModule === 'resources' ? 'page' : undefined}
                    >
                        <span className="lab-menu-icon">
                            <ResourceModuleIcon />
                        </span>
                        <span>{TEXT.resourceModuleLabel}</span>
                    </button>
                </aside>

                <section className="lab-content-panel">
                    <div className="lab-breadcrumb">
                        {moduleLabel} / <strong>{breadcrumbLabel}</strong>
                    </div>
                    {activeModule === 'courses' ? (
                        <>
                            {loading ? (
                                <div className="lab-loading">{TEXT.loading}</div>
                            ) : groupedCourses.length === 0 ? (
                                <div className="lab-empty">{TEXT.empty}</div>
                            ) : !selectedCourse ? (
                                <div className="lab-card-grid">
                                    {groupedCourses.map((courseGroup) => {
                                        const iconMeta = getCourseIconMeta({
                                            title: courseGroup.courseName,
                                            description: courseGroup.description,
                                            tags: courseGroup.tags,
                                        });
                                        const total = courseGroup.experiments.length;
                                        const inProgress = courseGroup.experiments.filter((item) => normalizeStatus(item) === 'in-progress').length;
                                        const completed = courseGroup.experiments.filter((item) => {
                                            const statusKey = normalizeStatus(item);
                                            return statusKey === 'submitted' || statusKey === 'graded';
                                        }).length;

                                        return (
                                            <article className="lab-course-card" key={courseGroup.key}>
                                                <div className={`lab-course-logo ${iconMeta.themeClass}`} aria-hidden>
                                                    <span>{iconMeta.label}</span>
                                                </div>

                                                <h3>{courseGroup.courseName}</h3>
                                                <p className="lab-course-desc">{courseGroup.description || TEXT.noDescription}</p>
                                                <p className="lab-course-teacher">{`${TEXT.teacherPrefix}${courseGroup.teacherName}`}</p>

                                                <div className="lab-chip-row">
                                                    {(courseGroup.tags || []).map((tag) => (
                                                        <span key={tag} className="lab-chip">{tag}</span>
                                                    ))}
                                                </div>

                                                <div className="lab-course-summary">
                                                    {`${TEXT.courseCountPrefix}${total}  ${TEXT.inProgressCountPrefix}${inProgress}  ${TEXT.completedCountPrefix}${completed}`}
                                                </div>

                                                <button
                                                    type="button"
                                                    className="lab-open-btn"
                                                    onClick={() => setSelectedCourseKey(courseGroup.key)}
                                                >
                                                    {TEXT.chooseCourse}
                                                </button>
                                            </article>
                                        );
                                    })}
                                </div>
                            ) : (
                                <>
                                    <div className="lab-course-header">
                                        <button type="button" className="lab-back-btn" onClick={() => setSelectedCourseKey('')}>
                                            {TEXT.backToCourseLibrary}
                                        </button>
                                        <span className="lab-course-summary">
                                            {`${selectedCourse.courseName} · ${TEXT.courseCountPrefix}${selectedCourseExperiments.length}`}
                                        </span>
                                    </div>

                                    {selectedCourseExperiments.length === 0 ? (
                                        <div className="lab-empty">{TEXT.empty}</div>
                                    ) : (
                                        <div className="lab-card-grid">
                                            {selectedCourseExperiments.map((item) => {
                                                const statusMeta = getStatusMeta(item);
                                                const canSubmit = statusMeta.key === 'in-progress' && !!item.student_exp_id;
                                                const iconMeta = getCourseIconMeta(item.course);

                                                return (
                                                    <article className="lab-course-card" key={item.course.id}>
                                                        <div className={`lab-course-logo ${iconMeta.themeClass}`} aria-hidden>
                                                            <span>{iconMeta.label}</span>
                                                        </div>

                                                        <h3>{item.course.title}</h3>
                                                        <div className={`lab-status-badge ${statusMeta.className}`}>
                                                            {statusMeta.text}
                                                        </div>

                                                        <p className="lab-course-desc">{item.course.description || TEXT.noDescription}</p>
                                                        <p className="lab-course-teacher">{`${TEXT.teacherPrefix}${getTeacherName(item.course)}`}</p>

                                                        <div className="lab-chip-row">
                                                            {(item.course.tags || []).map((tag) => (
                                                                <span key={tag} className="lab-chip">{tag}</span>
                                                            ))}
                                                        </div>

                                                        <AttachmentPanel courseId={item.course.id} />

                                                        {item.score !== null && item.score !== undefined ? (
                                                            <div className="lab-score-box">{`${TEXT.scorePrefix}${item.score}`}</div>
                                                        ) : null}

                                                        <button
                                                            type="button"
                                                            className="lab-open-btn"
                                                            onClick={() => startOrContinueCourse(item)}
                                                        >
                                                            {TEXT.openExperiment}
                                                        </button>

                                                        {canSubmit ? (
                                                            <div className="lab-submit-panel">
                                                                <label htmlFor={`pdf-${item.student_exp_id}`}>{TEXT.uploadPdf}</label>
                                                                <input
                                                                    id={`pdf-${item.student_exp_id}`}
                                                                    type="file"
                                                                    accept=".pdf,application/pdf"
                                                                    onChange={(e) => handlePdfFileChange(item.student_exp_id, e.target.files?.[0])}
                                                                />
                                                                {pdfFiles[item.student_exp_id] ? (
                                                                    <p className="lab-pdf-name">{pdfFiles[item.student_exp_id].name}</p>
                                                                ) : null}
                                                                <button
                                                                    type="button"
                                                                    className="lab-submit-btn"
                                                                    onClick={() => submitExperiment(item.student_exp_id)}
                                                                >
                                                                    {TEXT.submitHomework}
                                                                </button>
                                                            </div>
                                                        ) : null}
                                                    </article>
                                                );
                                            })}
                                        </div>
                                    )}
                                </>
                            )}
                        </>
                    ) : activeModule === 'resources' ? (
                        <StudentResourcePanel username={username} />
                    ) : (
                        <StudentProfilePanel
                            username={username}
                            profile={profile}
                            onProfileUpdated={handleProfileUpdated}
                        />
                    )}
                </section>
            </div>
        </div>
    );
}

function AttachmentPanel({ courseId }) {
    const [attachments, setAttachments] = useState([]);
    const [showList, setShowList] = useState(false);

    const loadAttachments = async () => {
        if (showList) {
            setShowList(false);
            return;
        }

        try {
            const response = await axios.get(`${API_BASE_URL}/api/experiments/${courseId}/attachments`);
            setAttachments(response.data || []);
            setShowList(true);
        } catch (error) {
            console.error('Failed to load attachments:', error);
        }
    };

    return (
        <div className="lab-attachment-panel">
            <button type="button" className="lab-attachment-toggle" onClick={loadAttachments}>
                {showList ? TEXT.hideAttachment : TEXT.viewAttachment}
            </button>
            {showList ? (
                <ul className="lab-attachment-list">
                    {attachments.length === 0 ? (
                        <li className="lab-attachment-empty">{TEXT.noAttachment}</li>
                    ) : (
                        attachments.map((att) => (
                            <li key={att.id}>
                                <span>{att.filename}</span>
                                <button
                                    type="button"
                                    onClick={() => window.open(`${API_BASE_URL}/api/attachments/${att.id}/download-word`, '_blank')}
                                >
                                    {TEXT.download}
                                </button>
                            </li>
                        ))
                    )}
                </ul>
            ) : null}
        </div>
    );
}

function StudentResourcePanel({ username }) {
    const [resources, setResources] = useState([]);
    const [resourceLoading, setResourceLoading] = useState(false);
    const [searchName, setSearchName] = useState('');
    const [searchType, setSearchType] = useState('');
    const [totalCount, setTotalCount] = useState(0);
    const [detailVisible, setDetailVisible] = useState(false);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailData, setDetailData] = useState(null);

    const loadResources = async ({ name = searchName, fileType = searchType } = {}) => {
        setResourceLoading(true);
        try {
            const response = await axios.get(`${API_BASE_URL}/api/student/resources`, {
                params: {
                    student_id: username,
                    name: name || undefined,
                    file_type: fileType || undefined
                }
            });
            const payload = response.data || {};
            setResources(Array.isArray(payload.items) ? payload.items : []);
            setTotalCount(Number.isFinite(payload.total) ? payload.total : 0);
        } catch (error) {
            console.error('Failed to load student resources:', error);
            alert(TEXT.resourceLoadError);
        } finally {
            setResourceLoading(false);
        }
    };

    useEffect(() => {
        loadResources({ name: '', fileType: '' });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [username]);

    const openResourceDetail = async (resourceId) => {
        setDetailVisible(true);
        setDetailLoading(true);
        setDetailData(null);
        try {
            const response = await axios.get(`${API_BASE_URL}/api/student/resources/${resourceId}`, {
                params: { student_id: username }
            });
            setDetailData(response.data || null);
        } catch (error) {
            console.error('Failed to load resource detail:', error);
            alert(error.response?.data?.detail || TEXT.resourceDetailError);
            setDetailVisible(false);
        } finally {
            setDetailLoading(false);
        }
    };

    return (
        <div className="lab-resource-panel">
            <div className="lab-resource-toolbar">
                <div className="lab-resource-search">
                    <input
                        type="text"
                        placeholder={TEXT.resourceNamePlaceholder}
                        value={searchName}
                        onChange={(event) => setSearchName(event.target.value)}
                    />
                    <select value={searchType} onChange={(event) => setSearchType(event.target.value)}>
                        {RESOURCE_TYPE_OPTIONS.map((item) => (
                            <option key={item.value || 'all'} value={item.value}>
                                {item.label}
                            </option>
                        ))}
                    </select>
                    <button type="button" onClick={() => loadResources()}>
                        {TEXT.resourceSearch}
                    </button>
                </div>
                <span className="lab-resource-total">{`${TEXT.resourceTotalPrefix} ${totalCount} ${TEXT.resourceTotalSuffix}`}</span>
            </div>

            <div className="lab-resource-table-wrap">
                <table className="lab-resource-table">
                    <thead>
                        <tr>
                            <th>{TEXT.resourceFileName}</th>
                            <th>{TEXT.resourceFileType}</th>
                            <th>{TEXT.resourceCreatedAt}</th>
                            <th>{TEXT.operation}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {resourceLoading ? (
                            <tr>
                                <td colSpan="4" className="lab-resource-empty-row">{TEXT.resourceLoading}</td>
                            </tr>
                        ) : resources.length === 0 ? (
                            <tr>
                                <td colSpan="4" className="lab-resource-empty-row">{TEXT.resourceEmpty}</td>
                            </tr>
                        ) : (
                            resources.map((resource) => (
                                <tr key={resource.id}>
                                    <td>{resource.filename}</td>
                                    <td>{resource.file_type || '-'}</td>
                                    <td>{formatDateTime(resource.created_at)}</td>
                                    <td>
                                        <button
                                            type="button"
                                            className="lab-resource-link detail"
                                            onClick={() => openResourceDetail(resource.id)}
                                        >
                                            {TEXT.detail}
                                        </button>
                                        <button
                                            type="button"
                                            className="lab-resource-link download"
                                            onClick={() => window.open(`${API_BASE_URL}/api/student/resources/${resource.id}/download?student_id=${encodeURIComponent(username)}`, '_blank')}
                                        >
                                            {TEXT.download}
                                        </button>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {detailVisible ? (
                <div className="lab-resource-modal-mask" onClick={() => setDetailVisible(false)}>
                    <div className="lab-resource-modal" onClick={(event) => event.stopPropagation()}>
                        <div className="lab-resource-modal-header">
                            <h3>{detailData?.filename || TEXT.detail}</h3>
                            <button type="button" onClick={() => setDetailVisible(false)}>{TEXT.close}</button>
                        </div>
                        <div className="lab-resource-modal-body">
                            {detailLoading ? (
                                <div className="lab-resource-preview-empty">{TEXT.resourceLoading}</div>
                            ) : (
                                <ResourcePreviewContent
                                    detailData={detailData}
                                    accessQueryKey="student_id"
                                    accessQueryValue={username}
                                    loadingText={TEXT.resourceLoading}
                                    emptyText={TEXT.noPreviewContent}
                                    unsupportedText={TEXT.unsupportedPreview}
                                />
                            )}
                        </div>
                        {detailData ? (
                            <div className="lab-resource-modal-footer">
                                <button
                                    type="button"
                                    className="lab-resource-download-btn"
                                    onClick={() => window.open(`${API_BASE_URL}/api/student/resources/${detailData.id}/download?student_id=${encodeURIComponent(username)}`, '_blank')}
                                >
                                    {TEXT.download}
                                </button>
                            </div>
                        ) : null}
                    </div>
                </div>
            ) : null}
        </div>
    );
}

function StudentProfilePanel({ username, profile, onProfileUpdated }) {
    const [loading, setLoading] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [securitySubmitting, setSecuritySubmitting] = useState(false);
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [securityQuestion, setSecurityQuestion] = useState('');
    const [securityAnswer, setSecurityAnswer] = useState('');
    const [securityQuestionSet, setSecurityQuestionSet] = useState(false);

    useEffect(() => {
        let cancelled = false;

        const loadProfile = async () => {
            if (!username) {
                return;
            }
            setLoading(true);
            try {
                const response = await axios.get(
                    `${API_BASE_URL}/api/student/profile?student_id=${username}`
                );
                if (cancelled) {
                    return;
                }
                const data = response.data || {};
                const nextProfile = {
                    real_name: data.real_name || '',
                    class_name: data.class_name || '',
                    student_id: data.student_id || username,
                    major: data.major || data.organization || '',
                    admission_year: data.admission_year || '',
                    admission_year_label: data.admission_year_label || '',
                    security_question: data.security_question || '',
                    security_question_set: Boolean(data.security_question_set)
                };
                if (onProfileUpdated) {
                    onProfileUpdated(nextProfile);
                }
                setSecurityQuestion(nextProfile.security_question || '');
                setSecurityQuestionSet(Boolean(nextProfile.security_question_set));
                localStorage.setItem('real_name', nextProfile.real_name || '');
                localStorage.setItem('class_name', nextProfile.class_name || '');
                localStorage.setItem('student_id', nextProfile.student_id || '');
                localStorage.setItem('major', nextProfile.major || '');
                localStorage.setItem('admission_year', nextProfile.admission_year || '');
            } catch (error) {
                if (!cancelled) {
                    console.error('Failed to load student profile:', error);
                    alert(TEXT.profileLoadError);
                }
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        };

        loadProfile();
        return () => {
            cancelled = true;
        };
    }, [onProfileUpdated, username]);

    const handleChangePassword = async (event) => {
        event.preventDefault();
        if (newPassword.length < 6) {
            alert(TEXT.passwordTooShort);
            return;
        }
        if (newPassword !== confirmPassword) {
            alert(TEXT.passwordMismatch);
            return;
        }

        setSubmitting(true);
        try {
            const response = await axios.post(`${API_BASE_URL}/api/student/profile/change-password`, {
                student_id: username,
                old_password: currentPassword,
                new_password: newPassword
            });
            alert(response.data?.message || TEXT.passwordChangeSuccess);
            setCurrentPassword('');
            setNewPassword('');
            setConfirmPassword('');
        } catch (error) {
            alert(`${TEXT.passwordChangeErrorPrefix}${error.response?.data?.detail || error.message}`);
        } finally {
            setSubmitting(false);
        }
    };

    const handleSaveSecurityQuestion = async (event) => {
        event.preventDefault();
        const normalizedQuestion = String(securityQuestion || '').trim();
        const normalizedAnswer = String(securityAnswer || '').trim();
        if (normalizedQuestion.length < 2) {
            alert('密保问题至少2个字符');
            return;
        }
        if (normalizedAnswer.length < 2) {
            alert('密保答案至少2个字符');
            return;
        }

        setSecuritySubmitting(true);
        try {
            const response = await axios.post(`${API_BASE_URL}/api/student/profile/security-question`, {
                student_id: username,
                security_question: normalizedQuestion,
                security_answer: normalizedAnswer
            });
            alert(response.data?.message || '密保问题已保存');
            setSecurityQuestion(normalizedQuestion);
            setSecurityQuestionSet(true);
            setSecurityAnswer('');
        } catch (error) {
            alert(`保存密保失败：${error.response?.data?.detail || error.message}`);
        } finally {
            setSecuritySubmitting(false);
        }
    };

    const majorDisplay = profile?.major || profile?.organization || '-';
    const classDisplay = profile?.class_name || '-';
    const admissionYearDisplay = profile?.admission_year_label || profile?.admission_year || '-';
    const studentIdDisplay = profile?.student_id || username || '-';

    return (
        <div className="lab-profile-panel">
            <div className="lab-profile-card">
                <h3>{TEXT.profileInfoTitle}</h3>
                {loading ? (
                    <div className="lab-profile-loading">{TEXT.profileLoading}</div>
                ) : (
                    <div className="lab-profile-grid">
                        <div className="lab-profile-item">
                            <span>{TEXT.studentIdPrefix}</span>
                            <strong>{studentIdDisplay}</strong>
                        </div>
                        <div className="lab-profile-item">
                            <span>{TEXT.majorPrefix}</span>
                            <strong>{majorDisplay || TEXT.profileNotAvailable}</strong>
                        </div>
                        <div className="lab-profile-item">
                            <span>{TEXT.classPrefix}</span>
                            <strong>{classDisplay || TEXT.profileNotAvailable}</strong>
                        </div>
                        <div className="lab-profile-item">
                            <span>{TEXT.admissionYearPrefix}</span>
                            <strong>{admissionYearDisplay || TEXT.profileNotAvailable}</strong>
                        </div>
                    </div>
                )}
            </div>

            <div className="lab-profile-card lab-profile-card--security">
                <h3>账号与安全</h3>
                <div className="lab-security-layout">
                    <section className="lab-security-block">
                        <div className="lab-security-head">
                            <h4>{TEXT.profilePasswordTitle}</h4>
                            <p>建议定期更新密码，保障账号安全。</p>
                        </div>
                        <form className="lab-password-form lab-security-form" onSubmit={handleChangePassword}>
                            <label htmlFor="current-password">{TEXT.currentPassword}</label>
                            <input
                                id="current-password"
                                type="password"
                                autoComplete="current-password"
                                value={currentPassword}
                                onChange={(event) => setCurrentPassword(event.target.value)}
                                required
                            />

                            <label htmlFor="new-password">{TEXT.newPassword}</label>
                            <input
                                id="new-password"
                                type="password"
                                autoComplete="new-password"
                                value={newPassword}
                                onChange={(event) => setNewPassword(event.target.value)}
                                minLength={6}
                                required
                            />

                            <label htmlFor="confirm-password">{TEXT.confirmPassword}</label>
                            <input
                                id="confirm-password"
                                type="password"
                                autoComplete="new-password"
                                value={confirmPassword}
                                onChange={(event) => setConfirmPassword(event.target.value)}
                                minLength={6}
                                required
                            />

                            <p className="lab-password-hint">{TEXT.passwordLengthHint}</p>
                            <button type="submit" className="lab-password-btn" disabled={submitting}>
                                {submitting ? `${TEXT.savePassword}...` : TEXT.savePassword}
                            </button>
                        </form>
                    </section>

                    <section className="lab-security-block">
                        <div className="lab-security-head">
                            <h4>密保设置</h4>
                            <p>{securityQuestionSet ? '已启用密保找回。' : '首次登录后建议尽快设置密保。'}</p>
                        </div>
                        <form className="lab-password-form lab-security-form lab-security-form--qa" onSubmit={handleSaveSecurityQuestion}>
                            <label htmlFor="security-question">密保问题</label>
                            <input
                                id="security-question"
                                type="text"
                                value={securityQuestion}
                                onChange={(event) => setSecurityQuestion(event.target.value)}
                                placeholder="例如：我最喜欢的老师名字？"
                                required
                            />

                            <label htmlFor="security-answer">密保答案</label>
                            <input
                                id="security-answer"
                                type="text"
                                value={securityAnswer}
                                onChange={(event) => setSecurityAnswer(event.target.value)}
                                placeholder="请输入密保答案"
                                required
                            />

                            <p className="lab-password-hint">
                                {securityQuestionSet
                                    ? '已设置密保问题，可在登录页通过密保找回密码。'
                                    : '首次登录后建议先设置密保问题，避免忘记密码无法自助找回。'}
                            </p>
                            <button type="submit" className="lab-password-btn" disabled={securitySubmitting}>
                                {securitySubmitting ? '保存中...' : (securityQuestionSet ? '更新密保问题' : '保存密保问题')}
                            </button>
                        </form>
                    </section>
                </div>
            </div>
        </div>
    );
}

function LabModuleIcon() {
    return (
        <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
            <path d="M6.5 5H3.5C2.95 5 2.5 5.45 2.5 6V18C2.5 18.55 2.95 19 3.5 19H20.5C21.05 19 21.5 18.55 21.5 18V6C21.5 5.45 21.05 5 20.5 5H17.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
            <path d="M9.2 5V4.2C9.2 3.54 9.74 3 10.4 3H13.6C14.26 3 14.8 3.54 14.8 4.2V5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
            <rect x="7.2" y="9" width="9.6" height="8" rx="1.6" stroke="currentColor" strokeWidth="1.8"/>
            <path d="M11.2 12.9H12.8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
        </svg>
    );
}

function ResourceModuleIcon() {
    return (
        <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
            <rect x="4" y="3.5" width="16" height="17" rx="2.2" stroke="currentColor" strokeWidth="1.8"/>
            <path d="M8 8H16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
            <path d="M8 12H16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
            <path d="M8 16H12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
        </svg>
    );
}

function ProfileModuleIcon() {
    return (
        <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
            <circle cx="12" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.8"/>
            <path d="M5.5 18.5C6.6 15.9 9 14.4 12 14.4C15 14.4 17.4 15.9 18.5 18.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
            <rect x="3.5" y="3.5" width="17" height="17" rx="2.4" stroke="currentColor" strokeWidth="1.4"/>
        </svg>
    );
}

export default StudentCourseList;


