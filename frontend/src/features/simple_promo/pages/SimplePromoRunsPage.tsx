import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Download, Eye, RefreshCw, FileText, CheckCircle2, AlertCircle, RotateCcw, ExternalLink } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { useToast } from '@/shared/components/Toast';
import { TaskStatusBadge } from '@/shared/components/TaskStatusBadge';
import { Dialog } from '@/shared/components/Dialog';
import { SimplePromoDetailDrawer } from '../components/SimplePromoDetailDrawer';

export const SimplePromoRunsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [rollbackTargetRun, setRollbackTargetRun] = useState<any | null>(null);

  const { data: runs = [], isLoading, refetch } = useQuery<any[]>({
    queryKey: ['simplePromoRuns'],
    queryFn: () => fetchJson('/api/simple-promo/runs'),
  });

  // 获取飞书表格地址
  const { data: feishuSheet } = useQuery<any>({
    queryKey: ['simplePromoFeishuSheet'],
    queryFn: () => fetchJson('/api/simple-promo/feishu-sheet'),
  });

  // 一键恢复投放 Mutation
  const rollbackMutation = useMutation({
    mutationFn: (runId: number) =>
      fetchJson(`/api/simple-promo/runs/${runId}/rollback`, {
        method: 'POST',
        headers: {
          'x-simple-promo-token': sessionStorage.getItem('simple_promo_token') || '',
        },
        body: JSON.stringify({ confirm: true }),
      }),
    onSuccess: (res: any) => {
      showSuccess(res.message || '已成功将该批次笔记原样恢复为【开启投放】！');
      setRollbackTargetRun(null);
      queryClient.invalidateQueries({ queryKey: ['simplePromoRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '恢复投放失败');
    },
  });

  const handleViewDetail = (runId: number) => {
    setSelectedRunId(runId);
    setDrawerOpen(true);
  };

  const handleExport = (runId: number) => {
    window.open(`/api/simple-promo/runs/${runId}/export`, '_blank');
  };

  return (
    <div className="card">
      <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span style={{ fontSize: '16px', fontWeight: 600 }}>简单投老笔记暂停运行记录</span>
          <span style={{ fontSize: '13px', color: '#64748b', fontWeight: 400, marginLeft: '10px' }}>
            记录每次巡检与暂停操作的完整变更明细，支持一键下载导出核对表格
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <button
          type="button"
          className="btn btn-outline btn-sm"
          onClick={() => refetch()}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 12px',
            borderRadius: '6px',
            border: '1px solid #cbd5e1',
            backgroundColor: '#fff',
            cursor: 'pointer',
            fontSize: '13px',
          }}
        >
          <RefreshCw size={14} />
          刷新记录
        </button>
        </div>
      </div>

      <div className="table-container" style={{ marginTop: '16px' }}>
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>加载运行日志中...</div>
        ) : runs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '50px', color: '#94a3b8' }}>暂无简单投运行记录</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #e2e8f0', textAlign: 'left', color: '#64748b' }}>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>ID</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>任务 / 操作名称</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>模式</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>触发方式</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>账号数</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>扫描笔记</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>老笔记 / 本次暂停</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>耗时</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>状态</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>完成时间</th>
                <th style={{ padding: '10px 14px', fontWeight: 600, textAlign: 'right' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr
                  key={r.id}
                  style={{ borderBottom: '1px solid #f1f5f9', transition: 'background-color 0.1s ease' }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f8fafc')}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                >
                  <td style={{ padding: '12px 14px', color: '#64748b', fontFamily: 'monospace' }}>
                    #{r.id}
                  </td>
                  <td style={{ padding: '12px 14px', color: '#0f172a' }}>
                    <strong>{r.task_name}</strong>
                  </td>
                  <td style={{ padding: '12px 14px' }}>
                    <span
                      style={{
                        fontSize: '11px',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        backgroundColor: r.mode === 'EXECUTE' ? '#fee2e2' : '#f1f5f9',
                        color: r.mode === 'EXECUTE' ? '#dc2626' : '#475569',
                        fontWeight: 500,
                      }}
                    >
                      {r.mode === 'EXECUTE' ? '实际执行' : '仅巡检'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 14px', color: '#64748b' }}>
                    {r.trigger_type === 'scheduled' ? '定时任务' : r.trigger_type === 'workbench' ? '工作台' : '手动执行'}
                  </td>
                  <td style={{ padding: '12px 14px', color: '#1e293b' }}>
                    {r.accounts_count} 个
                  </td>
                  <td style={{ padding: '12px 14px', color: '#1e293b' }}>
                    {r.total_notes_scanned} 篇
                  </td>
                  <td style={{ padding: '12px 14px' }}>
                    <span style={{ color: '#d97706', fontWeight: 600 }}>{r.pre_cutoff_notes_count} 篇</span>
                    <span style={{ color: '#94a3b8', margin: '0 4px' }}>/</span>
                    <span style={{ color: '#dc2626', fontWeight: 600 }}>
                      {r.mode === 'EXECUTE' ? `${r.paused_success_count} 暂停` : `${r.to_pause_count} 待停`}
                    </span>
                  </td>
                  <td style={{ padding: '12px 14px', color: '#64748b' }}>
                    {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : '-'}
                  </td>
                  <td style={{ padding: '12px 14px' }}>
                    <TaskStatusBadge status={r.status} />
                  </td>
                  <td style={{ padding: '12px 14px', color: '#64748b', whiteSpace: 'nowrap' }}>
                    {r.finished_at || r.started_at}
                  </td>
                  <td style={{ padding: '12px 14px', textAlign: 'right' }}>
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                      {r.mode === 'EXECUTE' && r.paused_success_count > 0 && (
                        <button
                          type="button"
                          className="btn btn-outline btn-sm"
                          onClick={() => setRollbackTargetRun(r)}
                          title="一键将该批次被暂停的老笔记恢复为开启投放"
                          style={{
                            padding: '4px 8px',
                            borderRadius: '4px',
                            fontSize: '12px',
                            border: '1px solid #93c5fd',
                            backgroundColor: '#eff6ff',
                            color: '#2563eb',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '3px',
                          }}
                        >
                          <RotateCcw size={12} />
                          恢复
                        </button>
                      )}
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        onClick={() => handleViewDetail(r.id)}
                        style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          fontSize: '12px',
                          border: '1px solid #cbd5e1',
                          backgroundColor: '#fff',
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        <Eye size={13} />
                        明细
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        onClick={() => handleExport(r.id)}
                        style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          fontSize: '12px',
                          border: '1px solid #cbd5e1',
                          backgroundColor: '#fff',
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          color: '#334155',
                        }}
                      >
                        <Download size={13} />
                        导出
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 明细弹窗抽屉 */}
      <SimplePromoDetailDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        runId={selectedRunId}
      />

      {/* 一键恢复确认弹窗 */}
      <Dialog
        isOpen={Boolean(rollbackTargetRun)}
        onClose={() => setRollbackTargetRun(null)}
        title="确认一键恢复开启投放"
        width="460px"
      >
        <div style={{ display: 'flex', gap: '14px', marginBottom: '16px' }}>
          <div style={{ color: '#2563eb' }}>
            <RotateCcw size={28} />
          </div>
          <div>
            <h4 style={{ fontSize: '15px', fontWeight: 600, color: '#1e293b', marginBottom: '4px' }}>
              恢复 Run #{rollbackTargetRun?.id} 暂停的笔记
            </h4>
            <p style={{ fontSize: '13px', color: '#64748b', lineHeight: 1.5 }}>
              确定向小红书聚光下发指令，将该批次成功暂停的 <strong>{rollbackTargetRun?.paused_success_count}</strong> 篇老笔记全部原样恢复为【开启投放】状态吗？
            </p>
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button
            type="button"
            onClick={() => setRollbackTargetRun(null)}
            style={{ padding: '6px 14px', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#fff', cursor: 'pointer' }}
          >
            取消
          </button>
          <button
            type="button"
            disabled={rollbackMutation.isPending}
            onClick={() => rollbackTargetRun && rollbackMutation.mutate(rollbackTargetRun.id)}
            style={{
              padding: '6px 18px',
              borderRadius: '6px',
              backgroundColor: '#2563eb',
              color: '#fff',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            {rollbackMutation.isPending ? '正在恢复中...' : '立即确认恢复'}
          </button>
        </div>
      </Dialog>
    </div>
  );
};
