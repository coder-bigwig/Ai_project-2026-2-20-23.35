import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import TeacherDashboard from '../TeacherDashboard';

jest.mock('axios');

jest.mock('../AdminStatsCenter', () => function MockAdminStatsCenter() {
  return <div>mock stats center</div>;
});

jest.mock('../AdminResourceControl', () => function MockAdminResourceControl() {
  return <div>mock resource control</div>;
});

global.IS_REACT_ACT_ENVIRONMENT = true;

function renderDashboard(props) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  act(() => {
    root.render(
      <MemoryRouter>
        <TeacherDashboard {...props} />
      </MemoryRouter>
    );
  });

  return { container, root };
}

describe('TeacherDashboard tabs', () => {
  beforeEach(() => {
    localStorage.clear();
    axios.get.mockImplementation((url) => {
      if (url.includes('/api/teacher/courses')) return Promise.resolve({ data: [] });
      if (url.includes('/api/teacher/progress')) return Promise.resolve({ data: [] });
      return Promise.reject(new Error(`unexpected url: ${url}`));
    });
  });

  afterEach(() => {
    localStorage.clear();
    jest.restoreAllMocks();
  });

  it('shows the statistics center tab to teachers without showing admin resource controls', async () => {
    const { container, root } = renderDashboard({
      username: 'teacher_001',
      userRole: 'teacher',
      onLogout: jest.fn(),
    });

    await act(async () => {
      await Promise.resolve();
    });

    const menuButtons = Array.from(container.querySelectorAll('.teacher-lab-sidebar .teacher-lab-menu-item'));
    expect(menuButtons).toHaveLength(8);
    expect(container.textContent).toContain('统计中心');
    expect(container.textContent).not.toContain('资源监控');

    await act(async () => {
      root.unmount();
    });
    document.body.removeChild(container);
  });
});
