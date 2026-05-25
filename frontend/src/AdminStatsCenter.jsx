import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import './AdminStatsCenter.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';
const AUTO_REFRESH_MS = 30000;

const CARD_TONES = {
  blue: { accent: '#2f84c8', soft: '#eaf4ff', ink: '#1f5f95' },
  cyan: { accent: '#2aa6b8', soft: '#e8fbfe', ink: '#147786' },
  green: { accent: '#37b06e', soft: '#eafbf2', ink: '#1f7c4d' },
  amber: { accent: '#ef9f2f', soft: '#fff5e6', ink: '#a86811' },
  violet: { accent: '#7a6be8', soft: '#f1efff', ink: '#5647be' },
  pink: { accent: '#e75c93', soft: '#fff0f6', ink: '#a93565' },
  slate: { accent: '#5d7a97', soft: '#eef3f8', ink: '#3f5b76' },
};

function clampPercent(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

function formatDateTime(value) {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '-';
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function formatCount(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return '0';
  return n.toLocaleString('zh-CN');
}

function formatPercent(value) {
  const n = clampPercent(value);
  return `${n.toFixed(1)}%`;
}

function formatDuration(seconds) {
  const value = Number(seconds || 0);
  if (!Number.isFinite(value) || value <= 0) return '0 分钟';
  const total = Math.floor(value);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}天 ${hours}小时 ${minutes}分钟`;
  if (hours > 0) return `${hours}小时 ${minutes}分钟`;
  return `${Math.max(1, minutes)}分钟`;
}

function formatHours(seconds) {
  const value = Number(seconds || 0);
  if (!Number.isFinite(value) || value <= 0) return '0.0 小时';
  return `${(value / 3600).toFixed(1)} 小时`;
}

function isCompletedProgressStatus(status) {
  const v = String(status || '').toLowerCase();
  return (
    v.includes('graded') ||
    v.includes('submit') ||
    v.includes('submitted') ||
    v.includes('completed') ||
    v.includes('评分') ||
    v.includes('提交') ||
    v.includes('完成')
  );
}

function resolveCourseName(item) {
  const explicit = String(item?.course_name || '').trim();
  if (explicit) return explicit;
  const explicitName = String(item?.name || '').trim();
  if (explicitName) return explicitName;
  const path = String(item?.notebook_path || '').trim();
  const first = path.split('/').filter(Boolean)[0] || '';
  if (first && first.toLowerCase() !== 'course') return first;
  return '未命名课程';
}

function summarizeCourseStatsPayload(payload) {
  const items = Array.isArray(payload) ? payload : [];
  const hasCourseShape = items.some((item) => Array.isArray(item?.experiments) || item?.name);

  if (hasCourseShape) {
    let experimentCount = 0;
    let publishedExperimentCount = 0;
    items.forEach((item) => {
      const experiments = Array.isArray(item?.experiments) ? item.experiments : [];
      experimentCount += Number(item?.experiment_count ?? experiments.length ?? 0);
      publishedExperimentCount += Number(item?.published_count ?? experiments.filter((exp) => exp?.published).length ?? 0);
    });
    return {
      courseCount: items.length,
      experimentCount,
      publishedExperimentCount,
    };
  }

  const courseNames = new Set();
  let publishedExperimentCount = 0;
  items.forEach((item) => {
    courseNames.add(resolveCourseName(item).toLowerCase());
    if (item?.published) publishedExperimentCount += 1;
  });

  return {
    courseCount: courseNames.size,
    experimentCount: items.length,
    publishedExperimentCount,
  };
}

function roleLabel(role) {
  const normalized = String(role || '').toLowerCase();
  if (normalized === 'teacher') return '教师';
  if (normalized === 'student') return '学生';
  if (normalized === 'admin') return '管理员';
  return normalized || '未知';
}

function roleTone(role) {
  const normalized = String(role || '').toLowerCase();
  if (normalized === 'teacher') return 'blue';
  if (normalized === 'student') return 'green';
  if (normalized === 'admin') return 'slate';
  return 'slate';
}

function statusMeta(row) {
  if (row?.server_running) return { label: '在线', className: 'is-online' };
  if (row?.server_pending) return { label: '启动中', className: 'is-pending' };
  return { label: '离线', className: 'is-offline' };
}

function toneStyle(toneName) {
  const tone = CARD_TONES[toneName] || CARD_TONES.blue;
  return {
    '--admin-sc-accent': tone.accent,
    '--admin-sc-soft': tone.soft,
    '--admin-sc-ink': tone.ink,
  };
}

function StatIcon({ name }) {
  const common = { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true };

  switch (name) {
    case 'grid':
      return (
        <svg {...common}>
          <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
          <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
          <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
          <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
        </svg>
      );
    case 'users':
      return (
        <svg {...common}>
          <path d="M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1" />
          <circle cx="9.5" cy="8" r="3" />
          <path d="M21 20v-1a4 4 0 0 0-3-3.86" />
          <path d="M16.5 5.2a3 3 0 0 1 0 5.6" />
        </svg>
      );
    case 'user-active':
      return (
        <svg {...common}>
          <circle cx="10" cy="8" r="3" />
          <path d="M4 20v-1a6 6 0 0 1 12 0v1" />
          <path d="M18 8l2 2 4-4" />
        </svg>
      );
    case 'book':
      return (
        <svg {...common}>
          <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16.5a1.5 1.5 0 0 1-1.5 1.5H6.5A2.5 2.5 0 0 1 4 18.5z" />
          <path d="M4 18.5A2.5 2.5 0 0 0 6.5 21" />
          <path d="M8 7h8" />
          <path d="M8 11h8" />
        </svg>
      );
    case 'flask':
      return (
        <svg {...common}>
          <path d="M10 3h4" />
          <path d="M11 3v6l-5.5 8.4A2 2 0 0 0 7.2 21h9.6a2 2 0 0 0 1.7-3.6L13 9V3" />
          <path d="M8.5 15h7" />
        </svg>
      );
    case 'rocket':
      return (
        <svg {...common}>
          <path d="M5 19c1.5-.3 3.2-1.1 4.5-2.4l5.1-5.1A8.3 8.3 0 0 0 17.9 4c-2.2.1-4.4 1-6 2.6L6.8 11.7C5.5 13 4.7 14.7 4.4 16.2L4 18z" />
          <path d="M13 7l4 4" />
          <path d="M6 18l-2 2" />
        </svg>
      );
    case 'activity':
      return (
        <svg {...common}>
          <path d="M3 12h4l2.2-4.2L13 17l2.4-5H21" />
        </svg>
      );
    case 'check-circle':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8.5" />
          <path d="M8.8 12.2l2.2 2.2 4.3-4.4" />
        </svg>
      );
    case 'monitor':
      return (
        <svg {...common}>
          <rect x="3" y="4" width="18" height="12" rx="2" />
          <path d="M8 20h8" />
          <path d="M12 16v4" />
        </svg>
      );
    case 'repeat':
      return (
        <svg {...common}>
          <path d="M17 1l4 4-4 4" />
          <path d="M3 11V9a4 4 0 0 1 4-4h14" />
          <path d="M7 23l-4-4 4-4" />
          <path d="M21 13v2a4 4 0 0 1-4 4H3" />
        </svg>
      );
    case 'clock':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8.5" />
          <path d="M12 7.5V12l3 2" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8.5" />
        </svg>
      );
  }
}

function MetricMeterPanel({ title, subtitle, metrics }) {
  return (
    <section className="admin-sc-chart-panel">
      <div className="admin-sc-chart-head">
        <h3>{title}</h3>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      <div className="admin-sc-meter-list">
        {metrics.map((metric) => (
          <div className="admin-sc-meter-item" key={metric.key}>
            <div className="admin-sc-meter-meta">
              <div className="admin-sc-meter-left">
                <span className="admin-sc-meter-label">{metric.label}</span>
                {metric.note ? <span className="admin-sc-meter-note">{metric.note}</span> : null}
              </div>
              <strong className="admin-sc-meter-value">{metric.valueText}</strong>
            </div>
            <div className="admin-sc-meter-track" aria-hidden="true">
              <div
                className="admin-sc-meter-fill"
                style={{ width: `${clampPercent(metric.percent)}%`, backgroundColor: metric.color || '#2f84c8' }}
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function CompareBarsPanel({ title, subtitle, groups, footerStats }) {
  return (
    <section className="admin-sc-chart-panel">
      <div className="admin-sc-chart-head">
        <h3>{title}</h3>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      <div className="admin-sc-compare-list">
        {groups.map((group) => {
          const teacherValue = Number(group.teacherValue || 0);
          const studentValue = Number(group.studentValue || 0);
          const localMax = Math.max(1, teacherValue, studentValue);
          const total = teacherValue + studentValue;
          const teacherShare = total > 0 ? (teacherValue / total) * 100 : 0;
          const studentShare = total > 0 ? (studentValue / total) * 100 : 0;
          const formatValue = group.formatter || formatCount;
          return (
            <div className="admin-sc-compare-item" key={group.key}>
              <div className="admin-sc-compare-top">
                <span className="admin-sc-compare-label">{group.label}</span>
                <span className="admin-sc-compare-total">总计 {formatValue(total)}</span>
              </div>
              <div className="admin-sc-compare-bars">
                <div className="admin-sc-role-row">
                  <span className="admin-sc-role-tag is-teacher">教师</span>
                  <div className="admin-sc-role-track" aria-hidden="true">
                    <div
                      className="admin-sc-role-fill is-teacher"
                      style={{ width: `${Math.max(0, Math.min(100, (teacherValue / localMax) * 100))}%` }}
                    />
                  </div>
                  <span className="admin-sc-role-value">{formatValue(teacherValue)}</span>
                  <span className="admin-sc-role-share">{formatPercent(teacherShare)}</span>
                </div>
                <div className="admin-sc-role-row">
                  <span className="admin-sc-role-tag is-student">学生</span>
                  <div className="admin-sc-role-track" aria-hidden="true">
                    <div
                      className="admin-sc-role-fill is-student"
                      style={{ width: `${Math.max(0, Math.min(100, (studentValue / localMax) * 100))}%` }}
                    />
                  </div>
                  <span className="admin-sc-role-value">{formatValue(studentValue)}</span>
                  <span className="admin-sc-role-share">{formatPercent(studentShare)}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {Array.isArray(footerStats) && footerStats.length > 0 ? (
        <div className="admin-sc-mini-grid">
          {footerStats.map((item) => (
            <div className="admin-sc-mini-card" key={item.key}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function TopUsersPanel({ title, subtitle, rows }) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return (
      <section className="admin-sc-chart-panel">
        <div className="admin-sc-chart-head">
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        <div className="admin-sc-empty">暂无 Jupyter 使用用户数据</div>
      </section>
    );
  }

  const scoreMax = Math.max(
    1,
    ...rows.map((row) => Math.max(Number(row.total_with_active_seconds || 0), Number(row.session_count || 0)))
  );

  return (
    <section className="admin-sc-chart-panel">
      <div className="admin-sc-chart-head">
        <h3>{title}</h3>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      <div className="admin-sc-top-list">
        {rows.map((row) => {
          const tone = roleTone(row.role);
          const status = statusMeta(row);
          const totalSeconds = Number(row.total_with_active_seconds ?? row.total_seconds ?? 0);
          const activeSeconds = Number(row.active_session_seconds ?? 0);
          const score = Math.max(totalSeconds, Number(row.session_count || 0));
          const widthPct = Math.max(0, Math.min(100, (score / scoreMax) * 100));
          return (
            <div className="admin-sc-top-item" key={`${row.role}-${row.username}`} style={toneStyle(tone)}>
              <div className="admin-sc-top-head">
                <div className="admin-sc-top-user">
                  <span className="admin-sc-top-name">{row.username}</span>
                  <span className="admin-sc-top-role">{roleLabel(row.role)}</span>
                  <span className={`admin-sc-top-status ${status.className}`}>{status.label}</span>
                </div>
                <div className="admin-sc-top-meta">
                  <span>{formatDuration(totalSeconds)}</span>
                  <span>会话 {formatCount(row.session_count)}</span>
                </div>
              </div>
              <div className="admin-sc-top-track" aria-hidden="true">
                <div className="admin-sc-top-fill" style={{ width: `${widthPct}%` }} />
              </div>
              <div className="admin-sc-top-foot">
                <span>最近活动 {formatDateTime(row.last_activity || row.last_seen_at)}</span>
                {activeSeconds > 0 ? <span>当前会话已进行 {formatDuration(activeSeconds)}</span> : <span>当前无活跃会话</span>}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function AdminStatsCenter({ username }) {
  const [coreStats, setCoreStats] = useState({
    classCount: 0,
    visibleStudentCount: 0,
    activeStudentCount: 0,
    courseCount: 0,
    experimentCount: 0,
    publishedExperimentCount: 0,
    activityCount: 0,
    completedActivityCount: 0,
    completionRate: 0,
    updatedAt: '',
  });
  const [usageMonitor, setUsageMonitor] = useState({ summary: {}, by_role: {}, users: [], generated_at: '', scope: '' });
  const [loadingCore, setLoadingCore] = useState(false);
  const [loadingUsage, setLoadingUsage] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const loadCoreStats = useCallback(async ({ silent = false } = {}) => {
    setLoadingCore(true);
    if (!silent) setErrorMessage('');
    try {
      const [classRes, studentRes, courseRes, progressRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/admin/classes`, { params: { teacher_username: username } }),
        axios.get(`${API_BASE_URL}/api/admin/students`, {
          params: { teacher_username: username, page: 1, page_size: 1 },
        }),
        axios.get(`${API_BASE_URL}/api/teacher/courses`, { params: { teacher_username: username } }),
        axios.get(`${API_BASE_URL}/api/teacher/progress`, { params: { teacher_username: username } }),
      ]);

      const classRows = Array.isArray(classRes?.data) ? classRes.data : [];
      const visibleStudentCount = Number(studentRes?.data?.total ?? 0);
      const progressRows = Array.isArray(progressRes?.data) ? progressRes.data : [];
      const activeStudentCount = new Set(
        progressRows
          .map((item) => String(item?.student_id || item?.username || '').trim())
          .filter(Boolean)
      ).size;
      const activityCount = progressRows.length;
      const completedActivityCount = progressRows.filter((item) => isCompletedProgressStatus(item?.status)).length;
      const completionRate = activityCount > 0 ? (completedActivityCount / activityCount) * 100 : 0;
      const courseStats = summarizeCourseStatsPayload(courseRes?.data);

      setCoreStats({
        classCount: classRows.length,
        visibleStudentCount,
        activeStudentCount,
        courseCount: Number(courseStats.courseCount || 0),
        experimentCount: Number(courseStats.experimentCount || 0),
        publishedExperimentCount: Number(courseStats.publishedExperimentCount || 0),
        activityCount,
        completedActivityCount,
        completionRate,
        updatedAt: new Date().toISOString(),
      });
    } catch (error) {
      if (!silent) {
        setErrorMessage(error?.response?.data?.detail || '加载基础统计失败');
      }
    } finally {
      setLoadingCore(false);
    }
  }, [username]);

  const loadUsageMonitor = useCallback(async ({ silent = false } = {}) => {
    setLoadingUsage(true);
    if (!silent) setErrorMessage('');
    try {
      const res = await axios.get(`${API_BASE_URL}/api/admin/usage-monitor`, {
        params: { admin_username: username },
      });
      setUsageMonitor(res.data || { summary: {}, by_role: {}, users: [], generated_at: '', scope: '' });
    } catch (error) {
      if (!silent) {
        setErrorMessage(error?.response?.data?.detail || '加载使用监控失败');
      }
    } finally {
      setLoadingUsage(false);
    }
  }, [username]);

  const loadAll = useCallback(async ({ silent = false } = {}) => {
    await Promise.all([loadCoreStats({ silent }), loadUsageMonitor({ silent })]);
  }, [loadCoreStats, loadUsageMonitor]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadAll({ silent: true });
    }, AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [loadAll]);

  const teacherUsage = usageMonitor?.by_role?.teacher || {};
  const studentUsage = usageMonitor?.by_role?.student || {};
  const usageUsers = Array.isArray(usageMonitor?.users) ? usageMonitor.users : [];

  const teacherActive = Number(usageMonitor?.summary?.active_teachers ?? teacherUsage.active_users ?? 0);
  const studentActive = Number(usageMonitor?.summary?.active_students ?? studentUsage.active_users ?? 0);
  const teacherSessionCount = Number(usageMonitor?.summary?.teacher_session_count ?? teacherUsage.session_count ?? 0);
  const studentSessionCount = Number(usageMonitor?.summary?.student_session_count ?? studentUsage.session_count ?? 0);
  const teacherDurationSeconds = Number(
    usageMonitor?.summary?.teacher_total_duration_seconds ?? teacherUsage.total_duration_with_active_seconds ?? 0
  );
  const studentDurationSeconds = Number(
    usageMonitor?.summary?.student_total_duration_seconds ?? studentUsage.total_duration_with_active_seconds ?? 0
  );
  const teacherTracked = Number(teacherUsage.tracked_users ?? 0);
  const studentTracked = Number(studentUsage.tracked_users ?? 0);

  const publishRate = coreStats.experimentCount > 0
    ? (coreStats.publishedExperimentCount / coreStats.experimentCount) * 100
    : 0;
  const activeStudentRate = coreStats.visibleStudentCount > 0
    ? (coreStats.activeStudentCount / coreStats.visibleStudentCount) * 100
    : 0;
  const teacherOnlineRate = teacherTracked > 0 ? (teacherActive / teacherTracked) * 100 : 0;
  const studentOnlineRate = studentTracked > 0 ? (studentActive / studentTracked) * 100 : 0;
  const teacherAvgSessionSeconds = teacherSessionCount > 0 ? teacherDurationSeconds / teacherSessionCount : 0;
  const studentAvgSessionSeconds = studentSessionCount > 0 ? studentDurationSeconds / studentSessionCount : 0;
  const activeUsersTotal = teacherActive + studentActive;
  const trackedUsersTotal = teacherTracked + studentTracked;
  const activeUsersRate = trackedUsersTotal > 0 ? (activeUsersTotal / trackedUsersTotal) * 100 : 0;

  const cards = [
    { code: 'CL', icon: 'grid', tone: 'blue', label: '班级数', value: formatCount(coreStats.classCount), note: '当前可管理的班级数量' },
    { code: 'ST', icon: 'users', tone: 'cyan', label: '可见学生', value: formatCount(coreStats.visibleStudentCount), note: '用户管理模块中可见学生总数' },
    { code: 'AS', icon: 'user-active', tone: 'green', label: '活跃学生', value: formatCount(coreStats.activeStudentCount), note: '基于进度记录去重后的学生数' },
    { code: 'CR', icon: 'book', tone: 'blue', label: '课程总数', value: formatCount(coreStats.courseCount), note: '当前教师可见课程数量' },
    { code: 'EX', icon: 'flask', tone: 'green', label: '实验总数', value: formatCount(coreStats.experimentCount), note: '全部课程下实验总量' },
    { code: 'PB', icon: 'rocket', tone: 'amber', label: '已发布实验', value: formatCount(coreStats.publishedExperimentCount), note: '处于发布状态的实验数量' },
    { code: 'AC', icon: 'activity', tone: 'violet', label: '学习活动', value: formatCount(coreStats.activityCount), note: '学生进度记录总条数' },
    { code: 'RT', icon: 'check-circle', tone: 'pink', label: '完成率', value: formatPercent(coreStats.completionRate), note: `已完成 ${formatCount(coreStats.completedActivityCount)} / ${formatCount(coreStats.activityCount)}` },
    { code: 'TU', icon: 'monitor', tone: 'blue', label: '在用教师', value: formatCount(teacherActive), note: 'Jupyter 当前在线/启动中的教师' },
    { code: 'SU', icon: 'monitor', tone: 'green', label: '在用学生', value: formatCount(studentActive), note: 'Jupyter 当前在线/启动中的学生' },
    { code: 'TC', icon: 'repeat', tone: 'slate', label: '教师使用次数', value: formatCount(teacherSessionCount), note: 'Jupyter 教师会话启动次数' },
    { code: 'SC', icon: 'repeat', tone: 'violet', label: '学生使用次数', value: formatCount(studentSessionCount), note: 'Jupyter 学生会话启动次数' },
    { code: 'TT', icon: 'clock', tone: 'blue', label: '教师使用时长', value: formatDuration(teacherDurationSeconds), note: 'Jupyter 教师累计使用时长' },
    { code: 'STM', icon: 'clock', tone: 'green', label: '学生使用时长', value: formatDuration(studentDurationSeconds), note: 'Jupyter 学生累计使用时长' },
  ];

  const ratioMetrics = [
    {
      key: 'completion-rate',
      label: '学习完成率',
      percent: coreStats.completionRate,
      valueText: formatPercent(coreStats.completionRate),
      note: `完成记录 ${formatCount(coreStats.completedActivityCount)} / ${formatCount(coreStats.activityCount)}`,
      color: '#2f84c8',
    },
    {
      key: 'publish-rate',
      label: '实验发布率',
      percent: publishRate,
      valueText: formatPercent(publishRate),
      note: `已发布实验 ${formatCount(coreStats.publishedExperimentCount)} / ${formatCount(coreStats.experimentCount)}`,
      color: '#ef9f2f',
    },
    {
      key: 'active-student-rate',
      label: '学生活跃覆盖率',
      percent: activeStudentRate,
      valueText: formatPercent(activeStudentRate),
      note: `活跃学生 ${formatCount(coreStats.activeStudentCount)} / ${formatCount(coreStats.visibleStudentCount)}`,
      color: '#37b06e',
    },
    {
      key: 'teacher-online-rate',
      label: '教师在线率（Jupyter）',
      percent: teacherOnlineRate,
      valueText: formatPercent(teacherOnlineRate),
      note: teacherTracked > 0 ? `在线教师 ${formatCount(teacherActive)} / ${formatCount(teacherTracked)}` : '暂无教师 Jupyter 使用记录',
      color: '#7a6be8',
    },
    {
      key: 'student-online-rate',
      label: '学生在线率（Jupyter）',
      percent: studentOnlineRate,
      valueText: formatPercent(studentOnlineRate),
      note: studentTracked > 0 ? `在线学生 ${formatCount(studentActive)} / ${formatCount(studentTracked)}` : '暂无学生 Jupyter 使用记录',
      color: '#2aa6b8',
    },
  ];

  const usageCompareGroups = [
    {
      key: 'online-users',
      label: '当前在线人数',
      teacherValue: teacherActive,
      studentValue: studentActive,
      formatter: formatCount,
    },
    {
      key: 'session-count',
      label: '累计会话次数',
      teacherValue: teacherSessionCount,
      studentValue: studentSessionCount,
      formatter: formatCount,
    },
    {
      key: 'duration-hours',
      label: '累计使用时长',
      teacherValue: teacherDurationSeconds,
      studentValue: studentDurationSeconds,
      formatter: formatHours,
    },
  ];

  const usageCompareFooters = [
    { key: 'teacher-avg', label: '教师平均单次时长', value: formatDuration(teacherAvgSessionSeconds) },
    { key: 'student-avg', label: '学生平均单次时长', value: formatDuration(studentAvgSessionSeconds) },
    { key: 'all-active', label: '当前活跃总人数', value: `${formatCount(activeUsersTotal)}（覆盖率 ${formatPercent(activeUsersRate)}）` },
  ];

  const topUsers = usageUsers
    .filter((row) => ['teacher', 'student'].includes(String(row?.role || '').toLowerCase()))
    .sort((a, b) => {
      const aOnline = (a?.server_running || a?.server_pending) ? 1 : 0;
      const bOnline = (b?.server_running || b?.server_pending) ? 1 : 0;
      if (bOnline !== aOnline) return bOnline - aOnline;
      const aSeconds = Number(a?.total_with_active_seconds ?? a?.total_seconds ?? 0);
      const bSeconds = Number(b?.total_with_active_seconds ?? b?.total_seconds ?? 0);
      if (bSeconds !== aSeconds) return bSeconds - aSeconds;
      const aSessions = Number(a?.session_count || 0);
      const bSessions = Number(b?.session_count || 0);
      return bSessions - aSessions;
    })
    .slice(0, 8);

  const isRefreshing = loadingCore || loadingUsage;
  const updatedAt = usageMonitor?.generated_at || coreStats.updatedAt;
  const scopeText = usageMonitor?.scope === 'jupyter_sessions' ? 'Jupyter 会话统计口径' : '实时统计口径';

  return (
    <section className="admin-sc-panel">
      <div className="admin-sc-head">
        <div className="admin-sc-title">
          <h2>数据统计中心</h2>
          <p>整合课程、实验、活动与 Jupyter 使用监控，展示实时统计与重点指标</p>
        </div>
        <div className="admin-sc-tools">
          <span className="admin-sc-pill">{scopeText}</span>
          <span className="admin-sc-pill">{`自动刷新 ${Math.round(AUTO_REFRESH_MS / 1000)} 秒`}</span>
          <span className="admin-sc-pill">
            {isRefreshing ? '更新中…' : `更新时间 ${formatDateTime(updatedAt)}`}
          </span>
          <button type="button" className="admin-sc-refresh" onClick={() => loadAll()} disabled={isRefreshing}>
            {isRefreshing ? '刷新中…' : '立即刷新'}
          </button>
        </div>
      </div>

      {errorMessage ? <div className="admin-sc-error">{errorMessage}</div> : null}

      <div className="admin-sc-row" role="list" aria-label="管理员统计卡片">
        {cards.map((item) => (
          <article className="admin-sc-card" key={item.code} role="listitem" style={toneStyle(item.tone)}>
            <div className="admin-sc-badge">
              <StatIcon name={item.icon} />
            </div>
            <div className="admin-sc-body">
              <div className="admin-sc-card-head">
                <h3>{item.label}</h3>
                <span className="admin-sc-code">{item.code}</span>
              </div>
              <div className="admin-sc-value">{item.value}</div>
              <p>{item.note}</p>
            </div>
          </article>
        ))}
      </div>

      <div className="admin-sc-charts">
        <MetricMeterPanel
          title="关键比率指标"
          subtitle="用于判断教学资源发布、学习完成与 Jupyter 实时活跃覆盖情况"
          metrics={ratioMetrics}
        />
        <CompareBarsPanel
          title="老师 / 学生使用对比"
          subtitle="对比当前在线、累计会话次数与累计使用时长（Jupyter 会话口径）"
          groups={usageCompareGroups}
          footerStats={usageCompareFooters}
        />
        <TopUsersPanel
          title="Jupyter 活跃用户 Top 8"
          subtitle="优先展示当前在线用户，其次按累计使用时长排序"
          rows={topUsers}
        />
      </div>
    </section>
  );
}

export default AdminStatsCenter;
