import React, { useState, useEffect, useMemo } from 'react';
import { Search, X, Check, CheckSquare, Square, ShieldCheck, AlertCircle } from 'lucide-react';
import { Dialog } from '@/shared/components/Dialog';
import { SchedulePicker } from '@/shared/components/SchedulePicker';
import { useToast } from '@/shared/components/Toast';
import { fetchJson } from '@/shared/api/client';

export interface Subaccount {
  id: string;
  name: string;
  has_cookie?: boolean;
  status?: number;
}

export interface SimplePromoTask {
  id?: number;
  name: string;
  accounts: Array<{ id: string; name: string }>;
  cutoff_date: string;
  whitelist_note_ids: string[];
  rrule: string;
  status?: string;
}

export interface CreateOrEditSimplePromoTaskDialogProps {
  isOpen: boolean;
  onClose: () => void;
  task?: SimplePromoTask | null;
  onSuccess: () => void;
  subaccounts: Subaccount[];
}

export const CreateOrEditSimplePromoTaskDialog: React.FC<CreateOrEditSimplePromoTaskDialogProps> = ({
  isOpen,
  onClose,
  task,
  onSuccess,
  subaccounts,
}) => {
  const { showSuccess, showError } = useToast();
  const isEdit = Boolean(task?.id);

  const [name, setName] = useState('');
  const [selectedAccounts, setSelectedAccounts] = useState<Array<{ id: string; name: string }>>([]);
  const [cutoffDate, setCutoffDate] = useState('2026-01-01 00:00:00');
  const [whitelistText, setWhitelistText] = useState('');
  const [rrule, setRrule] = useState('RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0');
  const [searchKw, setSearchKw] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (isOpen) {
      if (task) {
        setName(task.name || '');
        setSelectedAccounts(task.accounts || []);
        setCutoffDate(task.cutoff_date || '2026-01-01 00:00:00');
        setWhitelistText((task.whitelist_note_ids || []).join('\n'));
        setRrule(task.rrule || 'RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0');
      } else {
        setName('聚光简单投老笔记巡检暂停');
        setSelectedAccounts([]);
        setCutoffDate('2026-01-01 00:00:00');
        setWhitelistText('');
        setRrule('RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0');
      }
      setSearchKw('');
    }
  }, [isOpen, task]);

  const filteredSubaccounts = useMemo(() => {
    const kw = searchKw.trim().toLowerCase();
    if (!kw) return subaccounts;
    return subaccounts.filter(
      (acc) => acc.name.toLowerCase().includes(kw) || acc.id.toLowerCase().includes(kw)
    );
  }, [subaccounts, searchKw]);

  const selectedIds = useMemo(() => new Set(selectedAccounts.map((a) => a.id)), [selectedAccounts]);

  const toggleAccount = (acc: Subaccount) => {
    if (selectedIds.has(acc.id)) {
      setSelectedAccounts(selectedAccounts.filter((a) => a.id !== acc.id));
    } else {
      setSelectedAccounts([...selectedAccounts, { id: acc.id, name: acc.name }]);
    }
  };

  const handleSelectAllFiltered = () => {
    const toAdd: Array<{ id: string; name: string }> = [];
    for (const acc of filteredSubaccounts) {
      if (!selectedIds.has(acc.id)) {
        toAdd.push({ id: acc.id, name: acc.name });
      }
    }
    setSelectedAccounts([...selectedAccounts, ...toAdd]);
  };

  const handleDeselectAllFiltered = () => {
    const filteredIdSet = new Set(filteredSubaccounts.map((a) => a.id));
    setSelectedAccounts(selectedAccounts.filter((a) => !filteredIdSet.has(a.id)));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      showError('请输入任务名称');
      return;
    }
    if (selectedAccounts.length === 0) {
      showError('请至少勾选一个子账号');
      return;
    }
    const whitelist = whitelistText
      .split(/[\n,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    setSubmitting(true);
    try {
      if (isEdit && task?.id) {
        await fetchJson(`/api/simple-promo/tasks/${task.id}`, {
          method: 'PUT',
          body: JSON.stringify({
            name: name.trim(),
            accounts: selectedAccounts,
            cutoff_date: cutoffDate.trim(),
            whitelist_note_ids: whitelist,
            rrule,
          }),
        });
        showSuccess('任务更新成功');
      } else {
        await fetchJson('/api/simple-promo/tasks', {
          method: 'POST',
          body: JSON.stringify({
            name: name.trim(),
            accounts: selectedAccounts,
            cutoff_date: cutoffDate.trim(),
            whitelist_note_ids: whitelist,
            rrule,
          }),
        });
        showSuccess('新建任务成功');
      }
      onSuccess();
      onClose();
    } catch (err: any) {
      showError(err.message || '保存失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title={isEdit ? '编辑简单投定时巡检任务' : '新建简单投定时巡检任务'}
      width="680px"
    >
      <form onSubmit={handleSubmit}>
        {/* 任务名称 */}
        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>
            任务名称 <span style={{ color: 'var(--primary)' }}>*</span>
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例如：凯乐石简单投老笔记日常巡检暂停"
            style={{
              width: '100%',
              padding: '8px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '14px',
              outline: 'none',
            }}
          />
        </div>

        {/* 子账号选择与增删 */}
        <div style={{ marginBottom: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#1e293b' }}>
              目标聚光子账号 ({selectedAccounts.length} 个已选) <span style={{ color: 'var(--primary)' }}>*</span>
            </label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                onClick={handleSelectAllFiltered}
                style={{
                  fontSize: '12px',
                  color: 'var(--primary)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                全选匹配
              </button>
              <span style={{ color: '#cbd5e1' }}>|</span>
              <button
                type="button"
                onClick={handleDeselectAllFiltered}
                style={{
                  fontSize: '12px',
                  color: '#64748b',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                取消已筛选
              </button>
            </div>
          </div>

          {/* 已选子账号标签栏 */}
          {selectedAccounts.length > 0 && (
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '6px',
                padding: '8px 10px',
                background: '#f8fafc',
                borderRadius: '6px',
                border: '1px solid #e2e8f0',
                maxHeight: '90px',
                overflowY: 'auto',
                marginBottom: '8px',
              }}
            >
              {selectedAccounts.map((acc) => (
                <span
                  key={acc.id}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    fontSize: '12px',
                    padding: '2px 8px',
                    backgroundColor: '#ffffff',
                    border: '1px solid #cbd5e1',
                    borderRadius: '4px',
                    color: '#334155',
                  }}
                >
                  <span>{acc.name}</span>
                  <button
                    type="button"
                    onClick={() => toggleAccount(acc as Subaccount)}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: 0,
                      color: '#94a3b8',
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    <X size={13} />
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* 搜索子账号 */}
          <div style={{ position: 'relative', marginBottom: '8px' }}>
            <input
              type="text"
              value={searchKw}
              onChange={(e) => setSearchKw(e.target.value)}
              placeholder="搜索子账号名称或 ID..."
              style={{
                width: '100%',
                padding: '7px 10px 7px 32px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '13px',
                outline: 'none',
              }}
            />
            <Search
              size={15}
              style={{
                position: 'absolute',
                left: '10px',
                top: '50%',
                transform: 'translateY(-50%)',
                color: '#94a3b8',
              }}
            />
          </div>

          {/* 子账号可滚动多选列表 */}
          <div
            style={{
              maxHeight: '160px',
              overflowY: 'auto',
              border: '1px solid #e2e8f0',
              borderRadius: '6px',
              backgroundColor: '#ffffff',
            }}
          >
            {filteredSubaccounts.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
                未匹配到相关子账号
              </div>
            ) : (
              filteredSubaccounts.map((acc) => {
                const isChecked = selectedIds.has(acc.id);
                return (
                  <div
                    key={acc.id}
                    onClick={() => toggleAccount(acc)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 12px',
                      borderBottom: '1px solid #f1f5f9',
                      cursor: 'pointer',
                      backgroundColor: isChecked ? '#fff1f2' : 'transparent',
                      transition: 'background-color 0.1s ease',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {isChecked ? (
                        <CheckSquare size={16} color="var(--primary)" />
                      ) : (
                        <Square size={16} color="#94a3b8" />
                      )}
                      <div>
                        <div style={{ fontSize: '13px', fontWeight: 500, color: '#1e293b' }}>{acc.name}</div>
                        <div style={{ fontSize: '11px', color: '#64748b' }}>ID: {acc.id}</div>
                      </div>
                    </div>
                    <div>
                      {acc.has_cookie !== false ? (
                        <span
                          style={{
                            fontSize: '11px',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            backgroundColor: '#ecfdf5',
                            color: '#059669',
                          }}
                        >
                          Cookie有效
                        </span>
                      ) : (
                        <span
                          style={{
                            fontSize: '11px',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            backgroundColor: '#fef2f2',
                            color: '#dc2626',
                          }}
                        >
                          未配置凭据
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* 截止时间设置 */}
        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>
            老笔记发布时间截止点 (早于该时间的笔记将执行暂停)
          </label>
          <input
            type="text"
            value={cutoffDate}
            onChange={(e) => setCutoffDate(e.target.value)}
            placeholder="格式：2026-01-01 00:00:00"
            style={{
              width: '100%',
              padding: '8px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '14px',
              outline: 'none',
            }}
          />
          <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
            提示：默认为 2026-01-01 00:00:00，也可按需输入如 2025-06-01 00:00:00 等自定义时间。
          </div>
        </div>

        {/* 例外白名单笔记 */}
        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>
            保护白名单笔记 ID (可选，多行或逗号分隔)
          </label>
          <textarea
            value={whitelistText}
            onChange={(e) => setWhitelistText(e.target.value)}
            placeholder="输入不需要暂停的高转化老笔记 ID，每行一个..."
            rows={2}
            style={{
              width: '100%',
              padding: '8px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '13px',
              outline: 'none',
              resize: 'vertical',
            }}
          />
        </div>

        {/* 定时规则 */}
        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>
            巡检运行时间
          </label>
          <SchedulePicker value={rrule} onChange={(val) => setRrule(val)} />
        </div>

        {/* 底部操作 */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', paddingTop: '10px', borderTop: '1px solid #e2e8f0' }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              cursor: 'pointer',
              fontSize: '13px',
            }}
          >
            取消
          </button>
          <button
            type="submit"
            disabled={submitting}
            style={{
              padding: '8px 20px',
              borderRadius: '6px',
              backgroundColor: 'var(--primary)',
              color: '#ffffff',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '13px',
            }}
          >
            {submitting ? '保存中...' : isEdit ? '保存更改' : '立即创建'}
          </button>
        </div>
      </form>
    </Dialog>
  );
};
