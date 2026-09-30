import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Search,
  Calendar,
  Layers,
  FileSpreadsheet,
  Clock,
  Plus,
  X,
  AlertTriangle,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Sparkles,
  GripHorizontal
} from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Button } from '@/shared/components/Button';
import { StatusBadge } from '@/shared/components/Badge';
import { Dialog } from '@/shared/components/Dialog';
import { useToast } from '@/shared/components/Toast';

export const KeywordInsightPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError, showInfo } = useToast();

  const [inputWord, setInputWord] = useState('');
  const [selectedWords, setSelectedWords] = useState<string[]>(['凯乐石']);
  const [activeCategory, setActiveCategory] = useState<string>('全部');
  const [activeSubCategory, setActiveSubCategory] = useState<string>('');
  const [libraryHeight, setLibraryHeight] = useState<number>(() => {
    return parseInt(localStorage.getItem('kw_lib_height') || '260', 10);
  });
  const [libraryCollapsed, setLibraryCollapsed] = useState(false);

  // 日期范围计算 (统一 T-1/T-2 逻辑)
  const now = new Date();
  const isAfterNoon = now.getHours() >= 12;
  const offsetDays = isAfterNoon ? 1 : 2;
  
  const formatDate = (d: Date) => d.toISOString().split('T')[0];
  const maxAvailDate = new Date(now.getTime() - offsetDays * 86400 * 1000);
  const defaultStartDate = new Date(maxAvailDate.getTime() - 29 * 86400 * 1000);

  const [startDate, setStartDate] = useState(formatDate(defaultStartDate));
  const [endDate, setEndDate] = useState(formatDate(maxAvailDate));

  // 弹窗状态
  const [directSheetOpen, setDirectSheetOpen] = useState(false);
  const [directSheetTitle, setDirectSheetTitle] = useState('');
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [taskName, setTaskName] = useState('');
  const [taskUpdateMode, setTaskUpdateMode] = useState('overwrite');
  const [taskRrule, setTaskRrule] = useState('FREQ=DAILY;BYHOUR=12;BYMINUTE=30');

  // 获取关键词库
  const { data: libraryData } = useQuery<{
    categories: Record<string, Record<string, string[]>>;
    counts: Record<string, any>;
    all_keywords: string[];
  }>({
    queryKey: ['keywordLibrary'],
    queryFn: () => fetchJson('/api/keyword/library'),
    staleTime: 5 * 60 * 1000,
  });

  // 搜索查询
  const searchMutation = useMutation({
    mutationFn: (kws: string[]) =>
      fetchJson<{
        success: boolean;
        overall_status: string;
        keywords: string[];
        start_date: string;
        end_date: string;
        dates: string[];
        data: Record<string, Record<string, any> | null>;
        keyword_statuses: Record<string, { status: string; error_message?: string }>;
        successful_keywords: string[];
        empty_keywords: string[];
        failed_keywords: string[];
      }>('/api/keyword/search', {
        method: 'POST',
        body: JSON.stringify({
          keywords: kws,
          start_date: startDate,
          end_date: endDate,
        }),
      }),
    onSuccess: (res) => {
      if (res.failed_keywords?.length > 0) {
        showError(`${res.failed_keywords.length} 个关键词获取失败，可在表格中查看错误详情`);
      } else {
        showSuccess(`成功获取 ${res.keywords.length} 个词的数据`);
      }
    },
    onError: (err: any) => {
      showError(err.message || '查询失败');
    },
  });

  // 直接生成飞书表格
  const directCreateMutation = useMutation({
    mutationFn: () =>
      fetchJson<{
        success: boolean;
        spreadsheet_title: string;
        spreadsheet_url: string;
        keywords_count: number;
        days_count: number;
      }>('/api/keyword/feishu/direct_create', {
        method: 'POST',
        body: JSON.stringify({
          keywords: selectedWords,
          start_date: startDate,
          end_date: endDate,
          title: directSheetTitle || undefined,
        }),
      }),
    onSuccess: (res) => {
      showSuccess('飞书在线表格生成成功！');
      queryClient.invalidateQueries({ queryKey: ['keywordRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '生成飞书表格失败');
    },
  });

  // 创建定时任务
  const createTaskMutation = useMutation({
    mutationFn: () =>
      fetchJson<{ task_id: number; spreadsheet_url: string }>('/api/keyword/tasks', {
        method: 'POST',
        body: JSON.stringify({
          task_name: taskName,
          keywords: selectedWords,
          update_mode: taskUpdateMode,
          rrule: taskRrule,
          days_range: 90,
        }),
      }),
    onSuccess: () => {
      showSuccess('关键词定时同步任务创建成功！');
      setTaskModalOpen(false);
      queryClient.invalidateQueries({ queryKey: ['keywordTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '创建任务失败');
    },
  });

  // 添加词项
  const handleAddWords = (text: string) => {
    const words = text
      .replace(/[,，]/g, ' ')
      .split(/\s+/)
      .map((w) => w.trim())
      .filter((w) => w.length > 0);
    const set = new Set([...selectedWords, ...words]);
    setSelectedWords(Array.from(set));
    setInputWord('');
  };

  const handleRemoveWord = (word: string) => {
    setSelectedWords((prev) => prev.filter((w) => w !== word));
  };

  const handlePresetDays = (days: number) => {
    const end = new Date(maxAvailDate);
    const start = new Date(end.getTime() - (days - 1) * 86400 * 1000);
    setStartDate(formatDate(start));
    setEndDate(formatDate(end));
  };

  const queryResult = searchMutation.data;

  return (
    <div style={{ maxWidth: '1240px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* 顶部标题区 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>小红书聚光关键词深度洞察</h2>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
            检索搜索指数、广告曝光量、笔记数及市场出价，支持直接生成飞书在线表格或创建滚动定时任务
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <Button
            variant="outline"
            onClick={() => {
              setDirectSheetTitle(`关键词搜索指数监控_${new Date().toISOString().slice(0, 10)}`);
              setDirectSheetOpen(true);
            }}
            disabled={selectedWords.length === 0}
          >
            <FileSpreadsheet size={15} /> 直接生成飞书表
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              setTaskName(`关键词监控任务_${new Date().toISOString().slice(0, 10)}`);
              setTaskModalOpen(true);
            }}
            disabled={selectedWords.length === 0}
          >
            <Clock size={15} /> 创建定时任务
          </Button>
        </div>
      </div>

      {/* 关键词选择与搜索控制卡片 */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '20px', border: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                placeholder="输入关键词（支持空格、逗号分隔多词输入或粘贴）"
                value={inputWord}
                onChange={(e) => setInputWord(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    if (inputWord.trim()) handleAddWords(inputWord);
                  }
                }}
                style={{
                  flex: 1,
                  padding: '9px 14px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '14px',
                  outline: 'none',
                }}
              />
              <Button
                variant="secondary"
                onClick={() => {
                  if (inputWord.trim()) handleAddWords(inputWord);
                }}
              >
                <Plus size={16} /> 添加
              </Button>
            </div>

            {/* 已选关键词 Chips */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', minHeight: '32px' }}>
              {selectedWords.map((w) => (
                <span
                  key={w}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '4px 10px',
                    borderRadius: '9999px',
                    fontSize: '12px',
                    fontWeight: 500,
                    backgroundColor: '#f1f5f9',
                    color: '#334155',
                    border: '1px solid #e2e8f0',
                  }}
                >
                  {w}
                  <button
                    onClick={() => handleRemoveWord(w)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex' }}
                  >
                    <X size={13} />
                  </button>
                </span>
              ))}
              {selectedWords.length > 0 && (
                <button
                  onClick={() => setSelectedWords([])}
                  style={{
                    fontSize: '12px',
                    color: '#94a3b8',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    padding: '4px 8px',
                  }}
                >
                  清空全部
                </button>
              )}
            </div>
          </div>

          {/* 日期选择区 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', minWidth: '320px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                type="date"
                value={startDate}
                max={endDate}
                onChange={(e) => setStartDate(e.target.value)}
                style={{ padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
              />
              <span style={{ color: '#94a3b8' }}>至</span>
              <input
                type="date"
                value={endDate}
                max={formatDate(maxAvailDate)}
                onChange={(e) => setEndDate(e.target.value)}
                style={{ padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
              />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: '6px' }}>
                <Button size="sm" variant="ghost" onClick={() => handlePresetDays(7)}>
                  近7天
                </Button>
                <Button size="sm" variant="ghost" onClick={() => handlePresetDays(30)}>
                  近30天
                </Button>
                <Button size="sm" variant="ghost" onClick={() => handlePresetDays(90)}>
                  近90天
                </Button>
              </div>
              <span style={{ fontSize: '11px', color: '#ea580c', fontWeight: 500 }}>
                {isAfterNoon ? '今日 12:00 起支持 T-1 数据' : '中午 12:00 前最新支持 T-2 数据'}
              </span>
            </div>
          </div>

          <Button
            size="lg"
            variant="primary"
            onClick={() => searchMutation.mutate(selectedWords)}
            loading={searchMutation.isPending}
            disabled={selectedWords.length === 0}
            style={{ height: '42px', padding: '0 20px' }}
          >
            <Search size={16} /> 查询数据
          </Button>
        </div>
      </div>

      {/* 词库分类卡片 (可折叠 / 可拖拽高度) */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', overflow: 'hidden' }}>
        <div
          style={{
            padding: '12px 20px',
            backgroundColor: '#f8fafc',
            borderBottom: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Layers size={16} color="#ea3445" />
            <span style={{ fontSize: '14px', fontWeight: 600, color: '#0f172a' }}>关键词库索引</span>
            <span style={{ fontSize: '12px', color: '#94a3b8' }}>
              共 {libraryData?.counts?.total || 0} 个预置高潜词项
            </span>
          </div>
          <button
            onClick={() => setLibraryCollapsed(!libraryCollapsed)}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: '#64748b',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '12px',
            }}
          >
            {libraryCollapsed ? (
              <>
                展开词库 <ChevronDown size={14} />
              </>
            ) : (
              <>
                收起词库 <ChevronUp size={14} />
              </>
            )}
          </button>
        </div>

        {!libraryCollapsed && (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {/* 一级分类 */}
            <div style={{ display: 'flex', borderBottom: '1px solid #f1f5f9', padding: '0 16px', overflowX: 'auto' }}>
              {['全部', '防晒衣', '冲锋衣', '户外鞋', '速干衣裤', '羽绒服', '背包配件'].map((cat) => {
                const isAct = activeCategory === cat;
                return (
                  <button
                    key={cat}
                    onClick={() => {
                      setActiveCategory(cat);
                      setActiveSubCategory('');
                    }}
                    style={{
                      padding: '10px 14px',
                      fontSize: '13px',
                      fontWeight: isAct ? 600 : 500,
                      color: isAct ? '#ea3445' : '#64748b',
                      borderBottom: isAct ? '2px solid #ea3445' : '2px solid transparent',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {cat}
                  </button>
                );
              })}
            </div>

            {/* 词项平铺区 */}
            <div
              style={{
                height: `${libraryHeight}px`,
                overflowY: 'auto',
                padding: '16px 20px',
                display: 'flex',
                flexWrap: 'wrap',
                gap: '8px',
                alignContent: 'flex-start',
              }}
            >
              {(() => {
                let displayWords: string[] = [];
                if (libraryData) {
                  if (activeCategory === '全部') {
                    displayWords = libraryData.all_keywords.slice(0, 150);
                  } else if (libraryData.categories[activeCategory]) {
                    const subCats = libraryData.categories[activeCategory];
                    Object.values(subCats).forEach((wList) => {
                      displayWords.push(...wList);
                    });
                  }
                }
                return displayWords.map((word) => {
                  const isSelected = selectedWords.includes(word);
                  return (
                    <span
                      key={word}
                      onClick={() => {
                        if (isSelected) handleRemoveWord(word);
                        else setSelectedWords((prev) => [...prev, word]);
                      }}
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        fontSize: '12px',
                        cursor: 'pointer',
                        border: '1px solid ' + (isSelected ? '#ea3445' : '#e2e8f0'),
                        backgroundColor: isSelected ? '#fef2f2' : '#ffffff',
                        color: isSelected ? '#ea3445' : '#475569',
                        transition: 'all 0.1s',
                      }}
                    >
                      {word}
                    </span>
                  );
                });
              })()}
            </div>
          </div>
        )}
      </div>

      {/* 查询结果表格 */}
      {queryResult && (
        <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', overflow: 'hidden' }}>
          <div
            style={{
              padding: '16px 20px',
              borderBottom: '1px solid #e2e8f0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a' }}>
                查询结果 ({queryResult.keywords.length} 关键词，{queryResult.dates.length} 自然日)
              </h3>
              {queryResult.overall_status === 'partial' && (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    backgroundColor: '#fff7ed',
                    color: '#ea580c',
                    fontSize: '12px',
                  }}
                >
                  <AlertTriangle size={13} /> 部分词获取失败，见下表标签
                </span>
              )}
            </div>
            <div style={{ fontSize: '12px', color: '#64748b' }}>
              时间跨度：{queryResult.start_date} ~ {queryResult.end_date}
            </div>
          </div>

          <div style={{ overflowX: 'auto', maxHeight: '600px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
              <thead style={{ position: 'sticky', top: 0, backgroundColor: '#f8fafc', zIndex: 10 }}>
                <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                  <th style={{ padding: '10px 14px', minWidth: '140px', fontWeight: 600, color: '#475569' }}>关键词</th>
                  <th style={{ padding: '10px 14px', minWidth: '100px', fontWeight: 600, color: '#475569' }}>状态</th>
                  {queryResult.dates.map((d) => (
                    <th
                      key={d}
                      colSpan={4}
                      style={{
                        padding: '8px 12px',
                        textAlign: 'center',
                        borderLeft: '1px solid #e2e8f0',
                        fontWeight: 600,
                        color: '#0f172a',
                      }}
                    >
                      {d}
                    </th>
                  ))}
                </tr>
                <tr style={{ borderBottom: '1px solid #e2e8f0', backgroundColor: '#f1f5f9', fontSize: '11px', color: '#64748b' }}>
                  <th style={{ padding: '6px 14px' }}></th>
                  <th style={{ padding: '6px 14px' }}></th>
                  {queryResult.dates.map((d) => (
                    <React.Fragment key={d}>
                      <th style={{ padding: '6px 8px', borderLeft: '1px solid #e2e8f0', textAlign: 'right' }}>搜索</th>
                      <th style={{ padding: '6px 8px', textAlign: 'right' }}>曝光</th>
                      <th style={{ padding: '6px 8px', textAlign: 'right' }}>笔记</th>
                      <th style={{ padding: '6px 8px', textAlign: 'right' }}>出价</th>
                    </React.Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {queryResult.keywords.map((kw) => {
                  const kwStatus = queryResult.keyword_statuses[kw]?.status || 'success';
                  const kwData = queryResult.data[kw];

                  return (
                    <tr key={kw} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '12px 14px', fontWeight: 600, color: '#0f172a' }}>{kw}</td>
                      <td style={{ padding: '12px 14px' }}>
                        <StatusBadge
                          status={kwStatus}
                          label={
                            kwStatus === 'success'
                              ? '成功'
                              : kwStatus === 'empty'
                              ? '暂无数据'
                              : '获取失败'
                          }
                        />
                      </td>
                      {queryResult.dates.map((d) => {
                        const dayItem = kwData ? kwData[d] : null;
                        return (
                          <React.Fragment key={d}>
                            <td style={{ padding: '10px 8px', borderLeft: '1px solid #f1f5f9', textAlign: 'right' }}>
                              {dayItem ? dayItem.search_num : '-'}
                            </td>
                            <td style={{ padding: '10px 8px', textAlign: 'right', color: '#64748b' }}>
                              {dayItem ? dayItem.imp_num : '-'}
                            </td>
                            <td style={{ padding: '10px 8px', textAlign: 'right', color: '#64748b' }}>
                              {dayItem ? dayItem.note_num : '-'}
                            </td>
                            <td style={{ padding: '10px 8px', textAlign: 'right', color: '#64748b' }}>
                              {dayItem && dayItem.bid ? `¥${dayItem.bid.toFixed(2)}` : '-'}
                            </td>
                          </React.Fragment>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 直接生成飞书表格弹窗 */}
      <Dialog isOpen={directSheetOpen} onClose={() => setDirectSheetOpen(false)} title="直接生成飞书表格" width="460px">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              表格标题
            </label>
            <input
              type="text"
              value={directSheetTitle}
              onChange={(e) => setDirectSheetTitle(e.target.value)}
              style={{
                width: '100%',
                padding: '9px 12px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '14px',
              }}
            />
          </div>
          <div style={{ fontSize: '13px', color: '#64748b' }}>
            已选 <strong>{selectedWords.length}</strong> 个关键词，时间跨度：{startDate} 至 {endDate}。
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <Button variant="secondary" onClick={() => setDirectSheetOpen(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              loading={directCreateMutation.isPending}
              onClick={() => directCreateMutation.mutate()}
            >
              立即生成
            </Button>
          </div>
          {directCreateMutation.data?.spreadsheet_url && (
            <div
              style={{
                marginTop: '10px',
                padding: '12px',
                backgroundColor: '#f0fdf4',
                border: '1px solid #bbf7d0',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span style={{ fontSize: '13px', color: '#16a34a', fontWeight: 500 }}>飞书表格已生成！</span>
              <a
                href={directCreateMutation.data.spreadsheet_url}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '13px',
                  fontWeight: 600,
                  color: '#16a34a',
                }}
              >
                点击直达表格 <ExternalLink size={14} />
              </a>
            </div>
          )}
        </div>
      </Dialog>

      {/* 创建关键词任务弹窗 */}
      <Dialog isOpen={taskModalOpen} onClose={() => setTaskModalOpen(false)} title="创建关键词监控定时任务" width="460px">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              任务名称
            </label>
            <input
              type="text"
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
              style={{
                width: '100%',
                padding: '9px 12px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '14px',
              }}
            />
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              写入模式
            </label>
            <select
              value={taskUpdateMode}
              onChange={(e) => setTaskUpdateMode(e.target.value)}
              style={{
                width: '100%',
                padding: '9px 12px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '14px',
              }}
            >
              <option value="overwrite">全量滚动覆写 (保持最近90天)</option>
              <option value="append">增量历史累加 (保留旧日期并追加新日期)</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              调度频率 (RRULE)
            </label>
            <select
              value={taskRrule}
              onChange={(e) => setTaskRrule(e.target.value)}
              style={{
                width: '100%',
                padding: '9px 12px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '14px',
              }}
            >
              <option value="FREQ=DAILY;BYHOUR=12;BYMINUTE=30">每天 12:30 执行 (推荐，T-1数据就绪)</option>
              <option value="FREQ=DAILY;BYHOUR=18;BYMINUTE=0">每天 18:00 执行</option>
              <option value="FREQ=DAILY;BYHOUR=9;BYMINUTE=0">每天 09:00 执行 (T-2数据)</option>
            </select>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <Button variant="secondary" onClick={() => setTaskModalOpen(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              loading={createTaskMutation.isPending}
              onClick={() => createTaskMutation.mutate()}
            >
              创建任务
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
};

