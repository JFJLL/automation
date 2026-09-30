import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Play, Pause, Trash2, ExternalLink, RefreshCw, Calendar, FileText } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Button } from '@/shared/components/Button';
import { StatusBadge } from '@/shared/components/Badge';
import { Dialog } from '@/shared/components/Dialog';
import { useToast } from '@/shared/components/Toast';

export const TasksPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  const { data: tasks = [], isLoading, refetch } = useQuery<any[]>({
    queryKey: ['syncTasks'],
    queryFn: () => fetchJson('/api/tasks'),
  });

  const runNowMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/tasks/${taskId}/run_now`, { method: 'POST' }),
    onSuccess: (res: any) => {
      showSuccess(res.message || '任务同步执行完成');
      queryClient.invalidateQueries({ queryKey: ['syncTasks'] });
      queryClient.invalidateQueries({ queryKey: ['syncRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '执行同步失败');
    },
  });

  const toggleMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/tasks/${taskId}/toggle_status`, { method: 'POST' }),
    onSuccess: (res: any) => {
      showSuccess(`任务状态已切换为: ${res.status === 'active' ? '正常运行' : '已暂停'}`);
      queryClient.invalidateQueries({ queryKey: ['syncTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '切换状态失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/tasks/${taskId}`, { method: 'DELETE' }),
    onSuccess: () => {
      showSuccess('任务已归档删除');
      setDeleteConfirmId(null);
      queryClient.invalidateQueries({ queryKey: ['syncTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '删除任务失败');
    },
  });

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>数据同步任务管理</h2>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
            管理已配置的电商报表自动同步计划与飞书表格连接
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => refetch()}>
          <RefreshCw size={14} /> 刷新任务
        </Button>
      </div>

      <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', overflow: 'hidden' }}>
        {isLoading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>加载任务列表中...</div>
        ) : tasks.length === 0 ? (
          <div style={{ padding: '60px 20px', textAlign: 'center', color: '#94a3b8' }}>
            <FileText size={40} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
            <div style={{ fontSize: '15px', color: '#475569', fontWeight: 500 }}>暂无生效的数据同步任务</div>
            <div style={{ fontSize: '13px', marginTop: '6px' }}>可前往“导入新表”上传 Excel 并创建定时同步</div>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
            <thead>
              <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569' }}>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>任务名称 / ID</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>平台</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>模式与回溯</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>状态</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>上次执行</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>下次预定</th>
                <th style={{ padding: '12px 16px', fontWeight: 600, textAlign: 'right' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '14px 16px' }}>
                    <div style={{ fontWeight: 600, color: '#0f172a' }}>{t.name}</div>
                    <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>ID: #{t.id}</div>
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    <span
                      style={{
                        padding: '3px 8px',
                        borderRadius: '4px',
                        fontSize: '11px',
                        fontWeight: 600,
                        backgroundColor: '#f1f5f9',
                        color: '#334155',
                      }}
                    >
                      {t.platform === 'jzt' ? '京准通' : t.platform === 'taobao' ? '淘宝星河' : '小红书聚光'}
                      {t.sub_account_name ? ` (${t.sub_account_name})` : ''}
                    </span>
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    <div>{t.update_mode === 'overwrite' ? '全量覆写' : '增量更新'}</div>
                    <div style={{ fontSize: '11px', color: '#94a3b8' }}>校准 {t.calibration_days} 天</div>
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    <StatusBadge status={t.status} />
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    <div>{t.last_run_at ? t.last_run_at.substring(0, 16).replace('T', ' ') : '-'}</div>
                    {t.last_status && <StatusBadge status={t.last_status} style={{ marginTop: '4px' }} />}
                  </td>
                  <td style={{ padding: '14px 16px', color: '#64748b' }}>
                    {t.next_run_at ? t.next_run_at.substring(0, 16).replace('T', ' ') : '-'}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                    <div style={{ display: 'inline-flex', gap: '6px' }}>
                      <Button
                        size="sm"
                        variant="secondary"
                        title="立即执行同步"
                        loading={runNowMutation.isPending && runNowMutation.variables === t.id}
                        onClick={() => runNowMutation.mutate(t.id)}
                      >
                        <Play size={13} /> 运行
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        title={t.status === 'active' ? '暂停任务' : '恢复任务'}
                        onClick={() => toggleMutation.mutate(t.id)}
                      >
                        {t.status === 'active' ? <Pause size={13} /> : <Play size={13} />}
                      </Button>
                      {t.spreadsheet_url && (
                        <a
                          href={t.spreadsheet_url}
                          target="_blank"
                          rel="noreferrer"
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            padding: '6px 10px',
                            fontSize: '13px',
                            borderRadius: '6px',
                            backgroundColor: '#f0fdf4',
                            color: '#16a34a',
                            border: '1px solid #bbf7d0',
                            textDecoration: 'none',
                          }}
                        >
                          <ExternalLink size={13} /> 飞书
                        </a>
                      )}
                      <Button
                        size="sm"
                        variant="danger"
                        title="归档删除任务"
                        onClick={() => setDeleteConfirmId(t.id)}
                      >
                        <Trash2 size={13} />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 删除二次确认弹窗 */}
      <Dialog
        isOpen={deleteConfirmId !== null}
        onClose={() => setDeleteConfirmId(null)}
        title="确认删除同步任务"
        width="400px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <p style={{ fontSize: '14px', color: '#475569' }}>
            确定要归档删除该数据同步任务吗？已生成的飞书在线表格不会被删除，但后续定时任务将停止执行。
          </p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <Button variant="secondary" onClick={() => setDeleteConfirmId(null)}>
              取消
            </Button>
            <Button
              variant="danger"
              loading={deleteMutation.isPending}
              onClick={() => deleteConfirmId && deleteMutation.mutate(deleteConfirmId)}
            >
              确认归档删除
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
};

