import React, { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { X, Download, Copy, Check, ExternalLink, Search, Filter, CheckCircle2, AlertCircle, Clock, ShieldCheck, RotateCcw } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { TaskStatusBadge } from '@/shared/components/TaskStatusBadge';
import { useToast } from '@/shared/components/Toast';
import { Dialog } from '@/shared/components/Dialog';

export interface SimplePromoDetailDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  runId: number | null;
}

export const SimplePromoDetailDrawer: React.FC<SimplePromoDetailDrawerProps> = ({
  isOpen,
  onClose,
  runId,
}) => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();
  const [searchKw, setSearchKw] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'paused' | 'already' | 'whitelist' | 'error'>('all');
  const [copied, setCopied] = useState(false);
  const [confirmRollback, setConfirmRollback] = useState(false);
  const [rollbackLoading, setRollbackLoading] = useState(false);

  const { data: runDetail, isLoading, refetch: refetchDetail } = useQuery<any>({
    queryKey: ['simplePromoRunDetail', runId],
    queryFn: () => fetchJson(`/api/simple-promo/runs/${runId}`),
    enabled: isOpen && Boolean(runId),
  });

  // 获取飞书表格地址
  const { data: feishuSheet } = useQuery<any>({
    queryKey: ['simplePromoFeishuSheet'],
    queryFn: () => fetchJson('/api/simple-promo/feishu-sheet'),
  });

  const items = runDetail?.items || [];

  const filteredItems = useMemo(() => {
    const kw = searchKw.trim().toLowerCase();
    return items.filter((item: any) => {
      if (statusFilter === 'paused' && item.result_status !== '已暂停' && item.action !== '待暂停') return false;
      if (statusFilter === 'already' && item.result_status !== '无需操作') return false;
      if (statusFilter === 'whitelist' && item.result_status !== '跳过') return false;
      if (statusFilter === 'error' && item.result_status !== '失败' && !item.error_message) return false;

      if (!kw) return true;
      return (
        (item.note_title && item.note_title.toLowerCase().includes(kw)) ||
        (item.note_id && item.note_id.toLowerCase().includes(kw)) ||
        (item.account_name && item.account_name.toLowerCase().includes(kw)) ||
        (item.creativity_id && item.creativity_id.toLowerCase().includes(kw))
      );
    });
  }, [items, searchKw, statusFilter]);

  if (!isOpen || !runId) return null;

  const handleExportCsv = () => {
    window.open(`/api/simple-promo/runs/${runId}/export`, '_blank');
  };

  const handleExecuteRollback = async () => {
    if (!runId) return;
    setRollbackLoading(true);
    try {
      const res: any = await fetchJson(`/api/simple-promo/runs/${runId}/rollback`, {
        method: 'POST',
        headers: {
          'x-simple-promo-token': sessionStorage.getItem('simple_promo_token') || '',
        },
        body: JSON.stringify({ confirm: true }),
      });
      showSuccess(res.message || '已成功将笔记全部恢复为【开启投放】！');
      setConfirmRollback(false);
      refetchDetail();
      queryClient.invalidateQueries({ queryKey: ['simplePromoRuns'] });
    } catch (err: any) {
      showError(err.message || '恢复投放失败');
    } finally {
      setRollbackLoading(false);
    }
  };

  const handleCopyTable = async () => {
    if (!filteredItems || filteredItems.length === 0) {
      showError('暂无数据可复制');
      return;
    }
    const headers = ['子账号', '笔记标题', '笔记ID', '发布时间', '原投放状态', '操作动作', '处理状态'];
    const rows = filteredItems.map((item: any) => [
      item.account_name || '',
      item.note_title || '',
      item.note_id || '',
      item.note_publish_time || '',
      item.original_status || '',
      item.action || '',
      item.result_status || ''
    ]);
    const tsv = [headers.join('\t'), ...rows.map((r: string[]) => r.join('\t'))].join('\n');
    try {
      await navigator.clipboard.writeText(tsv);
      setCopied(true);
      showSuccess('📋 表格内容已复制到剪贴板，可直接在 Excel 中粘贴 (Ctrl+V)！');
      setTimeout(() => setCopied(false), 2000);
    } catch (err: any) {
      showError('复制失败: ' + err.message);
    }
  };

  const displayCutoff = (runDetail?.cutoff_date || '2026-01-01').split(' ')[0];

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(15, 23, 42, 0.45)',
        backdropFilter: 'blur(2px)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          width: '1060px',
          maxWidth: '96vw',
          height: '88vh',
          backgroundColor: '#ffffff',
          borderRadius: '12px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          animation: 'modalIn 0.15s ease-out',
        }}
      >
        {/* 头部标题与操作 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px 24px',
            borderBottom: '1px solid #e2e8f0',
            backgroundColor: '#ffffff',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <h3 style={{ fontSize: '17px', fontWeight: 600, color: '#0f172a' }}>
              运行明细核对 (Run #{runId})
            </h3>
            {runDetail?.status && <TaskStatusBadge status={runDetail.status} />}
            <span
              style={{
                fontSize: '12px',
                padding: '2px 8px',
                borderRadius: '4px',
                backgroundColor: runDetail?.mode === 'EXECUTE' ? '#fee2e2' : '#f1f5f9',
                color: runDetail?.mode === 'EXECUTE' ? '#dc2626' : '#475569',
                fontWeight: 500,
              }}
            >
              {runDetail?.mode === 'EXECUTE' ? '线上实际执行' : '仅巡检预览'}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {feishuSheet?.spreadsheet_url && (
              <a
                href={feishuSheet.spreadsheet_url}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 14px',
                  borderRadius: '6px',
                  border: '1px solid #a7f3d0',
                  backgroundColor: '#ecfdf5',
                  color: '#059669',
                  fontSize: '13px',
                  fontWeight: 500,
                  textDecoration: 'none',
                }}
              >
                <ExternalLink size={14} />
                飞书表格 ↗
              </a>
            )}
            {runDetail?.mode === 'EXECUTE' && runDetail?.paused_success_count > 0 && (
              <button
                type="button"
                onClick={() => setConfirmRollback(true)}
                disabled={rollbackLoading}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 14px',
                  borderRadius: '6px',
                  border: '1px solid #93c5fd',
                  backgroundColor: '#eff6ff',
                  color: '#2563eb',
                  fontSize: '13px',
                  fontWeight: 500,
                  cursor: 'pointer',
                }}
              >
                <RotateCcw size={14} />
                <span>{rollbackLoading ? '正在恢复...' : '一键恢复投放'}</span>
              </button>
            )}
            <button
              type="button"
              onClick={handleCopyTable}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 14px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                color: '#334155',
                fontSize: '13px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              {copied ? <Check size={14} color="#059669" /> : <Copy size={14} />}
              {copied ? '已复制' : '复制表格数据'}
            </button>
            <button
              type="button"
              onClick={handleExportCsv}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 14px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                color: '#334155',
                fontSize: '13px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              <Download size={15} />
              导出 Excel/CSV
            </button>
            <button
              type="button"
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: '#94a3b8',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* 概览统计条 */}
        {runDetail && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '20px',
              padding: '12px 24px',
              backgroundColor: '#f8fafc',
              borderBottom: '1px solid #e2e8f0',
              fontSize: '13px',
              flexWrap: 'wrap',
            }}
          >
            <div>
              <span style={{ color: '#64748b' }}>任务名称：</span>
              <strong style={{ color: '#1e293b' }}>{runDetail.task_name}</strong>
            </div>
            <div>
              <span style={{ color: '#64748b' }}>开始时间：</span>
              <span style={{ color: '#1e293b' }}>{runDetail.started_at}</span>
            </div>
            <div>
              <span style={{ color: '#64748b' }}>耗时：</span>
              <span style={{ color: '#1e293b' }}>
                {runDetail.duration_ms ? `${(runDetail.duration_ms / 1000).toFixed(1)} 秒` : '-'}
              </span>
            </div>
            <div>
              <span style={{ color: '#64748b' }}>截止时间：</span>
              <span style={{ color: '#1e293b' }}>{runDetail.cutoff_date}</span>
            </div>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: '14px' }}>
              <span>
                扫描笔记: <strong>{runDetail.total_notes_scanned}</strong>
              </span>
              <span>
                老笔记 ({displayCutoff}前): <strong style={{ color: '#f59e0b' }}>{runDetail.pre_cutoff_notes_count}</strong>
              </span>
              <span>
                本次暂停: <strong style={{ color: '#dc2626' }}>{runDetail.paused_success_count || runDetail.to_pause_count}</strong>
              </span>
              <span>
                原已暂停: <strong style={{ color: '#10b981' }}>{runDetail.already_paused_count}</strong>
              </span>
            </div>
          </div>
        )}

        {/* 筛选与搜索工具条 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 24px',
            borderBottom: '1px solid #e2e8f0',
            backgroundColor: '#ffffff',
          }}
        >
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              type="button"
              onClick={() => setStatusFilter('all')}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
                border: '1px solid',
                borderColor: statusFilter === 'all' ? 'var(--primary)' : '#e2e8f0',
                backgroundColor: statusFilter === 'all' ? 'var(--primary-light)' : '#ffffff',
                color: statusFilter === 'all' ? 'var(--primary)' : '#475569',
              }}
            >
              全部老笔记 ({items.length})
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter('paused')}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
                border: '1px solid',
                borderColor: statusFilter === 'paused' ? '#dc2626' : '#e2e8f0',
                backgroundColor: statusFilter === 'paused' ? '#fef2f2' : '#ffffff',
                color: statusFilter === 'paused' ? '#dc2626' : '#475569',
              }}
            >
              本次暂停 / 待暂停
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter('already')}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
                border: '1px solid',
                borderColor: statusFilter === 'already' ? '#059669' : '#e2e8f0',
                backgroundColor: statusFilter === 'already' ? '#ecfdf5' : '#ffffff',
                color: statusFilter === 'already' ? '#059669' : '#475569',
              }}
            >
              原已暂停
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter('whitelist')}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
                border: '1px solid',
                borderColor: statusFilter === 'whitelist' ? '#2563eb' : '#e2e8f0',
                backgroundColor: statusFilter === 'whitelist' ? '#eff6ff' : '#ffffff',
                color: statusFilter === 'whitelist' ? '#2563eb' : '#475569',
              }}
            >
              白名单保护
            </button>
          </div>

          <div style={{ position: 'relative', width: '260px' }}>
            <input
              type="text"
              value={searchKw}
              onChange={(e) => setSearchKw(e.target.value)}
              placeholder="搜索标题 / 笔记ID / 子账号..."
              style={{
                width: '100%',
                padding: '6px 10px 6px 28px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '12px',
                outline: 'none',
              }}
            />
            <Search
              size={14}
              style={{
                position: 'absolute',
                left: '8px',
                top: '50%',
                transform: 'translateY(-50%)',
                color: '#94a3b8',
              }}
            />
          </div>
        </div>

        {/* 数据明细表格 */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {isLoading ? (
            <div style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>正在加载记录明细...</div>
          ) : filteredItems.length === 0 ? (
            <div style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>未找到匹配的笔记明细</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead style={{ position: 'sticky', top: 0, backgroundColor: '#f8fafc', zIndex: 10 }}>
                <tr style={{ borderBottom: '1px solid #e2e8f0', textAlign: 'left', color: '#64748b' }}>
                  <th style={{ padding: '10px 16px', fontWeight: 600 }}>子账号</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600 }}>笔记标题</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600 }}>笔记ID / 链接</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600 }}>发布时间</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600 }}>原投放状态</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600 }}>操作动作</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600 }}>处理状态</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((item: any) => (
                  <tr
                    key={item.id}
                    style={{
                      borderBottom: '1px solid #f1f5f9',
                      transition: 'background-color 0.1s ease',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f8fafc')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <td style={{ padding: '10px 16px', color: '#1e293b' }}>
                      <strong>{item.account_name}</strong>
                    </td>
                    <td style={{ padding: '10px 16px', maxWidth: '320px', color: '#334155' }}>
                      <div
                        style={{
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={item.note_title}
                      >
                        {item.note_title || '（无标题）'}
                      </div>
                    </td>
                    <td style={{ padding: '10px 16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ fontFamily: 'monospace', color: '#64748b', fontSize: '12px' }}>
                          {item.note_id}
                        </span>
                        {item.note_url && (
                          <a
                            href={item.note_url}
                            target="_blank"
                            rel="noreferrer"
                            title="在小红书打开笔记"
                            style={{ color: 'var(--primary)', display: 'inline-flex', alignItems: 'center' }}
                          >
                            <ExternalLink size={13} />
                          </a>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: '10px 16px', color: '#64748b', whiteSpace: 'nowrap' }}>
                      {item.note_publish_time}
                    </td>
                    <td style={{ padding: '10px 16px' }}>
                      <span
                        style={{
                          fontSize: '11px',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          backgroundColor: item.original_status === '有效投放' ? '#ecfdf5' : '#f1f5f9',
                          color: item.original_status === '有效投放' ? '#059669' : '#64748b',
                        }}
                      >
                        {item.original_status}
                      </span>
                    </td>
                    <td style={{ padding: '10px 16px', color: '#334155' }}>
                      {item.action}
                    </td>
                    <td style={{ padding: '10px 16px' }}>
                      {item.result_status === '已暂停' ? (
                        <span
                          style={{
                            fontSize: '11px',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            backgroundColor: '#fee2e2',
                            color: '#dc2626',
                            fontWeight: 500,
                          }}
                        >
                          ● 已暂停
                        </span>
                      ) : item.result_status === '无需操作' ? (
                        <span
                          style={{
                            fontSize: '11px',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            backgroundColor: '#f1f5f9',
                            color: '#64748b',
                          }}
                        >
                          保持暂停
                        </span>
                      ) : item.result_status === '跳过' ? (
                        <span
                          style={{
                            fontSize: '11px',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            backgroundColor: '#eff6ff',
                            color: '#2563eb',
                          }}
                        >
                          白名单跳过
                        </span>
                      ) : (
                        <span style={{ fontSize: '11px', color: '#64748b' }}>{item.result_status}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* 确认一键恢复弹窗 */}
      <Dialog
        isOpen={confirmRollback}
        onClose={() => setConfirmRollback(false)}
        title="确认一键恢复开启投放"
        width="460px"
      >
        <div style={{ display: 'flex', gap: '14px', marginBottom: '16px' }}>
          <div style={{ color: '#2563eb' }}>
            <RotateCcw size={28} />
          </div>
          <div>
            <h4 style={{ fontSize: '15px', fontWeight: 600, color: '#1e293b', marginBottom: '4px' }}>
              恢复 Run #{runId} 暂停的老笔记
            </h4>
            <p style={{ fontSize: '13px', color: '#64748b', lineHeight: 1.5 }}>
              确定向小红书聚光下发指令，将本批次成功暂停的 <strong>{runDetail?.paused_success_count}</strong> 篇老笔记全部原样恢复为【开启投放】状态吗？
            </p>
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button
            type="button"
            onClick={() => setConfirmRollback(false)}
            style={{ padding: '6px 14px', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#fff', cursor: 'pointer' }}
          >
            取消
          </button>
          <button
            type="button"
            disabled={rollbackLoading}
            onClick={handleExecuteRollback}
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
            {rollbackLoading ? '正在恢复中...' : '立即确认恢复'}
          </button>
        </div>
      </Dialog>
    </div>
  );
};
