import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Play, Pause, Trash2, Plus, Minus, ExternalLink, RefreshCw, FileText } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Button } from '@/shared/components/Button';
import { StatusBadge } from '@/shared/components/Badge';
import { Dialog } from '@/shared/components/Dialog';
import { useToast } from '@/shared/components/Toast';

export const KeywordTasksPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();

  const [appendModalTaskId, setAppendModalTaskId] = useState<number | null>(null);
  const [appendWordsInput, setAppendWordsInput] = useState('');
  const [removeModalTaskId, setRemoveModalTaskId] = useState<number | null>(null);
  const [removeWordSelect, setRemoveWordSelect] = useState<string[]>([]);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  const { data: tasks = [], isLoading, refetch } = useQuery<any[]>({
    queryKey: ['keywordTasks'],
    queryFn: () => fetchJson('/api/keyword/tasks'),
  });

  const runNowMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/keyword/tasks/${taskId}/run_now`, { method: 'POST' }),
    onSuccess: (res: any) => {
      showSuccess(res.message || '任务同步成功');
      queryClient.invalidateQueries({ queryKey: ['keywordTasks'] });
      queryClient.invalidateQueries({ queryKey: ['keywordRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '立即同步失败');
    },
  });

  const toggleMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/keyword/tasks/${taskId}/toggle`, { method: 'POST' }),
    onSuccess: (res: any) => {
      showSuccess(`任务状态已切换为: ${res.status === 'active' ? '正常运行' : '已暂停'}`);
      queryClient.invalidateQueries({ queryKey: ['keywordTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '切换状态失败');
    },
  });

  const appendMutation = useMutation({
    mutationFn: ({ taskId, words }: { taskId: number; words: string[] }) =>
      fetchJson(`/api/keyword/tasks/${taskId}/append_keywords`, {
        method: 'POST',
        body: JSON.stringify({ keywords: words, sync_now: true }),
      }),
    onSuccess: () => {
      showSuccess('加词成功并已触发增量同步');
      setAppendModalTaskId(null);
      setAppendWordsInput('');
      queryClient.invalidateQueries({ queryKey: ['keywordTasks'] });
      queryClient.invalidateQueries({ queryKey: ['keywordRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '加词失败');
    },
  });

  const removeMutation = useMutation({
    mutationFn: ({ taskId, words }: { taskId: number; words: string[] }) =>
      fetchJson(`/api/keyword/tasks/${taskId}/remove_keywords`, {
        method: 'POST',
        body: JSON.stringify({ keywords: words }),
      }),
    onSuccess: () => {
      showSuccess('减词成功，历史数据保留且后续不再更新');
      setRemoveModalTaskId(null);
      setRemoveWordSelect([]);
      queryClient.invalidateQueries({ queryKey: ['keywordTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '减词失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/keyword/tasks/${taskId}`, { method: 'DELETE' }),
    onSuccess: () => {
      showSuccess('关键词任务已归档删除');
      setDeleteConfirmId(null);
      queryClient.invalidateQueries({ queryKey: ['keywordTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '删除任务失败');
    },
  });

  const activeTaskForRemove = tasks.find((t) => t.id === removeModalTaskId);

  return (
    <div style={{ maxWidth: '1240px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>关键词监控任务管理</h2>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
            管理聚光关键词每日自动化监控任务、动态加词、减词与飞书表格协同
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
            <div style={{ fontSize: '15px', color: '#475569', fontWeight: 500 }}>暂无生效的关键词监控任务</div>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
            <thead>
              <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569' }}>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>任务名称 / ID</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>词数 / 详情</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>状态</th>
                <th style={{ padding: '12px 16px', fontWeight: 600 }}>更新模式</th>
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
                  <td style={{ padding: '14px 16px', maxWidth: '320px' }}>
                    <div style={{ fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                      有效监控：{t.keywords?.length || 0} 个词
                      {t.removed_keywords?.length > 0 && (
                        <span style={{ fontSize: '11px', color: '#94a3b8', marginLeft: '6px' }}>
                          (已减 {t.removed_keywords.length} 个)
                        </span>
                      )}
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                      {t.keywords?.slice(0, 4).map((kw: string) => (
                        <span
                          key={kw}
                          style={{
                            padding: '2px 6px',
                            borderRadius: '4px',
                            backgroundColor: '#f1f5f9',
                            fontSize: '11px',
                            color: '#475569',
                          }}
                        >
                          {kw}
                        </span>
                      ))}
                      {t.keywords?.length > 4 && (
                        <span style={{ fontSize: '11px', color: '#94a3b8' }}>+{t.keywords.length - 4}...</span>
                      )}
                    </div>
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    <StatusBadge status={t.status} />
                  </td>
                  <td style={{ padding: '14px 16px', color: '#475569' }}>
                    {t.update_mode === 'append' ? '增量追加' : '全量覆写'}
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
                        title="追加新词"
                        onClick={() => {
                          setAppendModalTaskId(t.id);
                          setAppendWordsInput('');
                        }}
                      >
                        <Plus size={13} /> 加词
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        title="减词"
                        onClick={() => {
                          setRemoveModalTaskId(t.id);
                          setRemoveWordSelect([]);
                        }}
                      >
                        <Minus size={13} /> 减词
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

      {/* 加词弹窗 */}
      <Dialog
        isOpen={appendModalTaskId !== null}
        onClose={() => setAppendModalTaskId(null)}
        title="向任务追加关键词"
        width="440px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <p style={{ fontSize: '13px', color: '#64748b' }}>
            新词将立即加入该任务的监控列表，并自动抓取数据填入飞书表格中：
          </p>
          <input
            type="text"
            placeholder="输入新关键词（空格或逗号分隔多词）"
            value={appendWordsInput}
            onChange={(e) => setAppendWordsInput(e.target.value)}
            style={{
              padding: '9px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '14px',
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <Button variant="secondary" onClick={() => setAppendModalTaskId(null)}>
              取消
            </Button>
            <Button
              variant="primary"
              loading={appendMutation.isPending}
              disabled={!appendWordsInput.trim()}
              onClick={() => {
                if (appendModalTaskId) {
                  const words = appendWordsInput.replace(/[,，]/g, ' ').split(/\s+/).filter(Boolean);
                  appendMutation.mutate({ taskId: appendModalTaskId, words });
                }
              }}
            >
              确认加词
            </Button>
          </div>
        </div>
      </Dialog>

      {/* 减词弹窗 */}
      <Dialog
        isOpen={removeModalTaskId !== null}
        onClose={() => setRemoveModalTaskId(null)}
        title="从任务移除关键词"
        width="480px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <p style={{ fontSize: '13px', color: '#64748b' }}>
            被减掉的词将保留表格中的历史数据，但后续不再拉取更新，且不会产生历史日期错位：
          </p>
          <div style={{ maxHeight: '240px', overflowY: 'auto', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {activeTaskForRemove?.keywords?.map((kw: string) => {
              const isSelected = removeWordSelect.includes(kw);
              return (
                <span
                  key={kw}
                  onClick={() => {
                    if (isSelected) setRemoveWordSelect(prev => prev.filter(k => k !== kw));
                    else setRemoveWordSelect(prev => [...prev, kw]);
                  }}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    cursor: 'pointer',
                    border: '1px solid ' + (isSelected ? '#ef4444' : '#cbd5e1'),
                    backgroundColor: isSelected ? '#fef2f2' : '#ffffff',
                    color: isSelected ? '#ef4444' : '#334155',
                  }}
                >
                  {kw}
                </span>
              );
            })}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <Button variant="secondary" onClick={() => setRemoveModalTaskId(null)}>
              取消
            </Button>
            <Button
              variant="danger"
              loading={removeMutation.isPending}
              disabled={removeWordSelect.length === 0}
              onClick={() => {
                if (removeModalTaskId) {
                  removeMutation.mutate({ taskId: removeModalTaskId, words: removeWordSelect });
                }
              }}
            >
              确认减去 ({removeWordSelect.length} 词)
            </Button>
          </div>
        </div>
      </Dialog>

      {/* 删除确认弹窗 */}
      <Dialog
        isOpen={deleteConfirmId !== null}
        onClose={() => setDeleteConfirmId(null)}
        title="确认删除关键词任务"
        width="400px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <p style={{ fontSize: '14px', color: '#475569' }}>
            确定要归档删除该关键词监控任务吗？飞书表格内容将保留，但不再触发后续同步。
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
              确认删除
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
};

