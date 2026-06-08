import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import AdminStatsCenter from '../AdminStatsCenter';

jest.mock('axios');

jest.mock('echarts/core', () => ({
  use: jest.fn(),
  init: jest.fn(() => ({
    setOption: jest.fn(),
    resize: jest.fn(),
    dispose: jest.fn(),
  })),
}));
jest.mock('echarts/charts', () => ({
  BarChart: {},
  HeatmapChart: {},
  PieChart: {},
}));
jest.mock('echarts/components', () => ({
  GridComponent: {},
  LegendComponent: {},
  TooltipComponent: {},
  VisualMapComponent: {},
}));
jest.mock('echarts/renderers', () => ({
  CanvasRenderer: {},
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

function mockStatsRequests() {
  axios.get.mockImplementation((url) => {
    if (url.includes('/api/admin/classes')) {
      return Promise.resolve({ data: [{ id: 'class-1' }] });
    }
    if (url.includes('/api/admin/students')) {
      return Promise.resolve({ data: { total: 2, items: [] } });
    }
    if (url.includes('/api/teacher/courses')) {
      return Promise.resolve({
        data: [{
          id: 'course-1',
          name: 'Python',
          experiments: [
            { id: 'exp-1', title: '实验一', published: true },
            { id: 'exp-2', title: '实验二', published: false },
          ],
        }],
      });
    }
    if (url.includes('/api/teacher/progress')) {
      return Promise.resolve({
        data: [],
      });
    }
    if (url.includes('/api/admin/usage-monitor')) {
      return Promise.resolve({
        data: {
          scope: 'jupyter_sessions',
          generated_at: '2026-06-03T14:16:00Z',
          summary: {
            active_teachers: 0,
            active_students: 0,
            teacher_session_count: 0,
            student_session_count: 0,
            teacher_total_duration_seconds: 0,
            student_total_duration_seconds: 0,
          },
          by_role: {
            teacher: { tracked_users: 1 },
            student: { tracked_users: 2 },
          },
          users: [],
        },
      });
    }
    return Promise.reject(new Error(`unexpected url: ${url}`));
  });
}

describe('AdminStatsCenter', () => {
  let container;
  let root;

  beforeEach(() => {
    jest.useFakeTimers();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    mockStatsRequests();
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    document.body.removeChild(container);
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it('hides Jupyter usage monitor analytics for teachers while keeping student duration analytics', async () => {
    await act(async () => {
      root.render(<AdminStatsCenter username="teacher_001" userRole="teacher" />);
    });

    await act(async () => {
      await Promise.resolve();
    });

    const text = container.textContent;
    expect(text).toContain('班级数');
    expect(text).toContain('关键比率指标');
    expect(text).toContain('学生实验用时');
    expect(text).toContain('学生实验用时热力矩阵');
    expect(text).toContain('最长耗时 Top 5');
    expect(container.querySelector('.admin-sc-duration-section')).not.toBeNull();
    expect(text).not.toContain('在用教师');
    expect(text).not.toContain('在用学生');
    expect(text).not.toContain('教师使用次数');
    expect(text).not.toContain('学生使用次数');
    expect(text).not.toContain('教师使用时长');
    expect(text).not.toContain('学生使用时长');
    expect(text).not.toContain('教师在线率（Jupyter）');
    expect(text).not.toContain('学生在线率（Jupyter）');
    expect(text).not.toContain('老师 / 学生使用对比');
    expect(text).not.toContain('Jupyter 活跃用户 Top 8');
    expect(text).not.toContain('新增分析');
    expect(text).not.toContain('学习完成分布');
    expect(text).not.toContain('教师 / 学生 Jupyter 使用对比');
    expect(text).not.toContain('实验平均用时 Top');
    expect(text).not.toContain('学生累计用时排行');
  });

  it('keeps Jupyter usage monitor analytics for admins', async () => {
    await act(async () => {
      root.render(<AdminStatsCenter username="fit_admin" userRole="admin" />);
    });

    await act(async () => {
      await Promise.resolve();
    });

    const text = container.textContent;
    expect(text).not.toContain('在用教师');
    expect(text).not.toContain('在用学生');
    expect(text).toContain('教师使用次数');
    expect(text).toContain('学生使用次数');
    expect(text).toContain('教师使用时长');
    expect(text).toContain('学生使用时长');
    expect(text).toContain('教师在线率（Jupyter）');
    expect(text).toContain('学生在线率（Jupyter）');
    expect(text).toContain('老师 / 学生使用对比');
    expect(text).toContain('Jupyter 活跃用户 Top 8');
    expect(text).toContain('学生实验用时');
  });
});
