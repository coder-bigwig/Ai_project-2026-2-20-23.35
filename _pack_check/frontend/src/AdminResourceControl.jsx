import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import './AdminResourceControl.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

function formatDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return '0 B';
  if (value < 1024) return `${value.toFixed(0)} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(2)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(2)} MB`;
  if (value < 1024 ** 4) return `${(value / 1024 ** 3).toFixed(2)} GB`;
  return `${(value / 1024 ** 4).toFixed(2)} TB`;
}

function formatDuration(seconds) {
  const value = Number(seconds || 0);
  if (!Number.isFinite(value) || value <= 0) return '0分钟';
  const totalSeconds = Math.floor(value);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (days > 0) return `${days}天 ${hours}小时 ${minutes}分钟`;
  if (hours > 0) return `${hours}小时 ${minutes}分钟`;
  return `${minutes}分钟`;
}

function toDraftMap(users) {
  const map = {};
  (users || []).forEach((item) => {
    map[item.username] = {
      cpu_limit: String(item?.quota?.cpu_limit ?? ''),
      memory_limit: String(item?.quota?.memory_limit ?? ''),
      storage_limit: String(item?.quota?.storage_limit ?? ''),
      note: String(item?.quota_note || ''),
    };
  });
  return map;
}

function toBudgetDraft(budget) {
  return {
    max_total_cpu: String(budget?.max_total_cpu ?? ''),
    max_total_memory: String(budget?.max_total_memory ?? ''),
    max_total_storage: String(budget?.max_total_storage ?? ''),
    enforce_budget: Boolean(budget?.enforce_budget),
  };
}

