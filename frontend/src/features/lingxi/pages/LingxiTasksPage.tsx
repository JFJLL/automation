import React, { useState } from 'react';
import { Clock, Play, Pause, Trash2, Plus, Minus, ExternalLink } from 'lucide-react';
import { formatRruleText } from '@/shared/utils/formatRrule';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchJson } from '@/shared/api/client';
import { Dialog } from '@/shared/components/Dialog';
import { Button } from '@/shared/components/Button';
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
      showSuccess(res.msg || '任务执行成功');
      queryClient.invalidateQueries({ queryKey: ['lingxiTasks'] });
      queryClient.invalidateQueries({ queryKey: ['lingxiRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '立即执行失败');
    },
  });

  const toggleMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/lingxi/tasks/${taskId}/toggle`, { method: 'POST' }),
    onSuccess: (res: any) => {
      showSuccess(`任务状态已切换为: ${res.new_status === 'active' ? '正常运行' : '已暂停'}`);
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
        body: JSON.stringify({ keywords: words }),
      }),
    onSuccess: () => {
      showSuccess('加词成功');
      setAppendModalTaskId(null);
      setAppendWordsInput('');
      queryClient.invalidateQueries({ queryKey: ['lingxiTasks'] });
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
      showSuccess('词项已移入回收站');
      setRemoveModalTaskId(null);
      setRemoveWordSelect([]);
      queryClient.invalidateQueries({ queryKey: ['lingxiTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '移除词项失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/lingxi/tasks/${taskId}`, { method: 'DELETE' }),
    onSuccess: () => {
      showSuccess('任务已成功删除');
      setDeleteConfirmId(null);
      queryClient.invalidateQueries({ queryKey: ['lingxiTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '删除任务失败');
    },
  });

  const activeTaskForRemove = tasks.find((t) => t.id === removeModalTaskId);

  return (
    <div className="tab-pane active" style={{ padding: '0 4px' }}>
      <div className="section-head" style={{ marginBottom: '16px' }}>
        <div className="section-title">
          <div className="title-icon" style={{ background: '#fef2f2', color: '#ef4444' }}>
            <Clock size={20} />
          </div>
          <div>
            <h2>灵犀关键词同步任务</h2>
            <div className="section-desc">管理小红书灵犀关键词定时监控与飞书表格自动化同步调度。</div>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="table" style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>任务名称</th>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>监控关键词</th>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>写入模式</th>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>同步周期</th>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>飞书表格</th>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>状态</th>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569', textAlign: 'right' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={7} style={{ padding: '30px', textAlign: 'center', color: '#94a3b8' }}>
                    加载任务中...
                  </td>
                </tr>
              ) : tasks.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>
                    暂无灵犀关键词同步任务，可在「查询与概览」页搜索关键词后保存为定时任务。
                  </td>
                </tr>
              ) : (
                tasks.map((task) => (
                  <tr key={task.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '12px 16px', fontWeight: 600, color: '#1e293b' }}>
                      {task.name}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span className="badge badge-gray">{task.keywords?.length || 0} 个词</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setAppendModalTaskId(task.id)}
                          title="添加关键词"
                        >
                          <Plus size={14} />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setRemoveModalTaskId(task.id);
                            setRemoveWordSelect([]);
                          }}
                          title="移除关键词"
                        >
                          <Minus size={14} />
                        </Button>
                      </div>
                    </td>
                    <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>
                      {task.update_mode === 'append' ? '历史追加' : '全量覆盖'}
                    </td>
                    <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>
                      {formatRruleText(task.rrule)}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <a
                        href={task.spreadsheet_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: '#0284c7', display: 'inline-flex', alignItems: 'center', gap: '4px', textDecoration: 'none' }}
                      >
                        <span>查看表格</span>
                        <ExternalLink size={13} />
                      </a>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <span className={`badge ${task.status === 'active' ? 'badge-success' : 'badge-gray'}`}>
                        {task.status === 'active' ? '运行中' : '已暂停'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '8px', alignItems: 'center' }}>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => runNowMutation.mutate(task.id)}
                          disabled={runNowMutation.isPending}
                        >
                          <Play size={13} style={{ marginRight: '4px' }} />
                          立即同步
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleMutation.mutate(task.id)}
                          disabled={toggleMutation.isPending}
                          title={task.status === 'active' ? '暂停任务' : '启动任务'}
                        >
                          {task.status === 'active' ? <Pause size={15} /> : <Play size={15} />}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteConfirmId(task.id)}
                          title="删除任务"
                        >
                          <Trash2 size={15} style={{ color: '#ef4444' }} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 加词弹窗 */}
      <Dialog
        isOpen={appendModalTaskId !== null}
        onClose={() => setAppendModalTaskId(null)}
        title="追加监控关键词"
        width="440px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              关键词（空格或回车分隔多个）
            </label>
            <textarea
              className="form-control"
              rows={4}
              placeholder="如：婴儿配方奶粉 羊奶粉推荐"
              value={appendWordsInput}
              onChange={(e) => setAppendWordsInput(e.target.value)}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <Button variant="outline" onClick={() => setAppendModalTaskId(null)}>取消</Button>
            <Button
              variant="primary"
              disabled={!appendWordsInput.trim() || appendMutation.isPending}
              onClick={() => {
                if (appendModalTaskId !== null) {
                  const words = appendWordsInput.replace(/,/g, ' ').split(/\s+/).map((w) => w.trim()).filter(Boolean);
                  appendMutation.mutate({ taskId: appendModalTaskId, words });
                }
              }}
            >
              确认追加
            </Button>
          </div>
        </div>
      </Dialog>

      {/* 减词弹窗 */}
      <Dialog
        isOpen={removeModalTaskId !== null}
        onClose={() => setRemoveModalTaskId(null)}
        title="移除关键词项"
        width="460px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ fontSize: '13px', color: '#64748b' }}>
            勾选需要从该定时监控任务中移除的关键词：
          </div>
          <div style={{ maxHeight: '200px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px', padding: '10px', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
            {activeTaskForRemove?.keywords?.map((kw: string) => (
              <label key={kw} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={removeWordSelect.includes(kw)}
                  onChange={(e) => {
                    if (e.target.checked) setRemoveWordSelect([...removeWordSelect, kw]);
                    else setRemoveWordSelect(removeWordSelect.filter((w) => w !== kw));
                  }}
                />
                <span>{kw}</span>
              </label>
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <Button variant="outline" onClick={() => setRemoveModalTaskId(null)}>取消</Button>
            <Button
              variant="primary"
              disabled={removeWordSelect.length === 0 || removeMutation.isPending}
              onClick={() => {
                if (removeModalTaskId !== null) {
                  removeMutation.mutate({ taskId: removeModalTaskId, words: removeWordSelect });
                }
              }}
            >
              确认移除
            </Button>
          </div>
        </div>
      </Dialog>

      {/* 删除确认弹窗 */}
      <Dialog
        isOpen={deleteConfirmId !== null}
        onClose={() => setDeleteConfirmId(null)}
        title="确认删除任务"
        width="380px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <p style={{ fontSize: '13px', color: '#475569', margin: 0 }}>
            确定要删除该灵犀关键词监控任务吗？删除后将停止定时自动同步，飞书中的历史表格将继续保留。
          </p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <Button variant="outline" onClick={() => setDeleteConfirmId(null)}>取消</Button>
            <Button
              variant="primary"
              style={{ backgroundColor: '#ef4444', borderColor: '#ef4444' }}
              disabled={deleteMutation.isPending}
              onClick={() => {
                if (deleteConfirmId !== null) deleteMutation.mutate(deleteConfirmId);
              }}
            >
              确认删除
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
};

