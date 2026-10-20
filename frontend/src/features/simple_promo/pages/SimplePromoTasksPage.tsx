import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Play, Pause, PlayCircle, Edit2, Trash2, Clock, Users, Calendar, ExternalLink } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { useToast } from '@/shared/components/Toast';
import { TaskStatusBadge } from '@/shared/components/TaskStatusBadge';
import { formatRruleText } from '@/shared/utils/formatRrule';
import { Dialog } from '@/shared/components/Dialog';
import { CreateOrEditSimplePromoTaskDialog } from '../components/CreateOrEditSimplePromoTaskDialog';

export const SimplePromoTasksPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<any | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  const getAuthHeaders = (): Record<string, string> => {
    const token = sessionStorage.getItem('simple_promo_token') || '';
    return { 'x-simple-promo-token': token };
  };

  // 获取全部任务
  const { data: tasks = [], isLoading, refetch } = useQuery<any[]>({
    queryKey: ['simplePromoTasks'],
    queryFn: () => fetchJson('/api/simple-promo/tasks'),
  });

  // 获取子账号数据以供编辑使用
  const { data: subaccounts = [] } = useQuery<any[]>({
    queryKey: ['simplePromoSubaccounts'],
    queryFn: async () => {
      const data = await fetchJson<any[]>('/api/simple-promo/subaccounts');
      if (Array.isArray(data) && data.length > 0) {
        try {
          localStorage.setItem('sp_cached_subaccounts', JSON.stringify(data));
        } catch (_) {}
      }
      return data;
    },
    initialData: () => {
      try {
        const raw = localStorage.getItem('sp_cached_subaccounts');
        if (raw) return JSON.parse(raw);
      } catch (_) {}
      return undefined;
    },
    staleTime: 10 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
  });

  const { data: feishuSheet } = useQuery<any>({
    queryKey: ['simplePromoFeishuSheet'],
    queryFn: () => fetchJson('/api/simple-promo/feishu-sheet'),
  });

  // 立即执行 Mutation
  const runNowMutation = useMutation({
    mutationFn: (id: number) =>
      fetchJson(`/api/simple-promo/tasks/${id}/run_now`, {
        method: 'POST',
        headers: getAuthHeaders(),
      }),
    onSuccess: (res: any) => {
      showSuccess(res.message || '定时任务立即执行成功');
      queryClient.invalidateQueries({ queryKey: ['simplePromoTasks'] });
      queryClient.invalidateQueries({ queryKey: ['simplePromoRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '立即执行失败');
    },
  });

  // 切换启停 Mutation
  const toggleMutation = useMutation({
    mutationFn: (id: number) =>
      fetchJson(`/api/simple-promo/tasks/${id}/toggle`, {
        method: 'POST',
        headers: getAuthHeaders(),
      }),
    onSuccess: (res: any) => {
      showSuccess(`任务已切换为: ${res.status === 'active' ? '正常启用' : '已暂停'}`);
      queryClient.invalidateQueries({ queryKey: ['simplePromoTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '切换任务状态失败');
    },
  });

  // 删除 Mutation
  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      fetchJson(`/api/simple-promo/tasks/${id}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      }),
    onSuccess: () => {
      showSuccess('任务已删除');
      setDeleteConfirmId(null);
      queryClient.invalidateQueries({ queryKey: ['simplePromoTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '删除失败');
    },
  });

  const handleEdit = (task: any) => {
    setEditingTask(task);
    setDialogOpen(true);
  };

  const handleCreate = () => {
    setEditingTask(null);
    setDialogOpen(true);
  };

  return (
    <div className="card">
      <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span style={{ fontSize: '16px', fontWeight: 600 }}>简单投老笔记巡检任务列表</span>
          <span style={{ fontSize: '13px', color: '#64748b', fontWeight: 400, marginLeft: '10px' }}>
            自动每日巡检排查，防止老笔记被简单投系统误开启偷跑
          </span>
        </div>
      </div>

      <div className="table-container" style={{ marginTop: '16px' }}>
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>加载定时任务列表中...</div>
        ) : tasks.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '50px', color: '#94a3b8' }}>
            暂无简单投定时巡检任务，点击右上角【新建定时巡检任务】进行添加
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #e2e8f0', textAlign: 'left', color: '#64748b' }}>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>任务名称</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>目标子账号</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>飞书在线表格</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>老笔记截止点</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>定时规则</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>下次运行时间</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>最近运行</th>
                <th style={{ padding: '10px 14px', fontWeight: 600, textAlign: 'right' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => {
                const accounts = t.accounts || [];
                return (
                  <tr
                    key={t.id}
                    style={{ borderBottom: '1px solid #f1f5f9', transition: 'background-color 0.1s ease' }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f8fafc')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <td style={{ padding: '12px 14px', color: '#0f172a', minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
                        <strong
                          title={t.name}
                          style={{
                            flex: '1 1 auto',
                            minWidth: 0,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {t.name}
                        </strong>
                        {t.status === 'paused' && (
                          <span
                            style={{
                              fontSize: '11px',
                              padding: '1px 6px',
                              borderRadius: '3px',
                              backgroundColor: '#f1f5f9',
                              color: '#64748b',
                              flexShrink: 0,
                            }}
                          >
                            已暂停
                          </span>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: '12px 14px', maxWidth: '280px' }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                        {accounts.slice(0, 3).map((acc: any) => (
                          <span
                            key={acc.id}
                            style={{
                              fontSize: '11px',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              backgroundColor: '#f8fafc',
                              border: '1px solid #e2e8f0',
                              color: '#334155',
                            }}
                          >
                            {acc.name}
                          </span>
                        ))}
                        {accounts.length > 3 && (
                          <span
                            style={{
                              fontSize: '11px',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              backgroundColor: '#f1f5f9',
                              color: '#64748b',
                            }}
                          >
                            +{accounts.length - 3} 个账号
                          </span>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: '12px 14px' }}>
                      <a
                        href={feishuSheet?.spreadsheet_url || 'https://yimeichuanbo.feishu.cn/sheets/USKTstt6Zhja42ttnvrckJXcnQf'}
                        target="_blank"
                        rel="noreferrer"
                        style={{
                          color: 'var(--primary)',
                          fontWeight: 500,
                          textDecoration: 'none',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        查看监控表格 ↗
                      </a>
                    </td>
                    <td style={{ padding: '12px 14px', color: '#64748b', whiteSpace: 'nowrap' }}>
                      {t.cutoff_date}
                    </td>
                    <td style={{ padding: '12px 14px', color: '#1e293b' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Clock size={14} color="#64748b" />
                        <span>{formatRruleText(t.rrule)}</span>
                      </div>
                    </td>
                    <td style={{ padding: '12px 14px', color: '#64748b', whiteSpace: 'nowrap' }}>
                      {t.next_run_at ? t.next_run_at.replace('T', ' ').slice(0, 19) : '-'}
                    </td>
                    <td style={{ padding: '12px 14px' }}>
                      {t.last_status ? (
                        <div>
                          <TaskStatusBadge status={t.last_status} />
                          <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
                            {t.last_run_at ? t.last_run_at.replace('T', ' ').slice(0, 19) : ''}
                          </div>
                        </div>
                      ) : (
                        <span style={{ color: '#94a3b8' }}>尚未执行</span>
                      )}
                    </td>
                    <td style={{ padding: '12px 14px', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                        <button
                          type="button"
                          className="btn btn-outline btn-sm"
                          disabled={runNowMutation.isPending && runNowMutation.variables === t.id}
                          onClick={() => runNowMutation.mutate(t.id)}
                        >
                          立即执行
                        </button>
                        <button
                          type="button"
                          className={`btn btn-sm ${t.status === 'active' ? 'btn-outline' : 'btn-resume'}`}
                          onClick={() => toggleMutation.mutate(t.id)}
                        >
                          {t.status === 'active' ? '暂停' : '恢复'}
                        </button>
                        <button
                          type="button"
                          className="btn btn-outline btn-sm"
                          onClick={() => handleEdit(t)}
                        >
                          编辑
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger-outline btn-sm"
                          onClick={() => setDeleteConfirmId(t.id)}
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* 删除二次确认弹窗 */}
      <Dialog
        isOpen={Boolean(deleteConfirmId)}
        onClose={() => setDeleteConfirmId(null)}
        title="确认删除该定时任务"
        width="400px"
      >
        <p style={{ fontSize: '14px', color: '#64748b', marginBottom: '20px' }}>
          确定要删除此定时巡检任务吗？删除后将不再自动执行老笔记巡检，历史运行记录不受影响。
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button
            type="button"
            onClick={() => setDeleteConfirmId(null)}
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#fff',
              cursor: 'pointer',
            }}
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => deleteConfirmId && deleteMutation.mutate(deleteConfirmId)}
            style={{
              padding: '6px 16px',
              borderRadius: '6px',
              backgroundColor: '#ef4444',
              color: '#fff',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            确认删除
          </button>
        </div>
      </Dialog>

      {/* 新建/编辑任务弹窗 */}
      <CreateOrEditSimplePromoTaskDialog
        isOpen={dialogOpen}
        onClose={() => setDialogOpen(false)}
        task={editingTask}
        onSuccess={() => {
          refetch();
          queryClient.invalidateQueries({ queryKey: ['simplePromoTasks'] });
        }}
        subaccounts={subaccounts}
      />
    </div>
  );
};
