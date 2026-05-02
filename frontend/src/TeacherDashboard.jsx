
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import TeacherReview from './TeacherReview';
import TeacherUserManagement from './TeacherUserManagement';
import ResourceFileManagement from './ResourceFileManagement';
import TeacherAIModule from './TeacherAIModule';
import AdminStatsCenter from './AdminStatsCenter';
import AdminResourceControl from './AdminResourceControl';
import {
  closePendingWorkspaceWindow,
  getWorkspaceLaunchInfo,
  navigatePendingWorkspaceWindow,
  openPendingWorkspaceWindow,
  persistJupyterTokenFromUrl,
} from './jupyterAuth';
import './TeacherDashboard.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';
const DEFAULT_RESOURCE_TIERS = [
  { key: 'small', label: '小实验', cpu_limit: 1, memory_limit: '2G', storage_limit: '2G' },
  { key: 'medium', label: '普通实验', cpu_limit: 1, memory_limit: '4G', storage_limit: '4G' },
  { key: 'large', label: '大项目', cpu_limit: 2, memory_limit: '8G', storage_limit: '8G' },
  { key: 'xlarge', label: '超大项目', cpu_limit: 4, memory_limit: '16G', storage_limit: '20G' },
];

function normalizeResourceTier(value) {
  const key = String(value || '').trim().toLowerCase();
  return DEFAULT_RESOURCE_TIERS.some((item) => item.key === key) ? key : 'small';
}

function resourceTierLabel(item) {
  if (!item) return '小实验：1 CPU / 2G 内存';
  return `${item.label || item.key}：${item.cpu_limit} CPU / ${item.memory_limit} 内存`;
}
const TEACHER_COURSE_RESUME_KEY = 'teacherCourseResumeId';
const JUPYTERHUB_URL = process.env.REACT_APP_JUPYTERHUB_URL || '';
const DEFAULT_JUPYTERHUB_URL = `${window.location.origin}/jupyter/hub/home`;
const DEFAULT_JUPYTERHUB_HEALTH_URL = `${window.location.origin}/jupyter/hub/health`;
const LEGACY_JUPYTERHUB_URL = `${window.location.protocol}//${window.location.hostname}:8003/jupyter/hub/home`;
const TABS = [
  { key: 'courses', label: '课程库', tip: '课程与实验管理', Icon: CourseTabIcon },
  { key: 'progress', label: '学生进度', tip: '查看完成情况', Icon: ProgressTabIcon },
  { key: 'review', label: '提交审阅', tip: '批改学生作业', Icon: ReviewTabIcon },
  { key: 'users', label: '用户管理', tip: '班级和学生管理', Icon: UserTabIcon },
  { key: 'resources', label: '资源文件', tip: '平台资源管理', Icon: ResourceTabIcon },
  { key: 'profile', label: '个人中心', tip: '账号与安全设置', Icon: ProfileTabIcon },
  { key: 'ai', label: 'AI功能', tip: '模型与密钥配置', Icon: AITabIcon },
];

const ADMIN_STATS_TAB = {
  key: 'admin-stats',
  label: '统计中心',
  tip: '数据统计与可视化',
  Icon: AdminControlTabIcon,
};

const ADMIN_TAB = {
  key: 'admin-resource',
  label: '资源监控',
  tip: '容器配额与日志',
  Icon: AdminControlTabIcon,
};

