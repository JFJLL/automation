import React from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from '@/app/AppShell';
import { ImportPage } from '@/features/sync/pages/ImportPage';
import { TasksPage } from '@/features/sync/pages/TasksPage';
import { RunsPage } from '@/features/sync/pages/RunsPage';
import { KeywordInsightPage } from '@/features/keywords/pages/KeywordInsightPage';
import { KeywordTasksPage } from '@/features/keywords/pages/KeywordTasksPage';
import { KeywordRunsPage } from '@/features/keywords/pages/KeywordRunsPage';
import { SettingsPage } from '@/features/settings/pages/SettingsPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <Navigate to="/import" replace />,
      },
      {
        path: 'import',
        element: <ImportPage />,
      },
      {
        path: 'tasks',
        element: <TasksPage />,
      },
      {
        path: 'runs',
        element: <RunsPage />,
      },
      {
        path: 'keyword',
        element: <KeywordInsightPage />,
      },
      {
        path: 'keyword/tasks',
        element: <KeywordTasksPage />,
      },
      {
        path: 'keyword/runs',
        element: <KeywordRunsPage />,
      },
      {
        path: 'settings',
        element: <SettingsPage />,
      },
      {
        path: 'admin',
        element: <Navigate to="/settings" replace />,
      },
      {
        path: '*',
        element: <Navigate to="/import" replace />,
      },
    ],
  },
]);

