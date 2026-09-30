import React, { useState } from 'react';
import { Clock } from 'lucide-react';
import { formatRruleText } from '@/shared/utils/formatRrule';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchJson } from '@/shared/api/client';
import { Dialog } from '@/shared/components/Dialog';
import { useToast } from '@/shared/components/Toast';

export const LingxiTasksPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();

  const [appendModalTaskId, setAppendModalTaskId] = useState<number | null>(null);
  const [appendWordsInput, setAppendWordsInput] = useState('');
  const [removeModalTaskId, setRemoveModalTaskId] = useState<number | null>(null);
  const [removeWordSelect, setRemoveWordSelect] = useState<string[]>([]);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);

  const { data: tasks = [], isLoading, refetch } = useQuery<any[]>({
    queryKey: ['lingxiTasks'],
    queryFn: () => fetchJson('/api/lingxi/tasks'),
  });

  const runNowMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/lingxi/tasks/${taskId}/run_now`, { method: 'POST' }),
    onSuccess: (res: any) => {
      showSuccess(res.message || '任务同步成功');
      queryClient.invalidateQueries({ queryKey: ['lingxiTasks'] });
      queryClient.invalidateQueries({ queryKey: ['lingxiRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '立即同步失败');
    },
  });

  const toggleMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/lingxi/tasks/${taskId}/toggle`, { method: 'POST' }),
    onSuccess: (res: any) => {
      showSuccess(`任务状态已切换为: ${res.status === 'active' ? '正常运行' : '已暂停'}`);
      queryClient.invalidateQueries({ queryKey: ['lingxiTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '切换状态失败');
    },
  });

  const appendMutation = useMutation({
    mutationFn: ({ taskId, words }: { taskId: number; words: string[] }) =>
      fetchJson(`/api/lingxi/tasks/${taskId}/append_keywords`, {
        method: 'POST',
        body: JSON.stringify({ keywords: words, sync_now: true }),
      }),
    onSuccess: () => {
      showSuccess('加词成功并已触发增量同步');
      setAppendModalTaskId(null);
      setAppendWordsInput('');
      queryClient.invalidateQueries({ queryKey: ['lingxiTasks'] });
      queryClient.invalidateQueries({ queryKey: ['lingxiRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '加词失败');
    },
  });

  const removeMutation = useMutation({
    mutationFn: ({ taskId, words }: { taskId: number; words: string[] }) =>
      fetchJson(`/api/lingxi/tasks/${taskId}/remove_keywords`, {
        method: 'POST',
        body: JSON.stringify({ keywords: words }),
      }),
    onSuccess: () => {
      showSuccess('减词成功，历史数据保留且后续不再更新');
      setRemoveModalTaskId(null);
      setRemoveWordSelect([]);
      queryClient.invalidateQueries({ queryKey: ['lingxiTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '减词失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/lingxi/tasks/${taskId}`, { method: 'DELETE' }),
    onSuccess: () => {
      showSuccess('关键词任务已归档删除');
      setDeleteConfirmId(null);
      queryClient.invalidateQueries({ queryKey: ['lingxiTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '删除任务失败');
    },
  });

  const activeTaskForRemove = tasks.find((t) => t.id === removeModalTaskId);

  return (
    <div className="card">
      <div className="card-title">
        <span>现有灵犀关键词监控任务</span>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => refetch()}>
          🔄 刷新列表
        </button>
      </div>

      <div className="table-container">
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>加载任务中...</div>
        ) : tasks.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>暂无灵犀关键词监控任务</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>任务名称</th>
                <th>关键词详情</th>
                <th>状态</th>
                <th>对应飞书表格</th>
                <th>模式</th>
                <th>调度频率</th>
                <th>上次执行</th>
                <th style={{ textAlign: 'center' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id}>
                  <td>
                    <strong>{t.name}</strong>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>ID: #{t.id}</div>
                  </td>
                  <td style={{ maxWidth: '280px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>
                      有效监控: {t.keywords?.length || 0} 个词
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '2px' }}>
                      {t.keywords?.slice(0, 4).map((kw: string) => (
                        <span key={kw} className="badge badge-gray" style={{ fontSize: '11px' }}>
                          {kw}
                        </span>
                      ))}
                      {t.keywords?.length > 4 && (
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>+{t.keywords.length - 4}...</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <span className={`badge ${t.status === 'active' ? 'badge-success' : 'badge-gray'}`}>
                      {t.status === 'active' ? '正常运行' : '已暂停'}
                    </span>
                  </td>
                  <td>
                    {t.spreadsheet_url ? (
                      <a
                        href={t.spreadsheet_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: 'var(--primary)', fontWeight: 500, textDecoration: 'none' }}
                      >
                        查看飞书表格 ↗
                      </a>
                    ) : '-'}
                  </td>
                  <td>{t.update_mode === 'append' ? '增量追加' : '全量覆写'}</td>
                  <td>
                    <span className="freq-tag" title={t.rrule}>
                      <Clock size={12} className="icon" style={{ opacity: 0.7 }} />
                      <span>{formatRruleText(t.rrule)}</span>
                    </span>
                  </td>
                  <td>
                    <div>{t.last_run_at ? t.last_run_at.substring(0, 16).replace('T', ' ') : '-'}</div>
                    {t.last_status && (
                      <span className={`badge ${t.last_status === 'success' ? 'badge-success' : 'badge-danger'}`} style={{ marginTop: '2px' }}>
                        {t.last_status === 'success' ? '成功' : '失败'}
                      </span>
                    )}
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <div style={{ display: 'inline-flex', gap: '6px' }}>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        disabled={runNowMutation.isPending && runNowMutation.variables === t.id}
                        onClick={() => runNowMutation.mutate(t.id)}
                      >
                        ⚡ 立即同步
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        style={{ color: 'var(--primary)', fontWeight: 600 }}
                        onClick={() => {
                          setAppendModalTaskId(t.id);
                          setAppendWordsInput('');
                        }}
                      >
                        加词
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        style={{ color: '#d97706', fontWeight: 600 }}
                        onClick={() => {
                          setRemoveModalTaskId(t.id);
                          setRemoveWordSelect([]);
                        }}
                      >
                        减词
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        onClick={() => toggleMutation.mutate(t.id)}
                      >
                        {t.status === 'active' ? '暂停' : '恢复'}
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        style={{ color: 'var(--danger)' }}
                        onClick={() => setDeleteConfirmId(t.id)}
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 加词 Dialog */}
      <Dialog
        isOpen={appendModalTaskId !== null}
        onClose={() => setAppendModalTaskId(null)}
        title="向任务追加关键词"
        width="440px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            新词将立即加入该任务监控列表，并自动抓取数据填入飞书表格中：
          </p>
          <input
            type="text"
            className="form-control"
            placeholder="输入新关键词（空格或逗号分隔多词）"
            value={appendWordsInput}
            onChange={(e) => setAppendWordsInput(e.target.value)}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button type="button" className="btn btn-outline" onClick={() => setAppendModalTaskId(null)}>
              取消
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={appendMutation.isPending || !appendWordsInput.trim()}
              onClick={() => {
                if (appendModalTaskId) {
                  const words = appendWordsInput.replace(/[,，]/g, ' ').split(/\s+/).filter(Boolean);
                  appendMutation.mutate({ taskId: appendModalTaskId, words });
                }
              }}
            >
              确认加词
            </button>
          </div>
        </div>
      </Dialog>

      {/* 减词 Dialog */}
      <Dialog
        isOpen={removeModalTaskId !== null}
        onClose={() => setRemoveModalTaskId(null)}
        title="从任务移除关键词"
        width="480px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            被减掉的词将保留表格中的历史数据，但后续不再拉取更新：
          </p>
          <div style={{ maxHeight: '220px', overflowY: 'auto', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
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
                    border: '1px solid ' + (isSelected ? '#ef4444' : 'var(--border)'),
                    background: isSelected ? '#fef2f2' : '#ffffff',
                    color: isSelected ? '#ef4444' : 'var(--text)',
                  }}
                >
                  {kw}
                </span>
              );
            })}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button type="button" className="btn btn-outline" onClick={() => setRemoveModalTaskId(null)}>
              取消
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={removeMutation.isPending || removeWordSelect.length === 0}
              onClick={() => {
                if (removeModalTaskId) {
                  removeMutation.mutate({ taskId: removeModalTaskId, words: removeWordSelect });
                }
              }}
            >
              确认减去 ({removeWordSelect.length} 词)
            </button>
          </div>
        </div>
      </Dialog>

      {/* 删除确认 Dialog */}
      <Dialog
        isOpen={deleteConfirmId !== null}
        onClose={() => setDeleteConfirmId(null)}
        title="确认删除灵犀任务"
        width="400px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            确定要归档删除该灵犀关键词监控任务吗？飞书表格内容将保留，但不再触发后续同步。
          </p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button type="button" className="btn btn-outline" onClick={() => setDeleteConfirmId(null)}>
              取消
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={deleteMutation.isPending}
              onClick={() => deleteConfirmId && deleteMutation.mutate(deleteConfirmId)}
            >
              确认删除
            </button>
          </div>
        </div>
      </Dialog>
    </div>
  );
};

