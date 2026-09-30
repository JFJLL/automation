import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchJson } from '@/shared/api/client';
import { TaskTable } from '@/features/shared/TaskTable';
import { useTaskMutations } from '@/features/shared/useTaskMutations';

export const LingxiTasksPage: React.FC = () => {
  const { data: tasks = [], isLoading, refetch } = useQuery<any[]>({
    queryKey: ['lingxiTasks'],
    queryFn: () => fetchJson('/api/lingxi/tasks'),
  });

  const mutations = useTaskMutations('/api/lingxi', 'lingxi');

  return (
    <TaskTable
      tasks={tasks}
      isLoading={isLoading}
      refetch={refetch}
      mutations={mutations}
      title="现有灵犀人群关键词监控任务"
      emptyText="暂无灵犀人群关键词监控任务"
    />
  );
};
