import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchJson } from '@/shared/api/client';
import { TaskTable } from '@/features/shared/TaskTable';
import { useTaskMutations } from '@/features/shared/useTaskMutations';

export const KeywordTasksPage: React.FC = () => {
  const { data: tasks = [], isLoading, refetch } = useQuery<any[]>({
    queryKey: ['keywordTasks'],
    queryFn: () => fetchJson('/api/keyword/tasks'),
  });

  const mutations = useTaskMutations('/api/keyword', 'keyword');

  return (
    <TaskTable
      tasks={tasks}
      isLoading={isLoading}
      refetch={refetch}
      mutations={mutations}
      title="现有聚光关键词监控任务"
      emptyText="暂无聚光关键词监控任务"
    />
  );
};