function formatDate(v) {
  if (!v) return '-';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return '-';
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function formatDateTime(v) {
  if (!v) return '-';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return '-';
  return `${formatDate(v)} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function progressStatusKey(status) {
  const v = String(status || '').toLowerCase();
  if (v.includes('评分') || v.includes('graded')) return 'graded';
  if (v.includes('提交') || v.includes('submit')) return 'submitted';
  if (v.includes('进行') || v.includes('progress')) return 'in-progress';
  return 'not-started';
}

function isCompleted(status) {
  const key = progressStatusKey(status);
  return key === 'submitted' || key === 'graded';
}

function getErrorMessage(error, fallback) {
  if (error?.response?.status === 413) return '附件过大，请压缩后重试（当前限制 200MB）';
  return error?.response?.data?.detail || fallback;
}

function parseTags(v) {
  return String(v || '')
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean);
}

function normalizeStringArray(values) {
  if (!Array.isArray(values)) return [];
  const seen = new Set();
  const result = [];
  values.forEach((item) => {
    const normalized = String(item || '').trim();
    const key = normalized.toLowerCase();
    if (!normalized || seen.has(key)) return;
    seen.add(key);
    result.push(normalized);
  });
  return result;
}

function normalizePublishScope(value) {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'class' || normalized === 'student' || normalized === 'all') return normalized;
  return 'all';
}

function normalizeEditorPublishScope(value) {
  const scope = normalizePublishScope(value);
  return scope === 'student' ? 'student' : 'class';
}

function courseIconMeta(item) {
  const text = `${item?.name || ''} ${item?.title || ''} ${item?.description || ''} ${(item?.tags || []).join(' ')}`.toLowerCase();
  if (text.includes('vision') || text.includes('自动驾驶') || text.includes('视觉')) return { label: 'CV', cls: 'theme-vision' };
  if (text.includes('matplotlib') || text.includes('可视化') || text.includes('图表')) return { label: 'PLT', cls: 'theme-plot' };
  if (text.includes('pandas')) return { label: 'PD', cls: 'theme-pandas' };
  if (text.includes('numpy')) return { label: 'NP', cls: 'theme-numpy' };
  if (text.includes('machine learning') || text.includes('scikit') || text.includes('机器学习')) return { label: 'ML', cls: 'theme-ml' };
  if (text.includes('python')) return { label: 'PY', cls: 'theme-python' };
  return { label: 'LAB', cls: 'theme-generic' };
}

function resolveCourseName(item) {
  const explicit = String(item?.course_name || '').trim();
  if (explicit) return explicit;
  const path = String(item?.notebook_path || '').trim();
  const first = path.split('/').filter(Boolean)[0] || '';
  if (first && first.toLowerCase() !== 'course') return first;
  return 'Python程序设计';
}

function normalizeTeacherCourses(items) {
  if (!Array.isArray(items)) return [];
  const hasCourseShape = items.some((item) => Array.isArray(item?.experiments) || item?.name);

  if (hasCourseShape) {
    return items
      .map((item) => {
        const experiments = Array.isArray(item?.experiments)
          ? [...item.experiments].sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())
          : [];
        return {
          id: item?.id,
          name: item?.name || '未命名课程',
          description: item?.description || '',
          created_by: item?.created_by || '',
          created_at: item?.created_at || null,
          updated_at: item?.updated_at || item?.latest_experiment_at || item?.created_at || null,
          experiment_count: Number(item?.experiment_count ?? experiments.length),
          published_count: Number(item?.published_count ?? experiments.filter((exp) => exp?.published).length),
          tags: Array.isArray(item?.tags) ? item.tags : [],
          experiments,
        };
      })
      .sort((a, b) => new Date(b.updated_at || b.created_at || 0).getTime() - new Date(a.updated_at || a.created_at || 0).getTime());
  }

  const grouped = new Map();
  items.forEach((exp) => {
    const name = resolveCourseName(exp);
    const key = name.toLowerCase();
    const cur = grouped.get(key) || {
      id: `legacy-${key}`,
      name,
      description: '',
      created_by: exp?.created_by || '',
      created_at: exp?.created_at || null,
      updated_at: exp?.created_at || null,
      experiment_count: 0,
      published_count: 0,
      tags: new Set(),
      experiments: [],
    };
    cur.experiments.push(exp);
    cur.experiment_count += 1;
    if (exp?.published) cur.published_count += 1;
    (exp?.tags || []).forEach((tag) => tag && cur.tags.add(tag));
    if ((exp?.created_at || '') > (cur.updated_at || '')) cur.updated_at = exp.created_at;
    grouped.set(key, cur);
  });

  return Array.from(grouped.values())
    .map((item) => ({
      ...item,
      tags: Array.from(item.tags),
      experiments: item.experiments.sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()),
    }))
    .sort((a, b) => new Date(b.updated_at || 0).getTime() - new Date(a.updated_at || 0).getTime());
}

function flattenExperiments(courses) {
  const rows = [];
  (courses || []).forEach((course) => {
    (course?.experiments || []).forEach((exp) => rows.push(exp));
  });
  return rows;
}

function TeacherDashboard({ username, userRole, onLogout }) {
  const navigate = useNavigate();
  const isAdmin = userRole === 'admin' || String(username || '').trim() === 'admin';
  const tabs = useMemo(() => (isAdmin ? [...TABS, ADMIN_STATS_TAB, ADMIN_TAB] : TABS), [isAdmin]);
  const [activeTab, setActiveTab] = useState(isAdmin ? 'admin-stats' : 'courses');
  const [courses, setCourses] = useState([]);
  const [progress, setProgress] = useState([]);
  const [submissions, setSubmissions] = useState([]);
  const [loadingCourses, setLoadingCourses] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState(false);
  const [loadingSubmissions, setLoadingSubmissions] = useState(false);

  const [showCourseEditor, setShowCourseEditor] = useState(false);
  const [editingCourse, setEditingCourse] = useState(null);
  const [showExperimentEditor, setShowExperimentEditor] = useState(false);
  const [editingExperiment, setEditingExperiment] = useState(null);
  const [targetCourse, setTargetCourse] = useState(null);
  const [resourceTiers, setResourceTiers] = useState(DEFAULT_RESOURCE_TIERS);

  const currentTab = tabs.find((item) => item.key === activeTab) || tabs[0];

  const loadCourses = useCallback(async () => {
    setLoadingCourses(true);
    try {
      const res = await axios.get(`${API_BASE_URL}/api/teacher/courses`, { params: { teacher_username: username } });
      setCourses(normalizeTeacherCourses(res.data));
    } catch (error) {
      console.error('loadCourses failed', error);
      alert(getErrorMessage(error, '加载课程库失败'));
      setCourses([]);
    } finally {
      setLoadingCourses(false);
    }
  }, [username]);

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API_BASE_URL}/api/resource-tiers`)
      .then((res) => {
        if (cancelled) return;
        const tiers = Array.isArray(res.data) && res.data.length > 0 ? res.data : DEFAULT_RESOURCE_TIERS;
        setResourceTiers(tiers);
      })
      .catch(() => {
        if (!cancelled) setResourceTiers(DEFAULT_RESOURCE_TIERS);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const loadProgress = useCallback(async () => {
    setLoadingProgress(true);
    try {
      const res = await axios.get(`${API_BASE_URL}/api/teacher/progress`, { params: { teacher_username: username } });
      setProgress(Array.isArray(res.data) ? res.data : []);
    } catch (error) {
      console.error('loadProgress failed', error);
      alert(getErrorMessage(error, '加载学生进度失败'));
      setProgress([]);
    } finally {
      setLoadingProgress(false);
    }
  }, [username]);

  const loadSubmissions = useCallback(async () => {
    setLoadingSubmissions(true);
    try {
      const source = courses.length > 0
        ? courses
        : normalizeTeacherCourses((await axios.get(`${API_BASE_URL}/api/teacher/courses`, { params: { teacher_username: username } })).data || []);
      const experimentIds = source.flatMap((course) => (course?.experiments || []).map((exp) => exp.id)).filter(Boolean);
      if (experimentIds.length === 0) {
        setSubmissions([]);
        return;
      }

      const lists = await Promise.all(
        experimentIds.map((id) =>
          axios
            .get(`${API_BASE_URL}/api/teacher/experiments/${id}/submissions`)
            .then((res) => (Array.isArray(res.data) ? res.data : []))
            .catch(() => [])
        )
      );
      setSubmissions(lists.flat());
    } catch (error) {
      console.error('loadSubmissions failed', error);
      alert(getErrorMessage(error, '加载提交记录失败'));
      setSubmissions([]);
    } finally {
      setLoadingSubmissions(false);
    }
  }, [courses, username]);

  useEffect(() => {
    loadCourses();
    loadProgress();
  }, [loadCourses, loadProgress]);

  useEffect(() => {
    if (activeTab === 'review') loadSubmissions();
  }, [activeTab, loadSubmissions]);

  const handleGrade = async (submissionId, score, comment) => {
    try {
      await axios.post(`${API_BASE_URL}/api/teacher/grade/${submissionId}`, null, {
        params: { score, comment, teacher_username: username },
      });
      alert('评分成功');
      await loadSubmissions();
    } catch (error) {
      console.error('grade failed', error);
      alert(getErrorMessage(error, '评分失败'));
    }
  };

  const handleCreateCourse = async (formData) => {
    const payload = {
      name: String(formData.name || '').trim(),
      description: String(formData.description || '').trim(),
      teacher_username: username,
    };
    const res = await axios.post(`${API_BASE_URL}/api/teacher/courses`, payload);
    await loadCourses();
    return res.data;
  };

  const handleUpdateCourse = async (course, formData) => {
    const payload = {
      name: String(formData.name || '').trim(),
      description: String(formData.description || '').trim(),
      teacher_username: username,
    };
    const res = await axios.patch(`${API_BASE_URL}/api/teacher/courses/${course.id}`, payload);
    await loadCourses();
    return res.data;
  };

  const handleDeleteCourse = async (course) => {
    const total = Number(course?.experiment_count ?? course?.experiments?.length ?? 0);
    const hasExperiments = total > 0;
    const ok = hasExperiments
      ? window.confirm(`课程「${course?.name || '-'}」下有 ${total} 个实验，删除课程会一并删除实验。是否继续？`)
      : window.confirm(`确定删除课程「${course?.name || '-'}」吗？`);
    if (!ok) return;

    try {
      await axios.delete(`${API_BASE_URL}/api/teacher/courses/${course.id}`, {
        params: { teacher_username: username, delete_experiments: hasExperiments },
      });
      await loadCourses();
      alert('课程删除成功');
    } catch (error) {
      console.error('delete course failed', error);
      alert(getErrorMessage(error, '删除课程失败'));
    }
  };

  const handleToggleCoursePublish = async (course) => {
    const total = Number(course?.experiment_count ?? course?.experiments?.length ?? 0);
    if (total <= 0) {
      alert('课程下暂无实验，无法发布');
      return;
    }

    const currentPublished = Number(course?.published_count ?? 0) === total;
    try {
      await axios.patch(`${API_BASE_URL}/api/teacher/courses/${course.id}/publish`, null, {
        params: { teacher_username: username, published: !currentPublished },
      });
      await loadCourses();
      alert(currentPublished ? '已取消发布课程' : '课程已发布');
    } catch (error) {
      console.error('toggle course publish failed', error);
      alert(getErrorMessage(error, '课程发布操作失败'));
    }
  };

  const buildExperimentPayload = (experiment, formData, course) => {
    const tierKey = normalizeResourceTier(formData.resource_tier ?? experiment.resource_tier ?? experiment.resources?.resource_tier);
    const tier = resourceTiers.find((item) => item.key === tierKey) || DEFAULT_RESOURCE_TIERS[0];
    return {
      ...experiment,
      title: formData.title,
      description: formData.description,
      difficulty: formData.difficulty,
      tags: parseTags(formData.tags),
      notebook_path: formData.notebook_path,
      published: Boolean(formData.published),
      publish_scope: normalizePublishScope(formData.publish_scope ?? experiment.publish_scope),
      target_class_names: normalizeStringArray(formData.target_class_names ?? experiment.target_class_names),
      target_student_ids: normalizeStringArray(formData.target_student_ids ?? experiment.target_student_ids),
      course_id: course.id,
      course_name: course.name,
      created_by: experiment.created_by || username,
      created_at: experiment.created_at || new Date().toISOString(),
      resource_tier: tierKey,
      resources: {
        ...(experiment.resources || {}),
        cpu: Number(tier.cpu_limit) || 1,
        memory: tier.memory_limit || '2G',
        storage: tier.storage_limit || '2G',
        resource_tier: tierKey,
      },
    };
  };

  const handleCreateExperiment = async (course, formData) => {
    const tierKey = normalizeResourceTier(formData.resource_tier);
    const tier = resourceTiers.find((item) => item.key === tierKey) || DEFAULT_RESOURCE_TIERS[0];
    const payload = {
      title: formData.title,
      description: formData.description,
      difficulty: formData.difficulty,
      tags: parseTags(formData.tags),
      notebook_path: formData.notebook_path,
      published: Boolean(formData.published),
      publish_scope: normalizePublishScope(formData.publish_scope),
      target_class_names: normalizeStringArray(formData.target_class_names),
      target_student_ids: normalizeStringArray(formData.target_student_ids),
      course_id: course.id,
      course_name: course.name,
      created_by: course?.created_by || username,
      resource_tier: tierKey,
      resources: {
        cpu: Number(tier.cpu_limit) || 1,
        memory: tier.memory_limit || '2G',
        storage: tier.storage_limit || '2G',
        resource_tier: tierKey,
      },
    };
    const res = await axios.post(`${API_BASE_URL}/api/experiments`, payload);
    await loadCourses();
    return res.data;
  };

  const handleUpdateExperiment = async (course, experiment, formData) => {
    const payload = buildExperimentPayload(experiment, formData, course);
    const res = await axios.put(`${API_BASE_URL}/api/experiments/${experiment.id}`, payload);
    await loadCourses();
    return res.data;
  };

  const handleToggleExperimentPublish = async (course, experiment) => {
    try {
      const payload = buildExperimentPayload(
        experiment,
        {
          title: experiment.title || '',
          description: experiment.description || '',
          difficulty: experiment.difficulty || '初级',
          tags: Array.isArray(experiment.tags) ? experiment.tags.join(', ') : '',
          notebook_path: experiment.notebook_path || '',
          published: !experiment.published,
        },
        course
      );
      await axios.put(`${API_BASE_URL}/api/experiments/${experiment.id}`, payload);
      await loadCourses();
      alert(experiment.published ? '已取消发布实验' : '实验已发布');
    } catch (error) {
      console.error('toggle experiment publish failed', error);
      alert(getErrorMessage(error, '实验发布操作失败'));
    }
  };

  const handleDeleteExperiment = async (experiment) => {
    if (!window.confirm(`确定删除实验「${experiment?.title || experiment?.id || '-'}」吗？`)) return;
    try {
      await axios.delete(`${API_BASE_URL}/api/experiments/${experiment.id}`);
      await loadCourses();
      alert('实验删除成功');
    } catch (error) {
      console.error('delete experiment failed', error);
      alert(getErrorMessage(error, '删除实验失败'));
    }
  };

  const experiments = useMemo(() => flattenExperiments(courses), [courses]);
  const courseMap = useMemo(() => {
    const map = {};
    experiments.forEach((exp) => {
      map[exp.id] = exp;
    });
    return map;
  }, [experiments]);

  const courseCount = courses.length;
  const experimentCount = experiments.length;
  const publishedCount = useMemo(() => experiments.filter((item) => item.published).length, [experiments]);

  const logout = () => {
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
      'organization',
    ].forEach((key) => localStorage.removeItem(key));
    window.location.reload();
  };

  const openWorkspace = async (preferredWorkspace = 'lab') => {
    const pendingWindow = openPendingWorkspaceWindow(preferredWorkspace === 'code' ? 'Opening VS Code...' : 'Opening JupyterLab...');
    try {
      const resp = await axios.get(`${API_BASE_URL}/api/jupyterhub/auto-login-url`, { params: { username } });
      const launch = getWorkspaceLaunchInfo(resp?.data, preferredWorkspace);
      const preferredKey = String(preferredWorkspace || '').trim().toLowerCase();
      const preferredUrl = launch.workspaceUrls?.[preferredKey] || '';
      if (preferredKey === 'code' && !preferredUrl) {
        closePendingWorkspaceWindow(pendingWindow);
        alert('当前环境未启用 VS Code 工作区。');
        return;
      }
      const resolvedUrl = preferredUrl || launch.selectedUrl;
      if (resolvedUrl) {
        const launchUrl = persistJupyterTokenFromUrl(resolvedUrl);
        const opened = navigatePendingWorkspaceWindow(pendingWindow, launchUrl);
        if (!opened) {
          alert('浏览器拦截了新窗口，请允许弹出窗口后重试。');
        }
        return;
      }
      if (preferredWorkspace === 'code') {
        closePendingWorkspaceWindow(pendingWindow);
        alert('当前环境未启用 VS Code 工作区。');
        return;
      }
    } catch (err) {
      // fallback to below
    }

    if (preferredWorkspace === 'code') {
      closePendingWorkspaceWindow(pendingWindow);
      alert('当前环境未启用 VS Code 工作区。');
      return;
    }

    if (JUPYTERHUB_URL) {
      navigatePendingWorkspaceWindow(pendingWindow, JUPYTERHUB_URL);
      return;
    }

    try {
      const resp = await fetch(DEFAULT_JUPYTERHUB_HEALTH_URL, { method: 'GET', credentials: 'omit' });
      if (resp.ok) {
        navigatePendingWorkspaceWindow(pendingWindow, DEFAULT_JUPYTERHUB_URL);
        return;
      }
    } catch (err) {
      // ignore
    }

    navigatePendingWorkspaceWindow(pendingWindow, LEGACY_JUPYTERHUB_URL);
  };

  const openJupyterHub = () => openWorkspace('lab');
  const openCodeServer = () => openWorkspace('code');

  return (
    <div className="teacher-lab-shell">
      <header className="teacher-lab-topbar">
        <div className="teacher-lab-brand">
          <h1>福州理工学院AI编程实践教学平台</h1>
          <p>教师管理端 / AI Programming Practice Teaching Platform</p>
        </div>
        <div className="teacher-lab-user">
          <span className="teacher-lab-avatar">{(username || 'T').slice(0, 1).toUpperCase()}</span>
          <div className="teacher-lab-user-text">
            <span className="teacher-lab-user-name">教师账号：{username}</span>
          <span className="teacher-lab-user-role">角色：{isAdmin ? '系统管理员' : '教师管理员'}</span>
          </div>
          <button type="button" className="teacher-lab-jhub" onClick={openJupyterHub}>进入 JupyterHub</button>
          <button type="button" className="teacher-lab-jhub teacher-lab-jhub-code" onClick={openCodeServer}>进入 VS Code</button>
          <button type="button" className="teacher-lab-jhub teacher-lab-jhub-tutor" onClick={() => navigate('/deeptutor/')}>DeepTutor</button>
          <button type="button" className="teacher-lab-logout" onClick={logout}>退出</button>
        </div>
      </header>

      <div className="teacher-lab-layout">
        <aside className="teacher-lab-sidebar">
          <div className="teacher-lab-sidebar-title">模块</div>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`teacher-lab-menu-item ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.key)}
            >
              <span className="teacher-lab-menu-icon"><tab.Icon /></span>
              <span className="teacher-lab-menu-text"><strong>{tab.label}</strong><small>{tab.tip}</small></span>
            </button>
          ))}
        </aside>

        <section className="teacher-lab-content">
          <div className="teacher-lab-breadcrumb">教师端 / <strong>{currentTab.label}</strong></div>

          {activeTab === 'courses' ? (
            <>
              <div className="teacher-lab-toolbar">
                <div className="teacher-lab-toolbar-stats">
                  <span>课程总数：{courseCount}</span>
                  <span>实验总数：{experimentCount}</span>
                  <span>已发布实验：{publishedCount}</span>
                </div>
                <button type="button" className="teacher-lab-create-btn" onClick={() => {
                  setEditingCourse(null);
                  setShowCourseEditor(true);
                }}>
                  + 创建课程
                </button>
              </div>

              <CoursePanel
                courses={courses}
                loading={loadingCourses}
                onCreateExperiment={(course) => {
                  setTargetCourse(course);
                  setEditingExperiment(null);
                  setShowExperimentEditor(true);
                }}
                onEditCourse={(course) => {
                  setEditingCourse(course);
                  setShowCourseEditor(true);
                }}
                onPublishCourse={handleToggleCoursePublish}
                onDeleteCourse={handleDeleteCourse}
                onOpenExperiment={(experiment) => navigate(`/workspace/${experiment.id}`)}
                onEditExperiment={(course, experiment) => {
                  setTargetCourse(course);
                  setEditingExperiment(experiment);
                  setShowExperimentEditor(true);
                }}
                onPublishExperiment={handleToggleExperimentPublish}
                onDeleteExperiment={handleDeleteExperiment}
              />
            </>
          ) : null}

          {activeTab === 'progress' ? <ProgressPanel progress={progress} loading={loadingProgress} courseMap={courseMap} /> : null}

          {activeTab === 'review' ? (
            <div className="teacher-lab-section">
              <TeacherReview username={username} submissions={submissions} loading={loadingSubmissions} onGrade={handleGrade} />
            </div>
          ) : null}

          {activeTab === 'users' ? (
            <div className="teacher-lab-section">
              <TeacherUserManagement username={username} userRole={userRole} />
            </div>
          ) : null}

          {activeTab === 'resources' ? (
            <div className="teacher-lab-section">
              <ResourceFileManagement username={username} />
            </div>
          ) : null}

          {activeTab === 'profile' ? (
            <div className="teacher-lab-section">
              <TeacherProfilePanel username={username} userRole={userRole} />
            </div>
          ) : null}

          {activeTab === 'ai' ? (
            <div className="teacher-lab-section">
              <TeacherAIModule username={username} />
            </div>
          ) : null}

          {activeTab === 'admin-stats' ? (
            <div className="teacher-lab-section">
              <AdminStatsCenter username={username} />
            </div>
          ) : null}

          {activeTab === 'admin-resource' ? (
            <div className="teacher-lab-section">
              <AdminResourceControl username={username} />
            </div>
          ) : null}
        </section>
      </div>

      {showCourseEditor ? (
        <CourseEditorModal
          initialCourse={editingCourse}
          onClose={() => {
            setShowCourseEditor(false);
            setEditingCourse(null);
          }}
          onCreate={handleCreateCourse}
          onUpdate={handleUpdateCourse}
        />
      ) : null}

      {showExperimentEditor && targetCourse ? (
        <ExperimentEditorModal
          username={username}
          course={targetCourse}
          initialExperiment={editingExperiment}
          resourceTiers={resourceTiers}
          onClose={() => {
            setShowExperimentEditor(false);
            setEditingExperiment(null);
            setTargetCourse(null);
          }}
          onCreate={handleCreateExperiment}
          onUpdate={handleUpdateExperiment}
        />
      ) : null}
    </div>
  );
}

function CoursePanel({
  courses,
  loading,
  onCreateExperiment,
  onEditCourse,
  onPublishCourse,
  onDeleteCourse,
  onOpenExperiment,
  onEditExperiment,
  onPublishExperiment,
  onDeleteExperiment,
}) {
  const [selectedCourseId, setSelectedCourseId] = useState(() => {
    const cachedCourseId = String(sessionStorage.getItem(TEACHER_COURSE_RESUME_KEY) || '').trim();
    if (cachedCourseId) {
      sessionStorage.removeItem(TEACHER_COURSE_RESUME_KEY);
    }
    return cachedCourseId;
  });

  const selectedCourse = useMemo(() => {
    const needle = String(selectedCourseId || '').trim();
    if (!needle) return null;
    return (courses || []).find((item) => String(item?.id || '').trim() === needle) || null;
  }, [courses, selectedCourseId]);

  useEffect(() => {
    if (!selectedCourseId) return;
    const keep = (courses || []).some((item) => String(item?.id || '').trim() === String(selectedCourseId).trim());
    if (!keep) setSelectedCourseId('');
  }, [courses, selectedCourseId]);

  const buildCourseViewModel = (course) => {
    const experiments = Array.isArray(course?.experiments) ? course.experiments : [];
    const firstExperiment = experiments[0] || {};
    const icon = courseIconMeta({
      name: course?.name,
      title: firstExperiment.title,
      description: course?.description || firstExperiment.description,
      tags: course?.tags?.length ? course.tags : firstExperiment.tags,
    });

    const totalExperiments = Number(course?.experiment_count ?? experiments.length);
    const publishedCount = Number(course?.published_count ?? experiments.filter((item) => item.published).length);
    const allPublished = totalExperiments > 0 && publishedCount === totalExperiments;
    return { experiments, firstExperiment, icon, totalExperiments, publishedCount, allPublished };
  };

  const renderExperimentList = (course) => {
    const experiments = Array.isArray(course?.experiments) ? course.experiments : [];
    if (experiments.length === 0) {
      return (
        <article className="teacher-lab-card teacher-lab-card-empty" key={`${course?.id || 'course'}-empty`}>
          <div className={`teacher-lab-logo ${courseIconMeta(course).cls}`}>
            <span>{courseIconMeta(course).label}</span>
          </div>
          <h3>{'\u6682\u65e0\u5b9e\u9a8c'}</h3>
          <p className="teacher-lab-desc">
            {'\u5f53\u524d\u8bfe\u7a0b\u8fd8\u6ca1\u6709\u5b9e\u9a8c\uff0c\u70b9\u51fb\u4e0b\u65b9\u6309\u94ae\u6dfb\u52a0\u7b2c\u4e00\u4e2a\u5b9e\u9a8c\u3002'}
          </p>
          <div className="teacher-lab-card-actions">
            <button type="button" className="teacher-lab-btn primary" onClick={() => onCreateExperiment(course)}>
              {'+ \u6dfb\u52a0\u5b9e\u9a8c'}
            </button>
          </div>
        </article>
      );
    }

    return experiments.map((experiment) => {
      const iconMeta = courseIconMeta({
        ...experiment,
        name: course?.name || experiment?.course_name || '',
        description: `${experiment?.description || ''} ${course?.description || ''}`.trim(),
        tags: [...(course?.tags || []), ...(experiment?.tags || [])],
      });

      return (
        <article key={experiment.id} className="teacher-lab-card">
          <div className={`teacher-lab-logo ${iconMeta.cls}`}>
            <span>{iconMeta.label}</span>
          </div>
          <h3>{experiment.title || '\u672a\u547d\u540d\u5b9e\u9a8c'}</h3>
          <div className="teacher-lab-card-headline">
            <span className={`teacher-lab-status ${experiment.published ? 'published' : 'draft'}`}>
              {experiment.published ? '\u5df2\u53d1\u5e03' : '\u8349\u7a3f'}
            </span>
            <span className="teacher-lab-difficulty">{`\u96be\u5ea6\uff1a${experiment.difficulty || '-'}`}</span>
          </div>
          <p className="teacher-lab-desc">
            {experiment.description || '\u6682\u65e0\u5b9e\u9a8c\u63cf\u8ff0'}
          </p>
          <div className="teacher-lab-chip-row">
            {(experiment.tags?.length ? experiment.tags : ['\u65e0\u6807\u7b7e']).map((tag) => (
              <span key={`${experiment.id}-${tag}`} className="teacher-lab-chip">{tag}</span>
            ))}
          </div>
          <div className="teacher-lab-meta-row">{`Notebook\uff1a${experiment.notebook_path || '\u672a\u914d\u7f6e'}`}</div>

          <div className="teacher-lab-card-actions">
            <button
              type="button"
              className="teacher-lab-btn primary"
              onClick={() => {
                sessionStorage.setItem(TEACHER_COURSE_RESUME_KEY, String(course?.id || ''));
                onOpenExperiment(experiment);
              }}
            >
              {'\u6253\u5f00'}
            </button>
            <button type="button" className="teacher-lab-btn" onClick={() => onEditExperiment(course, experiment)}>{'\u7f16\u8f91'}</button>
          </div>
          <div className="teacher-lab-card-actions">
            <button type="button" className="teacher-lab-btn highlight" onClick={() => onPublishExperiment(course, experiment)}>
              {experiment.published ? '\u53d6\u6d88\u53d1\u5e03' : '\u53d1\u5e03'}
            </button>
            <button type="button" className="teacher-lab-btn danger" onClick={() => onDeleteExperiment(experiment)}>{'\u5220\u9664'}</button>
          </div>
        </article>
      );
    });
  };

  if (loading) return <div className="teacher-lab-loading">{'\u6b63\u5728\u52a0\u8f7d\u8bfe\u7a0b\u5e93...'}</div>;

  if (courses.length === 0) {
    return (
      <div className="teacher-lab-course-section">
        <div className="teacher-lab-empty">{'\u5f53\u524d\u6682\u65e0\u8bfe\u7a0b\uff0c\u8bf7\u5148\u521b\u5efa\u8bfe\u7a0b\u3002'}</div>
      </div>
    );
  }

  if (!selectedCourse) {
    return (
      <div className="teacher-lab-course-section">
        <div className="teacher-lab-card-grid">
          {courses.map((course) => {
            const { firstExperiment, icon, totalExperiments, publishedCount, allPublished } = buildCourseViewModel(course);

            return (
              <article className="teacher-lab-card" key={course.id}>
                <div className={`teacher-lab-logo ${icon.cls}`}><span>{icon.label}</span></div>
                <h3>{course.name || '\u672a\u547d\u540d\u8bfe\u7a0b'}</h3>
                <div className="teacher-lab-card-headline">
                  <span className={`teacher-lab-status ${allPublished ? 'published' : 'draft'}`}>
                    {allPublished ? '\u8bfe\u7a0b\u5df2\u53d1\u5e03' : `\u5df2\u53d1\u5e03 ${publishedCount}/${totalExperiments}`}
                  </span>
                  <span className="teacher-lab-difficulty">{`\u5b9e\u9a8c\u6570\uff1a${totalExperiments}`}</span>
                </div>
                <p className="teacher-lab-desc">
                  {course.description || firstExperiment.description || `\u672c\u8bfe\u7a0b\u5305\u542b ${totalExperiments} \u4e2a\u5b9e\u9a8c\uff0c\u70b9\u51fb\u4e0b\u65b9\u6309\u94ae\u67e5\u770b\u5b9e\u9a8c\u5217\u8868\u3002`}
                </p>
                <div className="teacher-lab-chip-row">
                  {(course.tags?.length ? course.tags : ['\u65e0\u6807\u7b7e']).map((tag) => (
                    <span key={`${course.id}-${tag}`} className="teacher-lab-chip">{tag}</span>
                  ))}
                </div>
                <div className="teacher-lab-meta-row">{`\u521b\u5efa\u8005\uff1a${course.created_by || '\u672a\u77e5'}`}</div>
                <div className="teacher-lab-meta-row">{`\u6700\u8fd1\u66f4\u65b0\u65f6\u95f4\uff1a${formatDate(course.updated_at || course.created_at)}`}</div>

                <div className="teacher-lab-card-actions">
                  <button type="button" className="teacher-lab-btn primary" onClick={() => setSelectedCourseId(course.id)}>{'\u67e5\u770b\u5b9e\u9a8c'}</button>
                  <button type="button" className="teacher-lab-btn" onClick={() => onCreateExperiment(course)}>{'+ \u6dfb\u52a0\u5b9e\u9a8c'}</button>
                  <button type="button" className="teacher-lab-btn" onClick={() => onEditCourse(course)}>{'\u7f16\u8f91\u8bfe\u7a0b'}</button>
                </div>

                <div className="teacher-lab-card-actions">
                  <button type="button" className="teacher-lab-btn highlight" onClick={() => onPublishCourse(course)}>
                    {allPublished ? '\u53d6\u6d88\u53d1\u5e03\u8bfe\u7a0b' : '\u53d1\u5e03\u8bfe\u7a0b'}
                  </button>
                  <button type="button" className="teacher-lab-btn danger" onClick={() => onDeleteCourse(course)}>{'\u5220\u9664\u8bfe\u7a0b'}</button>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    );
  }

  const { totalExperiments, publishedCount, allPublished } = buildCourseViewModel(selectedCourse);

  return (
    <div className="teacher-lab-course-section">
      <div className="teacher-lab-course-head">
        <button type="button" className="teacher-lab-course-back" onClick={() => setSelectedCourseId('')}>
          {'\u8fd4\u56de\u8bfe\u7a0b\u5e93'}
        </button>
        <span className="teacher-lab-course-pill">
          {`${selectedCourse.name || '\u672a\u547d\u540d\u8bfe\u7a0b'} \u00b7 \u5b9e\u9a8c\u6570\uff1a${totalExperiments}`}
        </span>
      </div>

      <div className="teacher-lab-course-tools">
        <button type="button" className="teacher-lab-btn primary" onClick={() => onCreateExperiment(selectedCourse)}>{'+ \u6dfb\u52a0\u5b9e\u9a8c'}</button>
        <button type="button" className="teacher-lab-btn" onClick={() => onEditCourse(selectedCourse)}>{'\u7f16\u8f91\u8bfe\u7a0b'}</button>
        <button type="button" className="teacher-lab-btn highlight" onClick={() => onPublishCourse(selectedCourse)}>
          {allPublished ? '\u53d6\u6d88\u53d1\u5e03\u8bfe\u7a0b' : `\u53d1\u5e03\u8bfe\u7a0b(${publishedCount}/${totalExperiments})`}
        </button>
        <button type="button" className="teacher-lab-btn danger" onClick={() => onDeleteCourse(selectedCourse)}>{'\u5220\u9664\u8bfe\u7a0b'}</button>
      </div>

      <div className="teacher-lab-card-grid teacher-lab-experiment-grid">
        {renderExperimentList(selectedCourse)}
      </div>
    </div>
  );
}

function ProgressPanel({ progress, loading, courseMap }) {
  const [filter, setFilter] = useState('all');
  const total = progress.length;
  const completed = useMemo(() => progress.filter((item) => isCompleted(item.status)).length, [progress]);
  const pending = total - completed;
  const rate = total > 0 ? ((completed / total) * 100).toFixed(1) : '0.0';

  const rows = useMemo(() => {
    if (filter === 'completed') return progress.filter((item) => isCompleted(item.status));
    if (filter === 'incomplete') return progress.filter((item) => !isCompleted(item.status));
    return progress;
  }, [filter, progress]);

  const statusLabel = {
    'not-started': '未开始',
    'in-progress': '进行中',
    submitted: '已提交',
    graded: '已评分',
  };

  if (loading) return <div className="teacher-lab-loading">正在加载学生进度...</div>;

  return (
    <div className="teacher-lab-section teacher-lab-progress">
      <div className="teacher-lab-progress-stats">
        <div className="teacher-lab-progress-stat"><span>总记录</span><strong>{total}</strong></div>
        <div className="teacher-lab-progress-stat success"><span>已完成</span><strong>{completed}</strong></div>
        <div className="teacher-lab-progress-stat warning"><span>未完成</span><strong>{pending}</strong></div>
        <div className="teacher-lab-progress-stat info"><span>完成率</span><strong>{rate}%</strong></div>
      </div>

      <div className="teacher-lab-filter-row">
        <label htmlFor="teacher-progress-filter">状态筛选：</label>
        <select id="teacher-progress-filter" value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">全部</option>
          <option value="completed">已完成</option>
          <option value="incomplete">未完成</option>
        </select>
      </div>

      <div className="teacher-lab-table-wrap">
        <table className="teacher-lab-table">
          <thead>
            <tr>
              <th>学号</th>
              <th>实验</th>
              <th>状态</th>
              <th>开始时间</th>
              <th>提交时间</th>
              <th>分数</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan="6" className="teacher-lab-empty-row">当前筛选条件下暂无数据</td>
              </tr>
            ) : (
              rows.map((item, index) => {
                const key = progressStatusKey(item.status);
                return (
                  <tr key={`${item.student_id}-${item.experiment_id}-${index}`}>
                    <td>{item.student_id || '-'}</td>
                    <td>{courseMap[item.experiment_id]?.title || item.experiment_id || '-'}</td>
                    <td><span className={`teacher-lab-progress-badge ${key}`}>{statusLabel[key] || item.status || '-'}</span></td>
                    <td>{formatDateTime(item.start_time)}</td>
                    <td>{formatDateTime(item.submit_time)}</td>
                    <td>{item.score === null || item.score === undefined ? '-' : item.score}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TeacherProfilePanel({ username, userRole }) {
  const [submitting, setSubmitting] = useState(false);
  const [securitySubmitting, setSecuritySubmitting] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [securityQuestion, setSecurityQuestion] = useState('');
  const [securityAnswer, setSecurityAnswer] = useState('');
  const [securityQuestionSet, setSecurityQuestionSet] = useState(false);

  const roleLabel = userRole === 'admin' ? '系统管理员' : '教师管理员';

  useEffect(() => {
    let cancelled = false;

    const loadSecurityQuestion = async () => {
      if (!username) return;
      try {
        const response = await axios.get(`${API_BASE_URL}/api/auth/security-question`, {
          params: { username },
        });
        if (cancelled) return;
        const question = String(response.data?.security_question || '');
        setSecurityQuestion(question);
        setSecurityQuestionSet(Boolean(question));
      } catch (error) {
        if (cancelled) return;
        setSecurityQuestion('');
        setSecurityQuestionSet(false);
      }
    };

    loadSecurityQuestion();
    return () => {
      cancelled = true;
    };
  }, [username]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;

    if (newPassword.length < 6) {
      alert('新密码长度不能少于6位');
      return;
    }

    if (newPassword !== confirmPassword) {
      alert('两次输入的新密码不一致');
      return;
    }

    if (newPassword === currentPassword) {
      alert('新密码不能与旧密码相同');
      return;
    }

    setSubmitting(true);
    try {
      const response = await axios.post(`${API_BASE_URL}/api/teacher/profile/change-password`, {
        teacher_username: username,
        old_password: currentPassword,
        new_password: newPassword,
      });

      const rememberMe = localStorage.getItem('rememberMe') === 'true';
      const rememberedUsername = String(localStorage.getItem('rememberedUsername') || '').trim();
      if (rememberMe && rememberedUsername === String(username || '').trim()) {
        localStorage.setItem('rememberedPassword', newPassword);
      }

      alert(response.data?.message || '密码修改成功');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (error) {
      alert(getErrorMessage(error, '修改密码失败'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleSaveSecurityQuestion = async (event) => {
    event.preventDefault();
    if (securitySubmitting) return;

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
      const response = await axios.post(`${API_BASE_URL}/api/teacher/profile/security-question`, {
        teacher_username: username,
        security_question: normalizedQuestion,
        security_answer: normalizedAnswer,
      });
      alert(response.data?.message || '密保问题已保存');
      setSecurityQuestion(normalizedQuestion);
      setSecurityQuestionSet(true);
      setSecurityAnswer('');
    } catch (error) {
      alert(getErrorMessage(error, '保存密保失败'));
    } finally {
      setSecuritySubmitting(false);
    }
  };

  return (
    <div className="teacher-profile-panel">
      <div className="teacher-profile-card">
        <h3>个人信息</h3>
        <div className="teacher-profile-grid">
          <div className="teacher-profile-item">
            <span>账号</span>
            <strong>{username || '-'}</strong>
          </div>
          <div className="teacher-profile-item">
            <span>角色</span>
            <strong>{roleLabel}</strong>
          </div>
          <div className="teacher-profile-item">
            <span>安全说明</span>
            <strong>修改后立即生效</strong>
          </div>
          <div className="teacher-profile-item">
            <span>密码规则</span>
            <strong>至少 6 位</strong>
          </div>
        </div>
      </div>

      <div className="teacher-profile-card">
        <h3>修改密码</h3>
        <form className="teacher-profile-form" onSubmit={handleSubmit}>
          <label htmlFor="teacher-current-password">当前密码</label>
          <input
            id="teacher-current-password"
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            required
          />

          <label htmlFor="teacher-new-password">新密码</label>
          <input
            id="teacher-new-password"
            type="password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            minLength={6}
            required
          />

          <label htmlFor="teacher-confirm-password">确认新密码</label>
          <input
            id="teacher-confirm-password"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            minLength={6}
            required
          />

          <p className="teacher-profile-hint">修改成功后，下次登录请使用新密码。</p>
          <button type="submit" className="teacher-profile-btn" disabled={submitting}>
            {submitting ? '保存中...' : '保存新密码'}
          </button>
        </form>

        <form className="teacher-profile-form" onSubmit={handleSaveSecurityQuestion}>
          <label htmlFor="teacher-security-question">密保问题</label>
          <input
            id="teacher-security-question"
            type="text"
            value={securityQuestion}
            onChange={(event) => setSecurityQuestion(event.target.value)}
            placeholder="例如：我第一门授课课程名？"
            required
          />

          <label htmlFor="teacher-security-answer">密保答案</label>
          <input
            id="teacher-security-answer"
            type="text"
            value={securityAnswer}
            onChange={(event) => setSecurityAnswer(event.target.value)}
            placeholder="请输入密保答案"
            required
          />

          <p className="teacher-profile-hint">
            {securityQuestionSet
              ? '已设置密保问题，可在登录页通过密保找回密码。'
              : '建议设置密保问题，避免忘记密码无法自助重置。'}
          </p>
          <button type="submit" className="teacher-profile-btn" disabled={securitySubmitting}>
            {securitySubmitting ? '保存中...' : (securityQuestionSet ? '更新密保问题' : '保存密保问题')}
          </button>
        </form>
      </div>
    </div>
  );
}
function CourseEditorModal({ initialCourse, onClose, onCreate, onUpdate }) {
  const isEdit = Boolean(initialCourse);
  const [formData, setFormData] = useState(() => ({
    name: initialCourse?.name || '',
    description: initialCourse?.description || '',
  }));
  const [saving, setSaving] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    try {
      if (isEdit) {
        await onUpdate(initialCourse, formData);
        alert('课程更新成功');
      } else {
        await onCreate(formData);
        alert('课程创建成功');
      }
      onClose();
    } catch (error) {
      console.error('save course failed', error);
      alert(getErrorMessage(error, isEdit ? '更新课程失败' : '创建课程失败'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(event) => event.stopPropagation()}>
        <h2>{isEdit ? '编辑课程' : '创建课程'}</h2>
        <form onSubmit={submit}>
          <div className="form-group">
            <label htmlFor="course-name">课程名称</label>
            <input
              id="course-name"
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="例如：Python程序设计"
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="course-description">课程简介（可选）</label>
            <textarea
              id="course-description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="请输入课程简介"
            />
          </div>
          <div className="form-actions">
            <button type="button" onClick={onClose} disabled={saving}>取消</button>
            <button type="submit" disabled={saving}>{saving ? '处理中...' : (isEdit ? '保存修改' : '创建课程')}</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ExperimentEditorModal({ username, course, initialExperiment, resourceTiers = DEFAULT_RESOURCE_TIERS, onClose, onCreate, onUpdate }) {
  const isEdit = Boolean(initialExperiment);
  const [formData, setFormData] = useState(() => ({
    title: initialExperiment?.title || '',
    description: initialExperiment?.description || '',
    difficulty: initialExperiment?.difficulty || '初级',
    tags: Array.isArray(initialExperiment?.tags) ? initialExperiment.tags.join(', ') : '',
    notebook_path: initialExperiment?.notebook_path || '',
    published: initialExperiment ? Boolean(initialExperiment?.published) : true,
    publish_scope: normalizeEditorPublishScope(initialExperiment?.publish_scope),
    target_class_names: normalizeStringArray(initialExperiment?.target_class_names),
    target_student_ids: normalizeStringArray(initialExperiment?.target_student_ids),
    resource_tier: normalizeResourceTier(initialExperiment?.resource_tier || initialExperiment?.resources?.resource_tier),
  }));
  const [targets, setTargets] = useState({ classes: [], students: [] });
  const [loadingTargets, setLoadingTargets] = useState(false);
  const [studentKeyword, setStudentKeyword] = useState('');
  const [files, setFiles] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const loadTargets = async () => {
      if (!username) return;
      setLoadingTargets(true);
      try {
        const res = await axios.get(`${API_BASE_URL}/api/teacher/publish-targets`, {
          params: { teacher_username: username },
        });
        if (cancelled) return;
        setTargets({
          classes: Array.isArray(res.data?.classes) ? res.data.classes : [],
          students: Array.isArray(res.data?.students) ? res.data.students : [],
        });
      } catch (error) {
        if (!cancelled) setTargets({ classes: [], students: [] });
      } finally {
        if (!cancelled) setLoadingTargets(false);
      }
    };

    loadTargets();
    return () => {
      cancelled = true;
    };
  }, [username]);

  const classes = Array.isArray(targets?.classes) ? targets.classes : [];
  const filteredStudents = useMemo(() => {
    const students = Array.isArray(targets?.students) ? targets.students : [];
    const needle = String(studentKeyword || '').trim().toLowerCase();
    if (!needle) return students;
    return students.filter((item) => {
      const sid = String(item?.student_id || '').toLowerCase();
      const realName = String(item?.real_name || '').toLowerCase();
      const className = String(item?.class_name || '').toLowerCase();
      return sid.includes(needle) || realName.includes(needle) || className.includes(needle);
    });
  }, [targets?.students, studentKeyword]);

  const onFileChange = (event) => {
    const next = Array.from(event.target.files || []);
    setFiles((prev) => {
      const keys = new Set(prev.map((file) => `${file.name}-${file.size}`));
      return [...prev, ...next.filter((file) => !keys.has(`${file.name}-${file.size}`))];
    });
    event.target.value = '';
  };

  const removeFile = (idx) => setFiles((prev) => prev.filter((_, i) => i !== idx));

  const toggleClass = (name) => {
    const normalizedName = String(name || '').trim();
    if (!normalizedName) return;
    setFormData((prev) => ({
      ...prev,
      target_class_names: prev.target_class_names.includes(normalizedName)
        ? prev.target_class_names.filter((item) => item !== normalizedName)
        : [...prev.target_class_names, normalizedName],
    }));
  };

  const toggleStudent = (studentId) => {
    const normalizedStudentId = String(studentId || '').trim();
    if (!normalizedStudentId) return;
    setFormData((prev) => ({
      ...prev,
      target_student_ids: prev.target_student_ids.includes(normalizedStudentId)
        ? prev.target_student_ids.filter((item) => item !== normalizedStudentId)
        : [...prev.target_student_ids, normalizedStudentId],
    }));
  };

  const submit = async (event) => {
    event.preventDefault();
    if (saving) return;

    if (formData.published && formData.publish_scope === 'class' && formData.target_class_names.length === 0) {
      alert('请选择至少一个班级');
      return;
    }
    if (formData.published && formData.publish_scope === 'student' && formData.target_student_ids.length === 0) {
      alert('请选择至少一个学生');
      return;
    }

    setSaving(true);
    try {
      const experiment = isEdit
        ? await onUpdate(course, initialExperiment, formData)
        : await onCreate(course, formData);

      let uploadError = null;
      if (experiment?.id && files.length > 0) {
        try {
          const data = new FormData();
          files.forEach((file) => data.append('files', file));
          await axios.post(`${API_BASE_URL}/api/teacher/experiments/${experiment.id}/attachments`, data, {
            headers: { 'Content-Type': 'multipart/form-data' },
          });
        } catch (error) {
          uploadError = error;
        }
      }

      if (uploadError) {
        alert(`实验已保存，但附件上传失败：${getErrorMessage(uploadError, '请稍后重试')}`);
        onClose();
        return;
      }

      alert(isEdit ? '实验更新成功' : '实验创建成功');
      onClose();
    } catch (error) {
      console.error('save experiment failed', error);
      alert(getErrorMessage(error, isEdit ? '更新实验失败' : '创建实验失败'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(event) => event.stopPropagation()}>
        <h2>{isEdit ? '编辑实验' : `添加实验 · ${course?.name || ''}`}</h2>
        <form onSubmit={submit}>
          <div className="form-group">
            <label htmlFor="experiment-course-name">所属课程</label>
            <input id="experiment-course-name" type="text" value={course?.name || ''} disabled />
          </div>
          <div className="form-group">
            <label htmlFor="experiment-title">实验名称</label>
            <input id="experiment-title" type="text" value={formData.title} onChange={(e) => setFormData({ ...formData, title: e.target.value })} required />
          </div>
          <div className="form-group">
            <label htmlFor="experiment-description">实验描述</label>
            <textarea id="experiment-description" value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} placeholder="请输入实验目标、内容和说明" />
          </div>
          <div className="form-group">
            <label htmlFor="experiment-difficulty">难度</label>
            <select id="experiment-difficulty" value={formData.difficulty} onChange={(e) => setFormData({ ...formData, difficulty: e.target.value })}>
              <option value="初级">初级</option>
              <option value="中级">中级</option>
              <option value="高级">高级</option>
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="experiment-tags">标签（逗号分隔）</label>
            <input id="experiment-tags" type="text" value={formData.tags} onChange={(e) => setFormData({ ...formData, tags: e.target.value })} placeholder="Python, 数据分析, 机器学习" />
          </div>
          <div className="form-group">
            <label htmlFor="experiment-notebook">Notebook 路径</label>
            <input id="experiment-notebook" type="text" value={formData.notebook_path} onChange={(e) => setFormData({ ...formData, notebook_path: e.target.value })} placeholder="course/example.ipynb" />
          </div>
          <div className="form-group">
            <label htmlFor="experiment-resource-tier">实验资源档位</label>
            <select
              id="experiment-resource-tier"
              value={formData.resource_tier}
              onChange={(e) => setFormData({ ...formData, resource_tier: e.target.value })}
            >
              {(resourceTiers || DEFAULT_RESOURCE_TIERS).map((tier) => (
                <option key={tier.key} value={tier.key}>{resourceTierLabel(tier)}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label htmlFor="experiment-attachments">附件上传（可选，可多选）</label>
            <input id="experiment-attachments" type="file" multiple onChange={onFileChange} />
            {files.length > 0 ? (
              <ul className="teacher-lab-upload-list">
                {files.map((file, index) => (
                  <li key={`${file.name}-${file.size}`}>
                    <span>{file.name}</span>
                    <button type="button" onClick={() => removeFile(index)}>移除</button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          <div className="form-group checkbox">
            <label htmlFor="experiment-published">
              <input id="experiment-published" type="checkbox" checked={formData.published} onChange={(e) => setFormData({ ...formData, published: e.target.checked })} />
              保存后立即发布
            </label>
          </div>

          {formData.published ? (
            <>
              <div className="form-group">
                <label>发布范围</label>
                <div className="publish-scope-row">
                  <label><input type="radio" name="edit-publish-scope" checked={formData.publish_scope === 'class'} onChange={() => setFormData({ ...formData, publish_scope: 'class', target_student_ids: [] })} /> 指定班级</label>
                  <label><input type="radio" name="edit-publish-scope" checked={formData.publish_scope === 'student'} onChange={() => setFormData({ ...formData, publish_scope: 'student', target_class_names: [] })} /> 指定学生</label>
                </div>
              </div>

              {formData.publish_scope === 'class' ? (
                <div className="form-group">
                  <label>{`选择班级（已选 ${formData.target_class_names.length}）`}</label>
                  {loadingTargets ? (
                    <div className="publish-target-loading">正在加载班级列表...</div>
                  ) : (
                    <div className="publish-target-list">
                      {classes.length === 0 ? (
                        <div className="publish-target-empty">暂无可选班级</div>
                      ) : (
                        classes.map((item) => {
                          const name = String(item?.name || '').trim();
                          return (
                            <label key={item?.id || name}>
                              <input type="checkbox" checked={formData.target_class_names.includes(name)} onChange={() => toggleClass(name)} />
                              <span>{name}</span>
                            </label>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>
              ) : null}

              {formData.publish_scope === 'student' ? (
                <div className="form-group">
                  <label>{`选择学生（已选 ${formData.target_student_ids.length}）`}</label>
                  <input
                    type="text"
                    value={studentKeyword}
                    onChange={(event) => setStudentKeyword(event.target.value)}
                    placeholder="按学号/姓名/班级搜索"
                  />
                  {loadingTargets ? (
                    <div className="publish-target-loading">正在加载学生列表...</div>
                  ) : (
                    <div className="publish-target-list">
                      {filteredStudents.length === 0 ? (
                        <div className="publish-target-empty">暂无匹配学生</div>
                      ) : (
                        filteredStudents.map((item) => {
                          const studentId = String(item?.student_id || '').trim();
                          const realName = String(item?.real_name || '').trim();
                          const className = String(item?.class_name || '').trim();
                          return (
                            <label key={studentId}>
                              <input type="checkbox" checked={formData.target_student_ids.includes(studentId)} onChange={() => toggleStudent(studentId)} />
                              <span>{`${studentId}${realName ? ` 路 ${realName}` : ''}${className ? ` 路 ${className}` : ''}`}</span>
                            </label>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>
              ) : null}
            </>
          ) : null}

          <div className="form-actions">
            <button type="button" onClick={onClose} disabled={saving}>取消</button>
            <button type="submit" disabled={saving}>{saving ? '处理中...' : (isEdit ? '保存修改' : '创建实验')}</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function CourseTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3.5" y="4" width="17" height="16" rx="2.5" />
      <path d="M8 9h8M8 13h8M8 17h5" />
    </svg>
  );
}

function ProgressTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 18V8m6 10V5m6 13v-6m6 6V3" />
    </svg>
  );
}

function ReviewTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 5h16v14H4z" />
      <path d="M8 9h8M8 13h5" />
      <path d="m14 16 2 2 4-4" />
    </svg>
  );
}

function UserTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5" />
      <path d="M17 10h4M19 8v4" />
    </svg>
  );
}

function ResourceTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 4h12l2 3v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" />
      <path d="M8 12h8M8 16h8M8 8h5" />
    </svg>
  );
}

function ProfileTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="3.2" />
      <path d="M5.5 18.5C6.6 15.9 9 14.4 12 14.4C15 14.4 17.4 15.9 18.5 18.5" />
      <rect x="3.5" y="3.5" width="17" height="17" rx="2.4" />
    </svg>
  );
}

function AITabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v4M6.5 5.5l2.8 2.8M3 12h4M17 12h4M6.5 18.5l2.8-2.8M14.7 15.7l2.8 2.8" />
      <circle cx="12" cy="12" r="5" />
      <path d="M10.5 12.2l1 1 2-2.3" />
    </svg>
  );
}

function AdminControlTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 6h16M4 12h16M4 18h16" />
      <circle cx="7" cy="6" r="1.5" />
      <circle cx="17" cy="12" r="1.5" />
      <circle cx="10" cy="18" r="1.5" />
    </svg>
  );
}

export default TeacherDashboard;
