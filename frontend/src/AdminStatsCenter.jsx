import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import * as echarts from 'echarts/core';
import { BarChart, HeatmapChart, PieChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import './AdminStatsCenter.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';
const AUTO_REFRESH_MS = 30000;

echarts.use([
  BarChart,
  HeatmapChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

const CHART_COLORS = {
  blue: '#2f84c8',
  blueDark: '#1f5f95',
  green: '#37b06e',
  orange: '#ef9f2f',
  violet: '#7a6be8',
  pink: '#e75c93',
  red: '#e25555',
  slate: '#5d7a97',
  grid: '#e6eef7',
  text: '#234c72',
  muted: '#6b869f',
};

function clampPercent(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

function normalizeText(value) {
  return String(value ?? '').trim();
}

function formatDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function formatCount(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return '0';
  return n.toLocaleString('zh-CN');
}

function formatPercent(value) {
  return `${clampPercent(value).toFixed(1)}%`;
}

function formatDuration(seconds, emptyText = '-') {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return emptyText;
  if (value === 0) return '0分钟';
  const total = Math.floor(value);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}天${hours > 0 ? ` ${hours}小时` : ''}`;
  if (hours > 0) return `${hours}小时${minutes > 0 ? ` ${minutes}分钟` : ''}`;
  return `${Math.max(1, minutes)}分钟`;
}

function formatHours(seconds) {
  const value = Number(seconds || 0);
  if (!Number.isFinite(value) || value <= 0) return '0.0小时';
  return `${(value / 3600).toFixed(1)}小时`;
}

function isCompletedProgressStatus(status) {
  const value = String(status || '').toLowerCase();
  return (
    value.includes('graded') ||
    value.includes('submit') ||
    value.includes('submitted') ||
    value.includes('completed') ||
    value.includes('评分') ||
    value.includes('提交') ||
    value.includes('完成')
  );
}

function isInProgressRow(row) {
  if (isCompletedProgressStatus(row?.status)) return false;
  const status = String(row?.status || '').toLowerCase();
  return Boolean(row?.start_time) || status.includes('progress') || status.includes('进行');
}

function isCompletedDurationRow(row) {
  const seconds = Number(row?.duration_seconds);
  return row?.duration_status === 'completed' && Number.isFinite(seconds) && seconds >= 0;
}

function getStudentLabel(row) {
  return normalizeText(row?.student_name) || normalizeText(row?.student_id) || '未知学生';
}

function getExperimentLabel(row) {
  return normalizeText(row?.experiment_title) || normalizeText(row?.experiment_id) || '未命名实验';
}

function resolveCourseName(item) {
  const explicit = normalizeText(item?.course_name);
  if (explicit) return explicit;
  const explicitName = normalizeText(item?.name);
  if (explicitName) return explicitName;
  const path = normalizeText(item?.notebook_path);
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

function buildOptionBase() {
  return {
    animationDuration: 450,
    textStyle: {
      color: CHART_COLORS.text,
      fontFamily: 'Inter, PingFang SC, Microsoft YaHei, sans-serif',
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(21, 44, 68, 0.92)',
      borderColor: 'rgba(255,255,255,0.12)',
      textStyle: { color: '#fff', fontSize: 12 },
      confine: true,
    },
  };
}

function EChartPanel({ title, subtitle, option, empty, emptyText = '暂无可展示数据', height = 300, className = '' }) {
  const chartRef = useRef(null);

  useEffect(() => {
    if (!chartRef.current || empty) return undefined;
    const chart = echarts.init(chartRef.current, null, { renderer: 'canvas' });
    chart.setOption(option, true);

    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(chartRef.current);
    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      resizeObserver.disconnect();
      chart.dispose();
    };
  }, [option, empty]);

  return (
    <section className={`admin-sc-chart-panel ${className}`}>
      <div className="admin-sc-chart-head">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
      </div>
      {empty ? (
        <div className="admin-sc-chart-empty" style={{ minHeight: height }}>
          {emptyText}
        </div>
      ) : (
        <div ref={chartRef} className="admin-sc-echart" style={{ height }} />
      )}
    </section>
  );
}

function StatIcon({ name }) {
  const common = {
    width: 20,
    height: 20,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
  };

  switch (name) {
    case 'users':
      return (
        <svg {...common}>
          <path d="M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1" />
          <circle cx="9.5" cy="8" r="3" />
          <path d="M21 20v-1a4 4 0 0 0-3-3.86" />
          <path d="M16.5 5.2a3 3 0 0 1 0 5.6" />
        </svg>
      );
    case 'activity':
      return (
        <svg {...common}>
          <path d="M3 12h4l2.2-4.2L13 17l2.4-5H21" />
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
    case 'check':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8.5" />
          <path d="M8.8 12.2l2.2 2.2 4.3-4.4" />
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

function CoreMetricCard({ item }) {
  return (
    <article className={`admin-sc-metric is-${item.tone || 'blue'}`}>
      <div className="admin-sc-metric-icon">
        <StatIcon name={item.icon} />
      </div>
      <div className="admin-sc-metric-main">
        <div className="admin-sc-metric-label">{item.label}</div>
        <strong>{item.value}</strong>
        <span>{item.note}</span>
      </div>
      <div className="admin-sc-metric-track" aria-hidden="true">
        <div style={{ width: `${clampPercent(item.percent ?? 100)}%` }} />
      </div>
    </article>
  );
}

function buildDurationModels(progressRows, filters) {
  const sourceRows = Array.isArray(progressRows) ? progressRows : [];
  const normalizedFilters = filters || {};
  const optionMap = {
    courses: new Map(),
    experiments: new Map(),
    classes: new Map(),
    students: new Map(),
  };
  const putOption = (map, value, label) => {
    const normalized = normalizeText(value);
    if (!normalized || map.has(normalized)) return;
    map.set(normalized, { value: normalized, label: normalizeText(label) || normalized });
  };

  sourceRows.forEach((row) => {
    putOption(optionMap.courses, row?.course_name, row?.course_name);
    putOption(optionMap.experiments, row?.experiment_id, getExperimentLabel(row));
    putOption(optionMap.classes, row?.class_name, row?.class_name);
    putOption(optionMap.students, row?.student_id, getStudentLabel(row));
  });

  const filteredRows = sourceRows.filter((row) => {
    if (normalizedFilters.courseName && normalizeText(row?.course_name) !== normalizedFilters.courseName) return false;
    if (normalizedFilters.experimentId && normalizeText(row?.experiment_id) !== normalizedFilters.experimentId) return false;
    if (normalizedFilters.className && normalizeText(row?.class_name) !== normalizedFilters.className) return false;
    if (normalizedFilters.studentId && normalizeText(row?.student_id) !== normalizedFilters.studentId) return false;
    return true;
  });

  const completedRows = filteredRows.filter(isCompletedDurationRow);
  const durationValues = completedRows
    .map((row) => Number(row.duration_seconds))
    .filter((value) => Number.isFinite(value) && value >= 0);
  const durationTotal = durationValues.reduce((sum, value) => sum + value, 0);

  const groupBy = (keyGetter, labelGetter, subLabelGetter) => {
    const groups = new Map();
    completedRows.forEach((row) => {
      const key = keyGetter(row);
      if (!key) return;
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          label: labelGetter(row),
          subLabel: subLabelGetter(row),
          total: 0,
          count: 0,
        });
      }
      const item = groups.get(key);
      item.total += Number(row.duration_seconds || 0);
      item.count += 1;
    });
    return Array.from(groups.values());
  };

  const experimentAverages = groupBy(
    (row) => normalizeText(row?.experiment_id) || getExperimentLabel(row),
    getExperimentLabel,
    (row) => normalizeText(row?.course_name) || '未归属课程',
  )
    .map((item) => ({ ...item, value: item.count > 0 ? item.total / item.count : 0 }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10);

  const studentTotals = groupBy(
    (row) => normalizeText(row?.student_id) || getStudentLabel(row),
    getStudentLabel,
    (row) => normalizeText(row?.class_name) || '未分班',
  )
    .map((item) => ({ ...item, value: item.total }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10);

  const latestCellRows = new Map();
  const studentMap = new Map();
  const experimentMap = new Map();
  const rowTime = (row) => {
    const time = Date.parse(row?.submit_time || row?.start_time || '');
    return Number.isFinite(time) ? time : 0;
  };
  filteredRows.forEach((row) => {
    const studentId = normalizeText(row?.student_id);
    const experimentId = normalizeText(row?.experiment_id);
    if (!studentId || !experimentId) return;
    if (!studentMap.has(studentId)) {
      studentMap.set(studentId, {
        value: studentId,
        label: getStudentLabel(row),
        subLabel: normalizeText(row?.class_name),
      });
    }
    if (!experimentMap.has(experimentId)) {
      experimentMap.set(experimentId, {
        value: experimentId,
        label: getExperimentLabel(row),
        subLabel: normalizeText(row?.course_name),
      });
    }
    const key = `${studentId}::${experimentId}`;
    const existing = latestCellRows.get(key);
    if (!existing || rowTime(row) >= rowTime(existing)) {
      latestCellRows.set(key, row);
    }
  });

  const sortByLabel = (items) => [...items].sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
  const students = sortByLabel(Array.from(studentMap.values())).slice(0, 30);
  const experiments = sortByLabel(Array.from(experimentMap.values())).slice(0, 20);
  const maxMinutes = Math.max(1, ...Array.from(latestCellRows.values()).filter(isCompletedDurationRow).map((row) => Math.ceil(Number(row.duration_seconds || 0) / 60)));
  const lowMax = Math.max(1, Math.ceil(maxMinutes * 0.33));
  const mediumMax = Math.max(lowMax + 1, Math.ceil(maxMinutes * 0.66));
  const heatmapData = [];
  experiments.forEach((experiment, xIndex) => {
    students.forEach((student, yIndex) => {
      const row = latestCellRows.get(`${student.value}::${experiment.value}`);
      const valid = isCompletedDurationRow(row);
      const minutes = valid ? Math.max(0, Math.ceil(Number(row.duration_seconds || 0) / 60)) : -1;
      heatmapData.push({
        value: [xIndex, yIndex, minutes],
        meta: {
          student: student.label,
          experiment: experiment.label,
          startTime: row?.start_time,
          submitTime: row?.submit_time,
          duration: valid ? Number(row.duration_seconds || 0) : null,
          status: row?.duration_status || 'none',
        },
      });
    });
  });

  return {
    options: {
      courses: sortByLabel(Array.from(optionMap.courses.values())),
      experiments: sortByLabel(Array.from(optionMap.experiments.values())),
      classes: sortByLabel(Array.from(optionMap.classes.values())),
      students: sortByLabel(Array.from(optionMap.students.values())),
    },
    filteredRows,
    completedRows,
    summary: {
      count: durationValues.length,
      average: durationValues.length > 0 ? durationTotal / durationValues.length : 0,
      max: durationValues.length > 0 ? Math.max(...durationValues) : 0,
      min: durationValues.length > 0 ? Math.min(...durationValues) : 0,
    },
    experimentAverages,
    studentTotals,
    students,
    experiments,
    heatmapData,
    heatmapRange: { maxMinutes, lowMax, mediumMax },
    longestRows: [...completedRows].sort((a, b) => Number(b.duration_seconds || 0) - Number(a.duration_seconds || 0)).slice(0, 5),
  };
}

function DurationAnalyticsSection({ models, filters, onFiltersChange }) {
  const [showDetails, setShowDetails] = useState(false);
  const hasAnyFilter = Boolean(filters.courseName || filters.experimentId || filters.className || filters.studentId);
  const handleFilterChange = (key, value) => {
    onFiltersChange((prev) => ({ ...(prev || {}), [key]: value }));
  };
  const resetFilters = () => onFiltersChange({ courseName: '', experimentId: '', className: '', studentId: '' });

  const heatmapOption = useMemo(() => ({
    ...buildOptionBase(),
    tooltip: {
      ...buildOptionBase().tooltip,
      formatter: (params) => {
        const meta = params?.data?.meta || {};
        return [
          `<strong>${meta.student || '-'}</strong>`,
          `实验：${meta.experiment || '-'}`,
          `开始：${formatDateTime(meta.startTime)}`,
          `提交：${formatDateTime(meta.submitTime)}`,
          `耗时：${meta.duration === null || meta.duration === undefined ? '-' : formatDuration(meta.duration)}`,
        ].join('<br/>');
      },
    },
    grid: { left: 88, right: 18, top: 32, bottom: 78 },
    xAxis: {
      type: 'category',
      data: models.experiments.map((item) => item.label),
      axisLabel: { rotate: 35, color: CHART_COLORS.muted, fontSize: 11, overflow: 'truncate', width: 84 },
      axisLine: { lineStyle: { color: CHART_COLORS.grid } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: models.students.map((item) => item.label),
      axisLabel: { color: CHART_COLORS.muted, fontSize: 11, overflow: 'truncate', width: 78 },
      axisLine: { lineStyle: { color: CHART_COLORS.grid } },
      axisTick: { show: false },
    },
    visualMap: {
      show: false,
      type: 'piecewise',
      pieces: [
        { value: -1, color: '#eef2f7' },
        { min: 0, max: models.heatmapRange.lowMax, color: '#dbeafe' },
        { min: models.heatmapRange.lowMax + 1, max: models.heatmapRange.mediumMax, color: '#93c5fd' },
        { min: models.heatmapRange.mediumMax + 1, color: '#2563eb' },
      ],
    },
    series: [{
      type: 'heatmap',
      data: models.heatmapData,
      label: {
        show: true,
        formatter: (params) => {
          const meta = params?.data?.meta || {};
          return meta.duration === null || meta.duration === undefined ? '-' : formatDuration(meta.duration);
        },
        color: '#173f66',
        fontSize: 10,
      },
      emphasis: {
        itemStyle: {
          borderColor: '#173f66',
          borderWidth: 1,
        },
      },
    }],
  }), [models]);

  return (
    <section className="admin-sc-duration-section">
      <div className="admin-sc-section-title">
        <div>
          <h3>学生实验用时</h3>
          <p>统计口径固定为提交时间减开始时间，筛选条件会同步影响热力图、排行和明细。</p>
        </div>
        <span>{formatCount(models.filteredRows.length)} 条进度记录</span>
      </div>

      <div className="admin-sc-duration-filters">
        <label>
          <span>课程</span>
          <select value={filters.courseName || ''} onChange={(event) => handleFilterChange('courseName', event.target.value)}>
            <option value="">全部课程</option>
            {models.options.courses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label>
          <span>实验</span>
          <select value={filters.experimentId || ''} onChange={(event) => handleFilterChange('experimentId', event.target.value)}>
            <option value="">全部实验</option>
            {models.options.experiments.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label>
          <span>班级</span>
          <select value={filters.className || ''} onChange={(event) => handleFilterChange('className', event.target.value)}>
            <option value="">全部班级</option>
            {models.options.classes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label>
          <span>学生</span>
          <select value={filters.studentId || ''} onChange={(event) => handleFilterChange('studentId', event.target.value)}>
            <option value="">全部学生</option>
            {models.options.students.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <button type="button" onClick={resetFilters} disabled={!hasAnyFilter}>重置</button>
      </div>

      <div className="admin-sc-duration-board">
        <EChartPanel
          title="学生实验用时热力矩阵"
          subtitle="横轴实验，纵轴学生；颜色越深表示耗时越长，灰色表示无完成数据"
          option={heatmapOption}
          empty={models.students.length === 0 || models.experiments.length === 0}
          emptyText="暂无学生实验用时数据"
          height={390}
          className="admin-sc-heatmap-panel"
        />
        <aside className="admin-sc-longest-panel">
          <div className="admin-sc-chart-head">
            <div>
              <h3>最长耗时 Top 5</h3>
              <p>用于快速定位耗时异常的学生与实验。</p>
            </div>
          </div>
          {models.longestRows.length === 0 ? (
            <div className="admin-sc-chart-empty">暂无完成记录</div>
          ) : (
            <div className="admin-sc-longest-list">
              {models.longestRows.map((row, index) => (
                <div className="admin-sc-longest-row" key={`${row.student_id}-${row.experiment_id}-${index}`}>
                  <span>{index + 1}</span>
                  <div>
                    <strong>{getStudentLabel(row)}</strong>
                    <small>{getExperimentLabel(row)}</small>
                  </div>
                  <b>{formatDuration(row.duration_seconds)}</b>
                </div>
              ))}
            </div>
          )}
          <div className="admin-sc-duration-mini">
            <span>完成记录</span><strong>{formatCount(models.summary.count)}</strong>
            <span>平均用时</span><strong>{models.summary.count > 0 ? formatDuration(models.summary.average) : '-'}</strong>
            <span>最长 / 最短</span><strong>{models.summary.count > 0 ? `${formatDuration(models.summary.max)} / ${formatDuration(models.summary.min)}` : '-'}</strong>
          </div>
        </aside>
      </div>

      <div className="admin-sc-detail-toggle">
        <button type="button" onClick={() => setShowDetails((value) => !value)}>
          {showDetails ? '收起明细' : '查看明细'}
        </button>
      </div>

      {showDetails ? (
        <div className="admin-sc-detail-table-wrap">
          <table className="admin-sc-detail-table">
            <thead>
              <tr>
                <th>学生</th>
                <th>班级</th>
                <th>实验</th>
                <th>课程</th>
                <th>开始时间</th>
                <th>提交时间</th>
                <th>耗时</th>
              </tr>
            </thead>
            <tbody>
              {models.filteredRows.length === 0 ? (
                <tr><td colSpan="7">当前筛选下暂无进度记录</td></tr>
              ) : (
                models.filteredRows.map((row, index) => (
                  <tr key={`${row.student_id}-${row.experiment_id}-${index}`}>
                    <td>{getStudentLabel(row)}</td>
                    <td>{normalizeText(row.class_name) || '-'}</td>
                    <td>{getExperimentLabel(row)}</td>
                    <td>{normalizeText(row.course_name) || '-'}</td>
                    <td>{formatDateTime(row.start_time)}</td>
                    <td>{formatDateTime(row.submit_time)}</td>
                    <td>{isCompletedDurationRow(row) ? formatDuration(row.duration_seconds) : '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      ) : null}
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
  const [progressRows, setProgressRows] = useState([]);
  const [durationFilters, setDurationFilters] = useState({ courseName: '', experimentId: '', className: '', studentId: '' });
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
      const fetchedProgressRows = Array.isArray(progressRes?.data) ? progressRes.data : [];
      const activeStudentCount = new Set(
        fetchedProgressRows
          .map((item) => normalizeText(item?.student_id || item?.username))
          .filter(Boolean)
      ).size;
      const activityCount = fetchedProgressRows.length;
      const completedActivityCount = fetchedProgressRows.filter((item) => isCompletedProgressStatus(item?.status)).length;
      const completionRate = activityCount > 0 ? (completedActivityCount / activityCount) * 100 : 0;
      const courseStats = summarizeCourseStatsPayload(courseRes?.data);

      setProgressRows(fetchedProgressRows);
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
      setProgressRows([]);
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
      if (error?.response?.status === 403) {
        setUsageMonitor({ summary: {}, by_role: {}, users: [], generated_at: '', scope: '' });
        return;
      }
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

  const durationModels = useMemo(
    () => buildDurationModels(progressRows, durationFilters),
    [progressRows, durationFilters]
  );

  const inProgressCount = progressRows.filter(isInProgressRow).length;
  const notStartedCount = Math.max(0, coreStats.activityCount - coreStats.completedActivityCount - inProgressCount);
  const activeStudentRate = coreStats.visibleStudentCount > 0
    ? (coreStats.activeStudentCount / coreStats.visibleStudentCount) * 100
    : 0;
  const averageExperimentDuration = durationModels.summary.count > 0 ? durationModels.summary.average : 0;

  const metrics = [
    {
      key: 'students',
      icon: 'users',
      tone: 'blue',
      label: '可见学生',
      value: formatCount(coreStats.visibleStudentCount),
      note: `活跃 ${formatCount(coreStats.activeStudentCount)} 人`,
      percent: activeStudentRate,
    },
    {
      key: 'active',
      icon: 'activity',
      tone: 'green',
      label: '活跃学生',
      value: formatCount(coreStats.activeStudentCount),
      note: `覆盖率 ${formatPercent(activeStudentRate)}`,
      percent: activeStudentRate,
    },
    {
      key: 'courses',
      icon: 'book',
      tone: 'blue',
      label: '课程数',
      value: formatCount(coreStats.courseCount),
      note: `已发布实验 ${formatCount(coreStats.publishedExperimentCount)}`,
      percent: coreStats.experimentCount > 0 ? (coreStats.publishedExperimentCount / coreStats.experimentCount) * 100 : 0,
    },
    {
      key: 'experiments',
      icon: 'flask',
      tone: 'green',
      label: '实验数',
      value: formatCount(coreStats.experimentCount),
      note: `学习记录 ${formatCount(coreStats.activityCount)}`,
      percent: 100,
    },
    {
      key: 'completion',
      icon: 'check',
      tone: 'pink',
      label: '完成率',
      value: formatPercent(coreStats.completionRate),
      note: `${formatCount(coreStats.completedActivityCount)} / ${formatCount(coreStats.activityCount)}`,
      percent: coreStats.completionRate,
    },
    {
      key: 'duration',
      icon: 'clock',
      tone: 'orange',
      label: '平均实验用时',
      value: durationModels.summary.count > 0 ? formatDuration(averageExperimentDuration) : '-',
      note: `完成记录 ${formatCount(durationModels.summary.count)} 条`,
      percent: durationModels.summary.count > 0 ? 100 : 0,
    },
  ];

  const completionOption = useMemo(() => ({
    ...buildOptionBase(),
    tooltip: { ...buildOptionBase().tooltip, trigger: 'item', formatter: '{b}<br/>{c} 条 ({d}%)' },
    legend: {
      bottom: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { color: CHART_COLORS.muted, fontSize: 11 },
    },
    series: [{
      name: '学习完成',
      type: 'pie',
      radius: ['54%', '74%'],
      center: ['50%', '43%'],
      avoidLabelOverlap: true,
      label: {
        formatter: '{b}\n{d}%',
        color: CHART_COLORS.text,
        fontSize: 12,
      },
      labelLine: { length: 8, length2: 6 },
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      data: [
        { value: coreStats.completedActivityCount, name: '已完成', itemStyle: { color: CHART_COLORS.green } },
        { value: inProgressCount, name: '进行中', itemStyle: { color: CHART_COLORS.orange } },
        { value: notStartedCount, name: '未开始', itemStyle: { color: '#cbd5e1' } },
      ],
    }],
  }), [coreStats.completedActivityCount, inProgressCount, notStartedCount]);

  const usageCompareOption = useMemo(() => ({
    ...buildOptionBase(),
    tooltip: {
      ...buildOptionBase().tooltip,
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => params.map((item) => {
        const isDuration = item.axisValue.includes('时长');
        const valueText = isDuration ? `${Number(item.value || 0).toFixed(1)}小时` : formatCount(item.value);
        return `${item.marker}${item.seriesName}：${valueText}`;
      }).join('<br/>'),
    },
    legend: {
      top: 0,
      right: 0,
      icon: 'roundRect',
      textStyle: { color: CHART_COLORS.muted, fontSize: 11 },
    },
    grid: { left: 42, right: 18, top: 46, bottom: 34 },
    xAxis: {
      type: 'category',
      data: ['在线人数', '会话次数', '累计时长'],
      axisTick: { show: false },
      axisLine: { lineStyle: { color: CHART_COLORS.grid } },
      axisLabel: { color: CHART_COLORS.muted, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: CHART_COLORS.grid, type: 'dashed' } },
      axisLabel: { color: CHART_COLORS.muted, fontSize: 11 },
    },
    series: [
      {
        name: '教师',
        type: 'bar',
        barMaxWidth: 24,
        itemStyle: { color: CHART_COLORS.blue, borderRadius: [6, 6, 0, 0] },
        data: [teacherActive, teacherSessionCount, Number((teacherDurationSeconds / 3600).toFixed(1))],
      },
      {
        name: '学生',
        type: 'bar',
        barMaxWidth: 24,
        itemStyle: { color: CHART_COLORS.green, borderRadius: [6, 6, 0, 0] },
        data: [studentActive, studentSessionCount, Number((studentDurationSeconds / 3600).toFixed(1))],
      },
    ],
  }), [studentActive, studentDurationSeconds, studentSessionCount, teacherActive, teacherDurationSeconds, teacherSessionCount]);

  const experimentDurationOption = useMemo(() => {
    const rows = [...durationModels.experimentAverages].reverse();
    return {
      ...buildOptionBase(),
      tooltip: {
        ...buildOptionBase().tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const item = params?.[0];
          const row = rows[item?.dataIndex] || {};
          return `${item?.marker || ''}${row.label || '-'}<br/>平均用时：${formatDuration(row.value)}<br/>完成记录：${formatCount(row.count)}`;
        },
      },
      grid: { left: 112, right: 24, top: 18, bottom: 24 },
      xAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: CHART_COLORS.grid, type: 'dashed' } },
        axisLabel: { color: CHART_COLORS.muted, fontSize: 11, formatter: (value) => `${Math.round(value / 60)}分` },
      },
      yAxis: {
        type: 'category',
        data: rows.map((item) => item.label),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: CHART_COLORS.grid } },
        axisLabel: { color: CHART_COLORS.muted, fontSize: 11, overflow: 'truncate', width: 100 },
      },
      series: [{
        type: 'bar',
        data: rows.map((item) => item.value),
        barMaxWidth: 18,
        itemStyle: { color: CHART_COLORS.orange, borderRadius: [0, 6, 6, 0] },
      }],
    };
  }, [durationModels.experimentAverages]);

  const studentDurationOption = useMemo(() => {
    const rows = [...durationModels.studentTotals].reverse();
    return {
      ...buildOptionBase(),
      tooltip: {
        ...buildOptionBase().tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const item = params?.[0];
          const row = rows[item?.dataIndex] || {};
          return `${item?.marker || ''}${row.label || '-'}<br/>累计用时：${formatDuration(row.value)}<br/>完成实验：${formatCount(row.count)}`;
        },
      },
      grid: { left: 96, right: 24, top: 18, bottom: 24 },
      xAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: CHART_COLORS.grid, type: 'dashed' } },
        axisLabel: { color: CHART_COLORS.muted, fontSize: 11, formatter: (value) => `${Math.round(value / 3600)}h` },
      },
      yAxis: {
        type: 'category',
        data: rows.map((item) => item.label),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: CHART_COLORS.grid } },
        axisLabel: { color: CHART_COLORS.muted, fontSize: 11, overflow: 'truncate', width: 82 },
      },
      series: [{
        type: 'bar',
        data: rows.map((item) => item.value),
        barMaxWidth: 18,
        itemStyle: { color: CHART_COLORS.violet, borderRadius: [0, 6, 6, 0] },
      }],
    };
  }, [durationModels.studentTotals]);

  const isRefreshing = loadingCore || loadingUsage;
  const updatedAt = usageMonitor?.generated_at || coreStats.updatedAt;
  const scopeText = usageMonitor?.scope === 'jupyter_sessions' ? 'Jupyter 会话统计口径' : '实时统计口径';

  return (
    <section className="admin-sc-panel">
      <div className="admin-sc-head">
        <div className="admin-sc-title">
          <h2>数据统计中心</h2>
          <p>面向教师的教学运营看板，聚合课程、实验完成、Jupyter 使用与学生实验用时。</p>
        </div>
        <div className="admin-sc-tools">
          <span className="admin-sc-pill">{scopeText}</span>
          <span className="admin-sc-pill">{`自动刷新 ${Math.round(AUTO_REFRESH_MS / 1000)} 秒`}</span>
          <span className="admin-sc-pill">
            {isRefreshing ? '更新中...' : `更新时间 ${formatDateTime(updatedAt)}`}
          </span>
          <button type="button" className="admin-sc-refresh" onClick={() => loadAll()} disabled={isRefreshing}>
            {isRefreshing ? '刷新中...' : '立即刷新'}
          </button>
        </div>
      </div>

      {errorMessage ? <div className="admin-sc-error">{errorMessage}</div> : null}

      <div className="admin-sc-metrics" role="list" aria-label="核心统计指标">
        {metrics.map((item) => <CoreMetricCard item={item} key={item.key} />)}
      </div>

      <div className="admin-sc-dashboard-grid">
        <EChartPanel
          title="学习完成分布"
          subtitle="按学生实验进度记录统计完成、进行中与未开始"
          option={completionOption}
          empty={coreStats.activityCount === 0}
          emptyText="暂无学习进度记录"
          height={300}
        />
        <EChartPanel
          title="教师 / 学生 Jupyter 使用对比"
          subtitle={`教师累计 ${formatHours(teacherDurationSeconds)}，学生累计 ${formatHours(studentDurationSeconds)}`}
          option={usageCompareOption}
          empty={teacherSessionCount + studentSessionCount + teacherActive + studentActive === 0}
          emptyText="暂无 Jupyter 使用记录"
          height={300}
        />
        <EChartPanel
          title="实验平均用时 Top"
          subtitle="按完成记录的平均自然耗时排序"
          option={experimentDurationOption}
          empty={durationModels.experimentAverages.length === 0}
          emptyText="暂无完成实验用时"
          height={320}
        />
        <EChartPanel
          title="学生累计用时排行"
          subtitle="按已完成实验的累计自然耗时排序"
          option={studentDurationOption}
          empty={durationModels.studentTotals.length === 0}
          emptyText="暂无学生完成用时"
          height={320}
        />
      </div>

      <DurationAnalyticsSection
        models={durationModels}
        filters={durationFilters}
        onFiltersChange={setDurationFilters}
      />
    </section>
  );
}

export default AdminStatsCenter;
