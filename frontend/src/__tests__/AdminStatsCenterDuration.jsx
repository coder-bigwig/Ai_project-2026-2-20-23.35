import { buildDurationModels } from '../AdminStatsCenter';

jest.mock('echarts/core', () => ({
  use: jest.fn(),
  init: jest.fn(),
}));
jest.mock('echarts/charts', () => ({ HeatmapChart: {} }));
jest.mock('echarts/components', () => ({
  GridComponent: {},
  TooltipComponent: {},
  VisualMapComponent: {},
}));
jest.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

test('duration heatmap uses course-student labels without exposing experiment UUIDs', () => {
  const models = buildDurationModels(
    [
      {
        student_id: '2401132029',
        experiment_id: '493154e7-85aa-4c43-a0ff-123456789abc',
        course_name: 'Python程序设计',
        start_time: '2026-05-29T19:00:00Z',
        submit_time: '2026-05-29T20:00:00Z',
        duration_status: 'completed',
        duration_seconds: 3600,
      },
    ],
    {}
  );

  expect(models.experiments[0].label).toBe('Python程序设计');
  expect(models.heatmapData[0].meta.experiment).toBe('Python程序设计-2401132029');
});

test('duration model resolves progress experiment UUIDs from teacher course payload', () => {
  const experimentId = '493154e7-8581-418f-afc3-cbee35b1c5b9';
  const models = buildDurationModels(
    [
      {
        student_id: '2401132028',
        experiment_id: experimentId,
        start_time: '2026-05-29T19:11:00Z',
        submit_time: null,
        duration_status: 'in_progress',
      },
    ],
    {},
    [
      {
        id: 'course-1',
        name: 'Python程序设计',
        experiments: [
          {
            id: experimentId,
            title: '实验一',
          },
        ],
      },
    ]
  );

  expect(models.experiments[0].label).toBe('Python程序设计');
  expect(models.filteredRows[0].experiment_title).toBe('实验一');
  expect(models.filteredRows[0].course_name).toBe('Python程序设计');
  expect(models.heatmapData[0].meta.experiment).toBe('Python程序设计-2401132028');
});
