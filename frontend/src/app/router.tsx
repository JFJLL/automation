import React from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from '@/app/AppShell';
import { ImportPage } from '@/features/sync/pages/ImportPage';
import { TasksPage } from '@/features/sync/pages/TasksPage';
import { RunsPage } from '@/features/sync/pages/RunsPage';
import { KeywordInsightPage } from '@/features/keywords/pages/KeywordInsightPage';
import { KeywordTasksPage } from '@/features/keywords/pages/KeywordTasksPage';
import { KeywordRunsPage } from '@/features/keywords/pages/KeywordRunsPage';
import { LingxiInsightPage } from '@/features/lingxi/pages/LingxiInsightPage';
import { LingxiTasksPage } from '@/features/lingxi/pages/LingxiTasksPage';
import { LingxiRunsPage } from '@/features/lingxi/pages/LingxiRunsPage';
import { SimplePromoWorkbenchPage } from '@/features/simple_promo/pages/SimplePromoWorkbenchPage';
import { SimplePromoTasksPage } from '@/features/simple_promo/pages/SimplePromoTasksPage';
import { SimplePromoRunsPage } from '@/features/simple_promo/pages/SimplePromoRunsPage';
import { AdminHomePage } from '@/features/admin/pages/AdminHomePage';
import { AdminTasksPage } from '@/features/admin/pages/AdminTasksPage';
import { AdminAuditPage } from '@/features/admin/pages/AdminAuditPage';
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
        path: 'lingxi',
        element: <LingxiInsightPage />,
      },
      {
        path: 'lingxi/tasks',
        element: <LingxiTasksPage />,
      },
      {
        path: 'lingxi/runs',
        element: <LingxiRunsPage />,
      },
      {
        path: 'admin',
        element: <AdminHomePage />,
      },
      {
        path: 'admin/tasks',
        element: <AdminTasksPage />,
      },
      {
        path: 'admin/audit',
        element: <AdminAuditPage />,
      },
      {
        path: 'admin/promo',
        element: <SimplePromoWorkbenchPage />,
      },
      {
        path: 'admin/promo/tasks',
        element: <SimplePromoTasksPage />,
      },
      {
        path: 'admin/promo/runs',
        element: <SimplePromoRunsPage />,
      },
      {
        path: 'simple-promo',
        element: <Navigate to="/admin/promo" replace />,
      },
      {
        path: 'simple-promo/tasks',
        element: <Navigate to="/admin/promo/tasks" replace />,
      },
      {
        path: 'simple-promo/runs',
        element: <Navigate to="/admin/promo/runs" replace />,
      },
      {
        path: 'admin/runs',
        element: <Navigate to="/admin/promo/runs" replace />,
      },
      {
        path: 'settings',
        element: <SettingsPage />,
      },
      {
        path: '*',
        element: <Navigate to="/import" replace />,
      },
    ],
  },
]);

