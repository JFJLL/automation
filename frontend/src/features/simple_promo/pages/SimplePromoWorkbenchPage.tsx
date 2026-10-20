import React, { useState, useEffect, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Search,
  ShieldCheck,
  ShieldAlert,
  Lock,
  Unlock,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  PlayCircle,
  Eye,
  CheckSquare,
  Square,
  RefreshCw,
  Filter,
  Copy,
  Check,
  RotateCcw,
  X
} from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { useToast } from '@/shared/components/Toast';
import { Dialog } from '@/shared/components/Dialog';
import { getPageCache, setPageCache } from '@/shared/utils/pageCache';

export const SimplePromoWorkbenchPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();

  // 账号选择与页面状态 (从内存缓存加载，跨板块切换不丢失数据)
  const [searchKw, setSearchKw] = useState(() => getPageCache('sp_searchKw', ''));
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set(getPageCache('sp_selectedIds', [])));
  const [cutoffDate, setCutoffDate] = useState(() => getPageCache('sp_cutoffDate', '2026-01-01 00:00:00'));
  const [whitelistModalOpen, setWhitelistModalOpen] = useState(false);
  const [whitelistText, setWhitelistText] = useState(() => getPageCache('sp_whitelistText', ''));

  // 二次确认执行弹窗
  const [confirmExecuteOpen, setConfirmExecuteOpen] = useState(false);
  const [ackRisk, setAckRisk] = useState(false);
  const [rollbackConfirmOpen, setRollbackConfirmOpen] = useState(false);

  // 巡检/执行结果
  const [scanResult, setScanResult] = useState<any | null>(() => getPageCache('sp_scanResult', null));
  const [resultFilter, setResultFilter] = useState<'all' | 'to_pause' | 'already_paused' | 'whitelist'>(() => getPageCache('sp_resultFilter', 'all'));
  const [copied, setCopied] = useState(false);

  // 状态自动同步到内存缓存 (网页内切换板块保留，刷新或重新打开后自动清空)
  useEffect(() => {
    setPageCache('sp_searchKw', searchKw);
  }, [searchKw]);

  useEffect(() => {
    setPageCache('sp_selectedIds', Array.from(selectedIds));
  }, [selectedIds]);

  useEffect(() => {
    setPageCache('sp_cutoffDate', cutoffDate);
  }, [cutoffDate]);

  useEffect(() => {
    setPageCache('sp_whitelistText', whitelistText);
  }, [whitelistText]);

  useEffect(() => {
    setPageCache('sp_scanResult', scanResult);
  }, [scanResult]);

  useEffect(() => {
    setPageCache('sp_resultFilter', resultFilter);
  }, [resultFilter]);

  // 获取全部子账号列表 (配置 staleTime 加快二次进入时的展示响应)
  const { data: subaccounts = [], isLoading: loadingAccounts, refetch: refetchAccounts } = useQuery<any[]>({
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

  // 过滤后的子账号列表
  const filteredAccounts = useMemo(() => {
    const kw = searchKw.trim().toLowerCase();
    if (!kw) return subaccounts;
    return subaccounts.filter(
      (acc) => acc.name.toLowerCase().includes(kw) || acc.id.toLowerCase().includes(kw)
    );
  }, [subaccounts, searchKw]);

  // 选中的账号对象列表
  const selectedAccountItems = useMemo(() => {
    return subaccounts.filter((acc) => selectedIds.has(acc.id)).map((acc) => ({ id: acc.id, name: acc.name }));
  }, [subaccounts, selectedIds]);

  // 快捷全选/反选
  const handleSelectAllFiltered = () => {
    const next = new Set(selectedIds);
    filteredAccounts.forEach((acc) => next.add(acc.id));
    setSelectedIds(next);
    setScanResult(null);
    setPageCache('sp_scanResult', null);
  };

  const handleClearSelected = () => {
    setSelectedIds(new Set());
    setScanResult(null);
    setPageCache('sp_scanResult', null);
  };

  const toggleAccount = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedIds(next);
    setScanResult(null);
    setPageCache('sp_scanResult', null);
  };

  // 巡检预览 Mutation (Dry Run)
  const inspectMutation = useMutation({
    mutationFn: (body: any) =>
      fetchJson('/api/simple-promo/inspect', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: async (res: any) => {
      showSuccess('巡检预览完成');
      // 拉取最新生成的 Run 明细
      if (res.run_id) {
        const detail = await fetchJson(`/api/simple-promo/runs/${res.run_id}`);
        setScanResult(detail);
      }
      queryClient.invalidateQueries({ queryKey: ['simplePromoRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '巡检预览失败');
    },
  });

  // 真实执行暂停 Mutation
  const executeMutation = useMutation({
    mutationFn: (body: any) =>
      fetchJson('/api/simple-promo/execute', {
        method: 'POST',
        headers: {
          'x-simple-promo-token': sessionStorage.getItem('simple_promo_token') || '',
        },
        body: JSON.stringify(body),
      }),
    onSuccess: async (res: any) => {
      showSuccess('线上批量暂停执行完成');
      setConfirmExecuteOpen(false);
      setAckRisk(false);
      if (res.run_id) {
        const detail = await fetchJson(`/api/simple-promo/runs/${res.run_id}`);
        setScanResult(detail);
      }
      queryClient.invalidateQueries({ queryKey: ['simplePromoRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '执行暂停失败');
    },
  });

  // 一键原样恢复 Mutation
  const rollbackMutation = useMutation({
    mutationFn: (runId: number) =>
      fetchJson(`/api/simple-promo/runs/${runId}/rollback`, {
        method: 'POST',
        headers: {
          'x-simple-promo-token': sessionStorage.getItem('simple_promo_token') || '',
        },
        body: JSON.stringify({ confirm: true }),
      }),
    onSuccess: async (res: any) => {
      showSuccess(res.message || '已成功将该批次笔记原样恢复为【开启投放】！');
      setRollbackConfirmOpen(false);
      if (scanResult?.id) {
        const detail = await fetchJson(`/api/simple-promo/runs/${scanResult.id}`);
        setScanResult(detail);
        setPageCache('sp_scanResult', detail);
      }
      queryClient.invalidateQueries({ queryKey: ['simplePromoRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '一键恢复失败');
    },
  });

  const handleStartInspect = () => {
    if (selectedAccountItems.length === 0) {
      showError('请先选择至少一个聚光子账号');
      return;
    }
    setScanResult(null);
    setPageCache('sp_scanResult', null);
    const whitelist = whitelistText
      .split(/[\n,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    inspectMutation.mutate({
      accounts: selectedAccountItems,
      cutoff_date: cutoffDate.trim(),
      whitelist_note_ids: whitelist,
    });
  };

  const handleStartExecute = () => {
    if (selectedAccountItems.length === 0) {
      showError('请先选择至少一个聚光子账号');
      return;
    }
    setConfirmExecuteOpen(true);
  };

  const handleConfirmSubmit = () => {
    const whitelist = whitelistText
      .split(/[\n,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    executeMutation.mutate({
      accounts: selectedAccountItems,
      cutoff_date: cutoffDate.trim(),
      whitelist_note_ids: whitelist,
      confirm: true,
    });
  };

  // 结果列表过滤
  const resultItems = useMemo(() => {
    const list = scanResult?.items || [];
    if (resultFilter === 'to_pause') {
      return list.filter((it: any) => it.action === '待暂停' || it.result_status === '已暂停');
    }
    if (resultFilter === 'already_paused') {
      return list.filter((it: any) => it.result_status === '无需操作' || it.original_status === '已暂停');
    }
    if (resultFilter === 'whitelist') {
      return list.filter((it: any) => it.result_status === '跳过');
    }
    return list;
  }, [scanResult, resultFilter]);

  // 复制表格数据到剪贴板 (TSV格式直接无缝粘贴到 Excel)
  const handleCopyTableData = async () => {
    if (!resultItems || resultItems.length === 0) {
      showError('暂无数据可复制');
      return;
    }
    const headers = ['子账号', '笔记标题', '笔记ID', '发布时间', '原投放状态', '操作动作', '处理状态'];
    const rows = resultItems.map((item: any) => [
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

  // 动态提取截止日期的日期部分用于标题展示
  const displayCutoffDate = (scanResult?.cutoff_date || cutoffDate).split(' ')[0] || '截止日';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* 头部导航与安全状态 */}
      <div className="card" style={{ padding: '16px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>简单投笔记暂停巡检工作台</span>
              <span
                style={{
                  fontSize: '11px',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  backgroundColor: 'var(--primary-light)',
                  color: 'var(--primary)',
                  fontWeight: 500,
                }}
              >
                聚光 Aurora
              </span>
            </h2>
            <p style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
              自动检测聚光简单投推广计划，精准识别老笔记并批量暂停（支持一键恢复投放，数据自动同步至飞书）
            </p>
          </div>
        </div>
      </div>

      {/* 第一步：选择聚光子账号与巡检条件 */}
      <div className="card" style={{ padding: '20px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#1e293b' }}>
            1. 选择目标聚光子账号 ({selectedIds.size} 个已选)
          </h3>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <button
              type="button"
              onClick={handleSelectAllFiltered}
              style={{ fontSize: '12px', color: '#2563eb', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              全选筛选结果
            </button>
            <span style={{ color: '#cbd5e1' }}>|</span>
            <button
              type="button"
              onClick={handleClearSelected}
              style={{ fontSize: '12px', color: '#64748b', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              清空已选
            </button>
          </div>
        </div>

        {/* 已选账号 Tags */}
        {selectedAccountItems.length > 0 && (
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '6px',
              padding: '8px 12px',
              background: '#f8fafc',
              borderRadius: '6px',
              border: '1px solid #e2e8f0',
              maxHeight: '96px',
              overflowY: 'auto',
              marginBottom: '12px',
            }}
          >
            {selectedAccountItems.map((acc) => (
              <span
                key={acc.id}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '12px',
                  padding: '3px 8px',
                  backgroundColor: '#ffffff',
                  border: '1px solid #cbd5e1',
                  borderRadius: '4px',
                  color: '#334155',
                }}
              >
                <span>{acc.name}</span>
                <button
                  type="button"
                  onClick={() => toggleAccount(acc.id)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: '#94a3b8' }}
                >
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>
        )}

        {/* 搜索与子账号筛选网格 */}
        <div style={{ position: 'relative', marginBottom: '12px' }}>
          <input
            type="text"
            value={searchKw}
            onChange={(e) => setSearchKw(e.target.value)}
            placeholder="输入品牌关键词（如 凯乐石、红京、EX3）或子账号ID进行快速检索..."
            style={{
              width: '100%',
              padding: '8px 12px 8px 34px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '13px',
              outline: 'none',
            }}
          />
          <Search
            size={16}
            style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }}
          />
        </div>

        <div
          style={{
            maxHeight: '180px',
            overflowY: 'auto',
            border: '1px solid #e2e8f0',
            borderRadius: '6px',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: '1px',
            backgroundColor: '#e2e8f0',
          }}
        >
          {loadingAccounts ? (
            <div style={{ gridColumn: '1 / -1', padding: '30px', textAlign: 'center', backgroundColor: '#ffffff', color: '#94a3b8' }}>
              正在加载聚光子账号凭据与状态...
            </div>
          ) : filteredAccounts.length === 0 ? (
            <div style={{ gridColumn: '1 / -1', padding: '30px', textAlign: 'center', backgroundColor: '#ffffff', color: '#94a3b8' }}>
              未搜索到匹配的聚光子账号
            </div>
          ) : (
            filteredAccounts.map((acc) => {
              const isChecked = selectedIds.has(acc.id);
              return (
                <div
                  key={acc.id}
                  onClick={() => toggleAccount(acc.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    backgroundColor: isChecked ? '#fff1f2' : '#ffffff',
                    cursor: 'pointer',
                    userSelect: 'none',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                    {isChecked ? (
                      <CheckSquare size={16} color="var(--primary)" style={{ flexShrink: 0 }} />
                    ) : (
                      <Square size={16} color="#94a3b8" style={{ flexShrink: 0 }} />
                    )}
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: '13px',
                          fontWeight: 500,
                          color: '#1e293b',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                        title={acc.name}
                      >
                        {acc.name}
                      </div>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>{acc.id}</div>
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: '11px',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      backgroundColor: acc.has_cookie !== false ? '#ecfdf5' : '#fef2f2',
                      color: acc.has_cookie !== false ? '#059669' : '#dc2626',
                      flexShrink: 0,
                      marginLeft: '6px',
                    }}
                  >
                    {acc.has_cookie !== false ? 'Cookie有效' : '无凭据'}
                  </span>
                </div>
              );
            })
          )}
        </div>

        {/* 条件配置与操作栏 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginTop: '16px',
            paddingTop: '16px',
            borderTop: '1px solid #f1f5f9',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '13px', color: '#475569', fontWeight: 500 }}>老笔记截止时间：</span>
              <input
                type="text"
                value={cutoffDate}
                onChange={(e) => setCutoffDate(e.target.value)}
                style={{
                  padding: '6px 10px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '13px',
                  width: '180px',
                }}
              />
            </div>
            <button
              type="button"
              onClick={() => setWhitelistModalOpen(true)}
              style={{
                fontSize: '13px',
                color: '#2563eb',
                background: '#eff6ff',
                border: '1px solid #bfdbfe',
                padding: '6px 12px',
                borderRadius: '6px',
                cursor: 'pointer',
              }}
            >
              白名单保护 ({whitelistText.split(/[\n,;]+/).filter(Boolean).length} 篇)
            </button>
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              type="button"
              onClick={handleStartInspect}
              disabled={inspectMutation.isPending || executeMutation.isPending}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 18px',
                borderRadius: '6px',
                backgroundColor: '#ffffff',
                color: '#334155',
                border: '1px solid #cbd5e1',
                fontSize: '13px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              <Eye size={16} />
              {inspectMutation.isPending ? '正在查询数据...' : '查询数据'}
            </button>

            <button
              type="button"
              onClick={handleStartExecute}
              disabled={inspectMutation.isPending || executeMutation.isPending}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 20px',
                borderRadius: '6px',
                backgroundColor: 'var(--primary)',
                color: '#ffffff',
                border: 'none',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
                boxShadow: '0 1px 3px rgba(239, 43, 58, 0.3)',
              }}
            >
              <PlayCircle size={16} />
              {executeMutation.isPending ? '正在暂停下发中...' : '确认执行线上暂停'}
            </button>
          </div>
        </div>
      </div>

      {/* 第二步：巡检与暂停结果呈现 */}
      {scanResult && (
        <div className="card" style={{ padding: '20px 24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div>
              <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#1e293b' }}>
                2. 巡检明细与投放状态报告 (Run #{scanResult.id})
              </h3>
              <p style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                {scanResult.message}
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {scanResult.paused_success_count > 0 && (
                <button
                  type="button"
                  onClick={() => setRollbackConfirmOpen(true)}
                  disabled={rollbackMutation.isPending}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '6px 12px',
                    borderRadius: '6px',
                    border: '1px solid #93c5fd',
                    backgroundColor: '#eff6ff',
                    cursor: 'pointer',
                    fontSize: '12px',
                    color: '#2563eb',
                    fontWeight: 500,
                  }}
                >
                  <RotateCcw size={13} />
                  <span>{rollbackMutation.isPending ? '正在恢复中...' : '一键原样恢复本次投放'}</span>
                </button>
              )}
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={handleCopyTableData}
                title="复制表格内容，可直接在 Excel 中按 Ctrl+V 粘贴"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  cursor: 'pointer',
                  fontSize: '12px',
                  color: '#334155',
                }}
              >
                {copied ? <Check size={13} color="#059669" /> : <Copy size={13} />}
                <span>{copied ? '已复制' : '复制表格数据'}</span>
              </button>
              <button
                type="button"
                onClick={() => window.open(`/api/simple-promo/runs/${scanResult.id}/export`, '_blank')}
                style={{
                  fontSize: '12px',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  cursor: 'pointer',
                  color: '#334155',
                }}
              >
                📥 导出当前结果 CSV
              </button>
            </div>
          </div>

          {/* 统计指标卡 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px', marginBottom: '16px' }}>
            <div style={{ padding: '12px 16px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
              <div style={{ fontSize: '12px', color: '#64748b' }}>扫描笔记总数</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', marginTop: '4px' }}>
                {scanResult.total_notes_scanned} 篇
              </div>
            </div>
            <div style={{ padding: '12px 16px', background: '#fffbeb', borderRadius: '8px', border: '1px solid #fef3c7' }}>
              <div style={{ fontSize: '12px', color: '#b45309' }}>{displayCutoffDate} 前老笔记</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: '#d97706', marginTop: '4px' }}>
                {scanResult.pre_cutoff_notes_count} 篇
              </div>
            </div>
            <div style={{ padding: '12px 16px', background: '#fef2f2', borderRadius: '8px', border: '1px solid #fee2e2' }}>
              <div style={{ fontSize: '12px', color: '#b91c1c' }}>
                {scanResult.mode === 'EXECUTE' ? '已成功暂停' : '待暂停老笔记'}
              </div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: '#dc2626', marginTop: '4px' }}>
                {scanResult.mode === 'EXECUTE' ? scanResult.paused_success_count : scanResult.to_pause_count} 篇
              </div>
            </div>
            <div style={{ padding: '12px 16px', background: '#ecfdf5', borderRadius: '8px', border: '1px solid #d1fae5' }}>
              <div style={{ fontSize: '12px', color: '#047857' }}>原已处于暂停</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: '#059669', marginTop: '4px' }}>
                {scanResult.already_paused_count} 篇
              </div>
            </div>
            <div style={{ padding: '12px 16px', background: '#f0fdf4', borderRadius: '8px', border: '1px solid #dcfce7' }}>
              <div style={{ fontSize: '12px', color: '#15803d' }}>{displayCutoffDate} 后新笔记保留</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: '#16a34a', marginTop: '4px' }}>
                {scanResult.total_notes_scanned - scanResult.pre_cutoff_notes_count} 篇
              </div>
            </div>
          </div>

          {/* 筛选选项卡 */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '12px', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px' }}>
            <button
              type="button"
              onClick={() => setResultFilter('all')}
              style={{
                padding: '4px 12px',
                borderRadius: '4px',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
                border: 'none',
                backgroundColor: resultFilter === 'all' ? '#1e293b' : 'transparent',
                color: resultFilter === 'all' ? '#ffffff' : '#64748b',
              }}
            >
              全部排查老笔记 ({scanResult.items?.length || 0})
            </button>
            <button
              type="button"
              onClick={() => setResultFilter('to_pause')}
              style={{
                padding: '4px 12px',
                borderRadius: '4px',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
                border: 'none',
                backgroundColor: resultFilter === 'to_pause' ? '#dc2626' : 'transparent',
                color: resultFilter === 'to_pause' ? '#ffffff' : '#64748b',
              }}
            >
              本次暂停 / 待暂停
            </button>
            <button
              type="button"
              onClick={() => setResultFilter('already_paused')}
              style={{
                padding: '4px 12px',
                borderRadius: '4px',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
                border: 'none',
                backgroundColor: resultFilter === 'already_paused' ? '#059669' : 'transparent',
                color: resultFilter === 'already_paused' ? '#ffffff' : '#64748b',
              }}
            >
              原已处于暂停
            </button>
          </div>

          {/* 笔记结果表格 */}
          <div style={{ maxHeight: '380px', overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
            {resultItems.length === 0 ? (
              <div style={{ padding: '60px 20px', textAlign: 'center', color: '#94a3b8' }}>
                <div style={{ fontSize: '15px', fontWeight: 600, color: '#475569', marginBottom: '6px' }}>
                  未获取到数据
                </div>
                <div style={{ fontSize: '13px', color: '#64748b' }}>
                  当前查询的子账号下暂无简单投推广计划或老笔记数据
                </div>
              </div>
            ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead style={{ position: 'sticky', top: 0, backgroundColor: '#f8fafc', zIndex: 5 }}>
                <tr style={{ borderBottom: '1px solid #e2e8f0', textAlign: 'left', color: '#64748b' }}>
                  <th style={{ padding: '8px 12px', fontWeight: 600 }}>子账号</th>
                  <th style={{ padding: '8px 12px', fontWeight: 600 }}>笔记标题</th>
                  <th style={{ padding: '8px 12px', fontWeight: 600 }}>笔记ID / 链接</th>
                  <th style={{ padding: '8px 12px', fontWeight: 600 }}>发布时间</th>
                  <th style={{ padding: '8px 12px', fontWeight: 600 }}>原投放状态</th>
                  <th style={{ padding: '8px 12px', fontWeight: 600 }}>操作动作</th>
                  <th style={{ padding: '8px 12px', fontWeight: 600 }}>处理状态</th>
                </tr>
              </thead>
              <tbody>
                {resultItems.map((item: any) => (
                  <tr key={item.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 12px', color: '#1e293b' }}>
                      <strong>{item.account_name}</strong>
                    </td>
                    <td style={{ padding: '8px 12px', maxWidth: '300px', color: '#334155' }}>
                      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.note_title}>
                        {item.note_title || '（无标题）'}
                      </div>
                    </td>
                    <td style={{ padding: '8px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <span style={{ fontFamily: 'monospace', color: '#64748b', fontSize: '12px' }}>{item.note_id}</span>
                        {item.note_url && (
                          <a href={item.note_url} target="_blank" rel="noreferrer" title="打开小红书笔记" style={{ color: 'var(--primary)' }}>
                            <ExternalLink size={12} />
                          </a>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: '8px 12px', color: '#64748b', whiteSpace: 'nowrap' }}>{item.note_publish_time}</td>
                    <td style={{ padding: '8px 12px' }}>
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
                    <td style={{ padding: '8px 12px', color: '#334155' }}>{item.action}</td>
                    <td style={{ padding: '8px 12px' }}>
                      <span
                        style={{
                          fontSize: '11px',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          backgroundColor: item.result_status === '已暂停' ? '#fee2e2' : '#f1f5f9',
                          color: item.result_status === '已暂停' ? '#dc2626' : '#64748b',
                          fontWeight: 500,
                        }}
                      >
                        {item.result_status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            )}
          </div>
        </div>
      )}

      {/* 白名单保护设置弹窗 */}
      <Dialog isOpen={whitelistModalOpen} onClose={() => setWhitelistModalOpen(false)} title="排除白名单笔记设置" width="500px">
        <div style={{ marginBottom: '14px', fontSize: '13px', color: '#64748b', lineHeight: 1.5 }}>
          输入不希望被暂停的优质老笔记 ID（每行一个或逗号隔开）。巡检与批量暂停时将自动跳过这些笔记。
        </div>
        <textarea
          value={whitelistText}
          onChange={(e) => setWhitelistText(e.target.value)}
          placeholder="例如：&#10;68625ca4000000000d019ace&#10;6773d02f000000000800df66"
          rows={6}
          style={{
            width: '100%',
            padding: '10px',
            borderRadius: '6px',
            border: '1px solid #cbd5e1',
            fontSize: '13px',
            outline: 'none',
            fontFamily: 'monospace',
            marginBottom: '16px',
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button
            type="button"
            onClick={() => setWhitelistModalOpen(false)}
            style={{ padding: '6px 14px', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#fff', cursor: 'pointer' }}
          >
            确定
          </button>
        </div>
      </Dialog>

      {/* 执行暂停动作二次确认弹窗 */}
      <Dialog isOpen={confirmExecuteOpen} onClose={() => setConfirmExecuteOpen(false)} title="确认执行线上暂停操作" width="480px">
        <div style={{ display: 'flex', gap: '14px', marginBottom: '16px' }}>
          <div style={{ color: '#dc2626' }}>
            <AlertTriangle size={32} />
          </div>
          <div>
            <h4 style={{ fontSize: '15px', fontWeight: 600, color: '#1e293b', marginBottom: '4px' }}>
              即将向小红书聚光下发批量暂停请求
            </h4>
            <p style={{ fontSize: '13px', color: '#64748b', lineHeight: 1.5 }}>
              该操作将直接修改当前选中的 <strong>{selectedAccountItems.length}</strong> 个子账号线上简单投创意状态。
              早于 <strong>{cutoffDate}</strong> 且不在白名单中的老笔记创意将被变更为【暂停】状态。
            </p>
          </div>
        </div>

        <div style={{ padding: '12px', background: '#f8fafc', borderRadius: '6px', marginBottom: '16px', fontSize: '13px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={ackRisk}
              onChange={(e) => setAckRisk(e.target.checked)}
              style={{ width: '16px', height: '16px' }}
            />
            <span style={{ color: '#334155' }}>我已核对所选子账号，确认执行线上暂停指令</span>
          </label>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button
            type="button"
            onClick={() => setConfirmExecuteOpen(false)}
            style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#fff', cursor: 'pointer' }}
          >
            取消
          </button>
          <button
            type="button"
            disabled={!ackRisk || executeMutation.isPending}
            onClick={handleConfirmSubmit}
            style={{
              padding: '8px 20px',
              borderRadius: '6px',
              backgroundColor: ackRisk ? '#dc2626' : '#cbd5e1',
              color: '#ffffff',
              border: 'none',
              cursor: ackRisk ? 'pointer' : 'not-allowed',
              fontWeight: 600,
            }}
          >
            {executeMutation.isPending ? '正在暂停中...' : '确认立即暂停'}
          </button>
        </div>
      </Dialog>

      {/* 一键恢复投放确认弹窗 */}
      <Dialog isOpen={rollbackConfirmOpen} onClose={() => setRollbackConfirmOpen(false)} title="确认一键恢复开启投放" width="480px">
        <div style={{ display: 'flex', gap: '14px', marginBottom: '16px' }}>
          <div style={{ color: '#2563eb' }}>
            <RotateCcw size={32} />
          </div>
          <div>
            <h4 style={{ fontSize: '15px', fontWeight: 600, color: '#1e293b', marginBottom: '4px' }}>
              一键恢复该批次全部老笔记为【开启投放】
            </h4>
            <p style={{ fontSize: '13px', color: '#64748b', lineHeight: 1.5 }}>
              确认向小红书聚光网关下发指令，将 Run #{scanResult?.id} 中成功暂停的 <strong>{scanResult?.paused_success_count}</strong> 篇老笔记全部原样恢复为【开启投放】（actionType=1）状态吗？
            </p>
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button
            type="button"
            onClick={() => setRollbackConfirmOpen(false)}
            style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#fff', cursor: 'pointer' }}
          >
            取消
          </button>
          <button
            type="button"
            disabled={rollbackMutation.isPending}
            onClick={() => scanResult?.id && rollbackMutation.mutate(scanResult.id)}
            style={{
              padding: '8px 20px',
              borderRadius: '6px',
              backgroundColor: '#2563eb',
              color: '#ffffff',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            {rollbackMutation.isPending ? '正在恢复下发中...' : '立即确认恢复投放'}
          </button>
        </div>
      </Dialog>
    </div>
  );
};