function AdminResourceControl({ username }) {
  const [overview, setOverview] = useState({ budget: {}, summary: {}, users: [] });
  const [drafts, setDrafts] = useState({});
  const [budgetDraft, setBudgetDraft] = useState(toBudgetDraft({}));
  const [logs, setLogs] = useState({ total: 0, items: [] });
  const [usageMonitor, setUsageMonitor] = useState({ summary: {}, by_role: {}, users: [] });
  const [logLimit, setLogLimit] = useState(200);
  const [keepRecent, setKeepRecent] = useState(200);
  const [loadingOverview, setLoadingOverview] = useState(false);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [loadingUsage, setLoadingUsage] = useState(false);
  const [savingUser, setSavingUser] = useState({});
  const [savingBudget, setSavingBudget] = useState(false);
  const [infoMessage, setInfoMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  const loadOverview = useCallback(async () => {
    setLoadingOverview(true);
    setErrorMessage('');
    try {
      const res = await axios.get(`${API_BASE_URL}/api/admin/resource-control/overview`, {
        params: { admin_username: username },
      });
      const payload = res.data || {};
      setOverview(payload);
      setDrafts(toDraftMap(payload.users || []));
      setBudgetDraft(toBudgetDraft(payload.budget || {}));
    } catch (error) {
      setErrorMessage(error?.response?.data?.detail || '加载资源监控数据失败');
    } finally {
      setLoadingOverview(false);
    }
  }, [username]);

  const loadUsageMonitor = useCallback(async () => {
    setLoadingUsage(true);
    try {
      const res = await axios.get(`${API_BASE_URL}/api/admin/usage-monitor`, {
        params: { admin_username: username },
      });
      setUsageMonitor(res.data || { summary: {}, by_role: {}, users: [] });
    } catch (error) {
      setErrorMessage(error?.response?.data?.detail || '加载使用监控失败');
    } finally {
      setLoadingUsage(false);
    }
  }, [username]);

  const loadLogs = useCallback(async (limit = logLimit) => {
    setLoadingLogs(true);
    try {
      const safeLimit = Math.max(20, Math.min(Number(limit) || 200, 1000));
      const res = await axios.get(`${API_BASE_URL}/api/admin/operation-logs`, {
        params: { admin_username: username, limit: safeLimit },
      });
      setLogs(res.data || { total: 0, items: [] });
    } catch (error) {
      setErrorMessage(error?.response?.data?.detail || '加载操作日志失败');
    } finally {
      setLoadingLogs(false);
    }
  }, [logLimit, username]);

  useEffect(() => {
    loadOverview();
    loadUsageMonitor();
    loadLogs();
  }, [loadOverview, loadUsageMonitor, loadLogs]);

  const rows = useMemo(() => (Array.isArray(overview?.users) ? overview.users : []), [overview]);
  const summary = overview?.summary || {};
  const usageSummary = usageMonitor?.summary || {};
  const teacherUsage = usageMonitor?.by_role?.teacher || {};
  const studentUsage = usageMonitor?.by_role?.student || {};

  const setRowDraftField = (rowUsername, field, value) => {
    setDrafts((prev) => ({
      ...prev,
      [rowUsername]: {
        ...(prev[rowUsername] || {}),
        [field]: value,
      },
    }));
  };

  const saveUserQuota = async (rowUsername) => {
    const draft = drafts[rowUsername];
    if (!draft) return;
    setSavingUser((prev) => ({ ...prev, [rowUsername]: true }));
    setErrorMessage('');
    setInfoMessage('');
    try {
      await axios.put(`${API_BASE_URL}/api/admin/resource-control/users/${encodeURIComponent(rowUsername)}`, {
        admin_username: username,
        cpu_limit: Number(draft.cpu_limit),
        memory_limit: draft.memory_limit,
        storage_limit: draft.storage_limit,
        note: draft.note || '',
      });
      setInfoMessage(`Updated quota for ${rowUsername}`);
      await loadOverview();
      await loadLogs();
    } catch (error) {
      setErrorMessage(error?.response?.data?.detail || `Failed to update quota for ${rowUsername}`);
    } finally {
      setSavingUser((prev) => ({ ...prev, [rowUsername]: false }));
    }
  };

  const resetUserQuota = async (rowUsername) => {
    setSavingUser((prev) => ({ ...prev, [rowUsername]: true }));
    setErrorMessage('');
    setInfoMessage('');
    try {
      await axios.delete(`${API_BASE_URL}/api/admin/resource-control/users/${encodeURIComponent(rowUsername)}`, {
        params: { admin_username: username },
      });
      setInfoMessage(`Reset quota for ${rowUsername}`);
      await loadOverview();
      await loadLogs();
    } catch (error) {
      setErrorMessage(error?.response?.data?.detail || `Failed to reset quota for ${rowUsername}`);
    } finally {
      setSavingUser((prev) => ({ ...prev, [rowUsername]: false }));
    }
  };

  const saveBudget = async () => {
    setSavingBudget(true);
    setErrorMessage('');
    setInfoMessage('');
    try {
      await axios.put(`${API_BASE_URL}/api/admin/resource-control/budget`, {
        admin_username: username,
        max_total_cpu: Number(budgetDraft.max_total_cpu),
        max_total_memory: budgetDraft.max_total_memory,
        max_total_storage: budgetDraft.max_total_storage,
        enforce_budget: Boolean(budgetDraft.enforce_budget),
      });
      setInfoMessage('服务器资源预算已更新');
      await loadOverview();
      await loadLogs();
    } catch (error) {
      setErrorMessage(error?.response?.data?.detail || 'Failed to update budget');
    } finally {
      setSavingBudget(false);
    }
  };

  const clearLogs = async () => {
    setErrorMessage('');
    setInfoMessage('');
    try {
      await axios.delete(`${API_BASE_URL}/api/admin/operation-logs`, {
        params: { admin_username: username, keep_recent: Math.max(0, Number(keepRecent) || 0) },
      });
      setInfoMessage('日志清理完成');
      await loadLogs();
    } catch (error) {
      setErrorMessage(error?.response?.data?.detail || '日志清理失败');
    }
  };

  return (
    <div className="admin-resource-panel">
      <div className="admin-resource-head">
        <h2>资源监控与配额管理</h2>
        <div className="admin-resource-head-actions">
          <button
            type="button"
            onClick={() => {
              loadOverview();
              loadUsageMonitor();
            }}
            disabled={loadingOverview || loadingUsage}
          >
            刷新资源监控
          </button>
          <button type="button" onClick={() => loadLogs()} disabled={loadingLogs}>刷新操作日志</button>
        </div>
      </div>

      {infoMessage ? <div className="admin-resource-notice success">{infoMessage}</div> : null}
      {errorMessage ? <div className="admin-resource-notice error">{errorMessage}</div> : null}

      <div className="admin-resource-summary-grid">
        <article>
          <h3>用户与容器概览</h3>
          <p>总用户数：{summary.total_users ?? 0}</p>
          <p>学生数：{summary.students ?? 0}</p>
          <p>教师数：{summary.teachers ?? 0}</p>
          <p>管理员数：{summary.admins ?? 0}</p>
          <p>运行中容器：{summary.running_servers ?? 0}</p>
        </article>
        <article>
          <h3>配额分配总量</h3>
          <p>CPU：{summary.assigned_cpu ?? 0} / {summary.budget_cpu ?? 0}</p>
          <p>内存：{formatBytes(summary.assigned_memory_bytes)} / {formatBytes(summary.budget_memory_bytes)}</p>
          <p>存储：{formatBytes(summary.assigned_storage_bytes)} / {formatBytes(summary.budget_storage_bytes)}</p>
        </article>
        <article>
          <h3>活跃容器占用</h3>
          <p>CPU：{summary.active_cpu ?? 0}</p>
          <p>内存：{formatBytes(summary.active_memory_bytes)}</p>
          <p>存储：{formatBytes(summary.active_storage_bytes)}</p>
        </article>
        <article>
          <h3>教师使用情况（Jupyter）</h3>
          <p>当前在用教师：{usageSummary.active_teachers ?? teacherUsage.active_users ?? 0}</p>
          <p>使用次数：{teacherUsage.session_count ?? 0}</p>
          <p>累计时长：{formatDuration(usageSummary.teacher_total_duration_seconds ?? teacherUsage.total_duration_with_active_seconds ?? 0)}</p>
          <p>统计口径：Jupyter 会话</p>
        </article>
        <article>
          <h3>学生使用情况（Jupyter）</h3>
          <p>当前在用学生：{usageSummary.active_students ?? studentUsage.active_users ?? 0}</p>
          <p>使用次数：{studentUsage.session_count ?? 0}</p>
          <p>累计时长：{formatDuration(usageSummary.student_total_duration_seconds ?? studentUsage.total_duration_with_active_seconds ?? 0)}</p>
          <p>统计时间：{formatDateTime(usageMonitor?.generated_at)}</p>
        </article>
      </div>

      <section className="admin-resource-budget">
        <h3>服务器预算配置</h3>
        <div className="admin-resource-budget-form">
          <label>
            CPU 总预算
            <input
              type="number"
              min="0.1"
              step="0.1"
              value={budgetDraft.max_total_cpu}
              onChange={(event) => setBudgetDraft((prev) => ({ ...prev, max_total_cpu: event.target.value }))}
            />
          </label>
          <label>
            内存总预算
            <input
              type="text"
              value={budgetDraft.max_total_memory}
              onChange={(event) => setBudgetDraft((prev) => ({ ...prev, max_total_memory: event.target.value }))}
              placeholder="例如 128G"
            />
          </label>
          <label>
            存储总预算
            <input
              type="text"
              value={budgetDraft.max_total_storage}
              onChange={(event) => setBudgetDraft((prev) => ({ ...prev, max_total_storage: event.target.value }))}
              placeholder="例如 1T"
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={budgetDraft.enforce_budget}
              onChange={(event) => setBudgetDraft((prev) => ({ ...prev, enforce_budget: event.target.checked }))}
            />
            启用硬性预算约束
          </label>
          <button type="button" onClick={saveBudget} disabled={savingBudget}>
            {savingBudget ? '保存中…' : '保存预算'}
          </button>
        </div>
      </section>

      <section className="admin-resource-users">
        <h3>教师/学生容器资源配额管理</h3>
        {loadingOverview ? (
          <div className="admin-resource-loading">正在加载用户配额...</div>
        ) : (
          <div className="admin-resource-table-wrap">
            <table className="admin-resource-table">
              <thead>
                <tr>
                  <th>用户</th>
                  <th>角色</th>
                  <th>班级</th>
                  <th>容器状态</th>
                  <th>CPU</th>
                  <th>内存</th>
                  <th>存储</th>
                  <th>备注</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan="9" className="empty">暂无用户数据</td>
                  </tr>
                ) : (
                  rows.map((item) => {
                    const draft = drafts[item.username] || {};
                    const busy = Boolean(savingUser[item.username]);
                    return (
                      <tr key={item.username}>
                        <td>
                          <strong>{item.username}</strong>
                          <div className="sub">{item.real_name || '-'}</div>
                        </td>
                        <td>{item.role}</td>
                        <td>{item.class_name || '-'}</td>
                        <td>
                          <span className={`status ${item.server_running ? 'running' : (item.server_pending ? 'pending' : 'stopped')}`}>
                            {item.server_running ? 'Running' : (item.server_pending ? 'Starting' : 'Stopped')}
                          </span>
                          <div className="sub">{formatDateTime(item.last_activity)}</div>
                        </td>
                        <td>
                          <input
                            type="number"
                            min="0.1"
                            step="0.1"
                            value={draft.cpu_limit ?? ''}
                            onChange={(event) => setRowDraftField(item.username, 'cpu_limit', event.target.value)}
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            value={draft.memory_limit ?? ''}
                            onChange={(event) => setRowDraftField(item.username, 'memory_limit', event.target.value)}
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            value={draft.storage_limit ?? ''}
                            onChange={(event) => setRowDraftField(item.username, 'storage_limit', event.target.value)}
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            value={draft.note ?? ''}
                            onChange={(event) => setRowDraftField(item.username, 'note', event.target.value)}
                            placeholder="可选备注"
                          />
                          <div className="sub">
                            {item.quota_source === 'custom'
                              ? `自定义：${item.quota_updated_by || '-'} ${formatDateTime(item.quota_updated_at)}`
                              : '默认配额'}
                          </div>
                        </td>
                        <td className="actions">
                          <button type="button" onClick={() => saveUserQuota(item.username)} disabled={busy}>
                            {busy ? '保存中…' : '保存'}
                          </button>
                          <button type="button" className="ghost" onClick={() => resetUserQuota(item.username)} disabled={busy}>
                            恢复默认
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="admin-resource-logs">
        <div className="admin-resource-logs-head">
          <h3>操作日志</h3>
          <div className="admin-resource-logs-actions">
            <label>
              查询条数
              <input
                type="number"
                min="20"
                max="1000"
                value={logLimit}
                onChange={(event) => setLogLimit(event.target.value)}
              />
            </label>
            <button type="button" onClick={() => loadLogs(logLimit)} disabled={loadingLogs}>刷新日志</button>
            <label>
              清理后保留
              <input
                type="number"
                min="0"
                max="1000"
                value={keepRecent}
                onChange={(event) => setKeepRecent(event.target.value)}
              />
            </label>
            <button type="button" className="danger" onClick={clearLogs}>清理日志</button>
          </div>
        </div>

        <div className="admin-resource-log-total">日志总数：{logs.total ?? 0}</div>
        <div className="admin-resource-table-wrap">
          <table className="admin-resource-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>操作人</th>
                <th>动作</th>
                <th>目标</th>
                <th>详情</th>
              </tr>
            </thead>
            <tbody>
              {(logs.items || []).length === 0 ? (
                <tr>
                  <td colSpan="5" className="empty">暂无日志</td>
                </tr>
              ) : (
                (logs.items || []).map((item) => (
                  <tr key={item.id}>
                    <td>{formatDateTime(item.created_at)}</td>
                    <td>{item.operator || '-'}</td>
                    <td>{item.action || '-'}</td>
                    <td>{item.target || '-'}</td>
                    <td>{item.detail || '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default AdminResourceControl;


