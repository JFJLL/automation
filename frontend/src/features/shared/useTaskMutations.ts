import { useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchJson } from '@/shared/api/client';
import { useToast } from '@/shared/components/Toast';

export function useTaskMutations(serviceBase: string, queryKeyPrefix: string) {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();
  const base = serviceBase.endsWith('/') ? serviceBase.slice(0, -1) : serviceBase;

  const runNowMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson<any>(base + '/tasks/' + taskId + '/run_now', { method: 'POST' }),
    onSuccess: (res: any) => {
      showSuccess(res?.message || '任务同步执行提交成功');
      queryClient.invalidateQueries({ queryKey: [queryKeyPrefix + 'Tasks'] });
      queryClient.invalidateQueries({ queryKey: [queryKeyPrefix + 'Runs'] });
    },
    onError: (err: any) => {
      showError(err.message || '运行失败');
    },
  });

  const toggleMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson<any>(base + '/tasks/' + taskId + '/toggle', { method: 'POST' }),
    onSuccess: (res: any) => {
      showSuccess(res?.new_status === 'paused' || res?.status === 'paused' ? '任务已暂停' : '任务已恢复调度');
      queryClient.invalidateQueries({ queryKey: [queryKeyPrefix + 'Tasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '状态切换失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson<any>(base + '/tasks/' + taskId, { method: 'DELETE' }),
    onSuccess: () => {
      showSuccess('任务已成功归档删除');
      queryClient.invalidateQueries({ queryKey: [queryKeyPrefix + 'Tasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '归档删除失败');
    },
  });

  const appendKeywordsMutation = useMutation({
    mutationFn: ({ taskId, keywords }: { taskId: number; keywords: string[] }) =>
      fetchJson<any>(base + '/tasks/' + taskId + '/append_keywords', {
        method: 'POST',
        body: JSON.stringify({ keywords }),
      }),
    onSuccess: () => {
      showSuccess('关键词追加成功');
      queryClient.invalidateQueries({ queryKey: [queryKeyPrefix + 'Tasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '追加关键词失败');
    },
  });

  const removeKeywordsMutation = useMutation({
    mutationFn: ({ taskId, keywords }: { taskId: number; keywords: string[] }) =>
      fetchJson<any>(base + '/tasks/' + taskId + '/remove_keywords', {
        method: 'POST',
        body: JSON.stringify({ keywords }),
      }),
    onSuccess: () => {
      showSuccess('关键词移除成功');
      queryClient.invalidateQueries({ queryKey: [queryKeyPrefix + 'Tasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '移除关键词失败');
    },
  });

  const isPendingTaskId = (taskId: number): boolean => {
    return (
      (runNowMutation.isPending && runNowMutation.variables === taskId) ||
      (toggleMutation.isPending && toggleMutation.variables === taskId) ||
      (deleteMutation.isPending && deleteMutation.variables === taskId) ||
      (appendKeywordsMutation.isPending && (appendKeywordsMutation.variables as any)?.taskId === taskId) ||
      (removeKeywordsMutation.isPending && (removeKeywordsMutation.variables as any)?.taskId === taskId)
    );
  };

  return {
    runNowMutation,
    toggleMutation,
    deleteMutation,
    appendKeywordsMutation,
    removeKeywordsMutation,
    isPendingTaskId,
  };
}