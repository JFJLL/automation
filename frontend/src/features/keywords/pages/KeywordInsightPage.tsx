import React, { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Sparkles, Calendar, Search, X, Clock, Tags, Copy } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Dialog } from '@/shared/components/Dialog';
import { useToast } from '@/shared/components/Toast';

export const KeywordInsightPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);

  const [inputWord, setInputWord] = useState('');
  const [selectedWords, setSelectedWords] = useState<string[]>(['凯乐石']);
  const [activePrimeCategory, setActivePrimeCategory] = useState<string>('全部词库');
  const [activeSubCategory, setActiveSubCategory] = useState<string>('全部');
  const [libraryFilter, setLibraryFilter] = useState('');
  const [isDescending, setIsDescending] = useState(true);

  // 日期范围服务 (Asia/Shanghai)
  const { data: businessTime } = useQuery<{
    timezone: string;
    now: string;
    latest_keyword_date: string;
    is_after_noon: boolean;
  }>({
    queryKey: ['businessTime'],
    queryFn: () => fetchJson('/api/business-time'),
  });

  const maxEndDate = businessTime?.latest_keyword_date || '2026-09-29';
  const [endDate, setEndDate] = useState(maxEndDate);
  const [startDate, setStartDate] = useState(() => {
    const d = new Date(maxEndDate);
    d.setDate(d.getDate() - 89);
    return d.toISOString().split('T')[0];
  });
  const [activePresetPill, setActivePresetPill] = useState<number>(90);

  useEffect(() => {
    if (businessTime?.latest_keyword_date) {
      setEndDate(businessTime.latest_keyword_date);
      const d = new Date(businessTime.latest_keyword_date);
      d.setDate(d.getDate() - 89);
      setStartDate(d.toISOString().split('T')[0]);
    }
  }, [businessTime?.latest_keyword_date]);

  // 词库拖拽多选 (框选)
  const libraryListRef = useRef<HTMLDivElement>(null);
  const dragBoxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = libraryListRef.current;
    if (!container) return;

    let isDown = false;
    let isDragging = false;
    let startX = 0;
    let startY = 0;

    const handleMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return;
      const rect = container.getBoundingClientRect();
      if (e.clientX > rect.right - 14) return;
      isDown = true;
      isDragging = false;
      startX = e.clientX;
      startY = e.clientY;
    };

    const handleMouseMove = (e: MouseEvent) => {
      if (!isDown) return;
      const dx = Math.abs(e.clientX - startX);
      const dy = Math.abs(e.clientY - startY);
      if (!isDragging && (dx > 4 || dy > 4)) {
        isDragging = true;
      }
      if (isDragging && dragBoxRef.current) {
        e.preventDefault();
        const left = Math.min(e.clientX, startX);
        const top = Math.min(e.clientY, startY);
        const width = Math.abs(e.clientX - startX);
        const height = Math.abs(e.clientY - startY);

        const box = dragBoxRef.current;
        box.style.left = left + 'px';
        box.style.top = top + 'px';
        box.style.width = width + 'px';
        box.style.height = height + 'px';
        box.style.display = 'block';

        const keywords = container.querySelectorAll('.library-keyword');
        keywords.forEach((kw) => {
          const r = kw.getBoundingClientRect();
          const intersects = !(
            r.right < left ||
            r.left > left + width ||
            r.bottom < top ||
            r.top > top + height
          );
          kw.classList.toggle('drag-hover', intersects);
        });
      }
    };

    const handleMouseUp = (e: MouseEvent) => {
      if (!isDown) return;
      isDown = false;
      if (dragBoxRef.current) {
        dragBoxRef.current.style.display = 'none';
      }
      if (isDragging) {
        isDragging = false;
        const keywords = container.querySelectorAll('.library-keyword');
        const toAdd: string[] = [];
        keywords.forEach((kw) => {
          if (kw.classList.contains('drag-hover')) {
            kw.classList.remove('drag-hover');
            const word = kw.getAttribute('data-keyword') || kw.textContent?.trim();
            if (word) {
              toAdd.push(word);
            }
          }
        });
        if (toAdd.length > 0) {
          setSelectedWords((prev) => Array.from(new Set([...prev, ...toAdd])));
        }
        window.addEventListener(
          'click',
          (ev) => {
            ev.stopPropagation();
          },
          { capture: true, once: true }
        );
      }
    };

    container.addEventListener('mousedown', handleMouseDown);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      container.removeEventListener('mousedown', handleMouseDown);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // 词库高度拖拽
  const [libraryHeight, setLibraryHeight] = useState<number>(() => {
    return parseInt(localStorage.getItem('kw_lib_height') || '260', 10);
  });
  const isDraggingHeight = useRef(false);
  const startDragY = useRef(0);
  const startHeight = useRef(0);

  const handlePointerDownResize = (e: React.PointerEvent) => {
    isDraggingHeight.current = true;
    startDragY.current = e.clientY;
    startHeight.current = libraryHeight;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const handlePointerMoveResize = (e: React.PointerEvent) => {
    if (!isDraggingHeight.current) return;
    const delta = e.clientY - startDragY.current;
    const newH = Math.max(160, Math.min(650, startHeight.current + delta));
    setLibraryHeight(newH);
    localStorage.setItem('kw_lib_height', String(newH));
  };
  const handlePointerUpResize = (e: React.PointerEvent) => {
    isDraggingHeight.current = false;
    try { (e.target as HTMLElement).releasePointerCapture(e.pointerId); } catch {}
  };

  // 弹窗状态
  const [directSheetOpen, setDirectSheetOpen] = useState(false);
  const [directSheetTitle, setDirectSheetTitle] = useState('');
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [taskName, setTaskName] = useState('');
  const [taskUpdateMode, setTaskUpdateMode] = useState('overwrite');
  const [taskRrule, setTaskRrule] = useState('FREQ=DAILY;BYHOUR=12;BYMINUTE=30');

  // 获取词库
  const { data: libraryData } = useQuery<{
    categories: Record<string, Record<string, string[]>>;
    counts: Record<string, any>;
    all_keywords: string[];
  }>({
    queryKey: ['keywordLibrary'],
    queryFn: () => fetchJson('/api/keyword/library'),
    staleTime: 5 * 60 * 1000,
  });

  // 搜索接口
  const searchMutation = useMutation({
    mutationFn: (kws: string[]) =>
      fetchJson<any>('/api/keyword/search', {
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
        showSuccess(`成功检索 ${res.keywords.length} 个关键词数据`);
      }
    },
    onError: (err: any) => {
      showError(err.message || '查询失败');
    },
  });

  // 直接建表
  const directCreateMutation = useMutation({
    mutationFn: () =>
      fetchJson<any>('/api/keyword/feishu/direct_create', {
        method: 'POST',
        body: JSON.stringify({
          keywords: selectedWords,
          start_date: startDate,
          end_date: endDate,
          title: directSheetTitle || undefined,
        }),
      }),
    onSuccess: () => {
      showSuccess('飞书在线表格生成完成！已配置全员可读写。');
      queryClient.invalidateQueries({ queryKey: ['keywordRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '生成飞书表格失败');
    },
  });

  // 创建定时任务
  const createTaskMutation = useMutation({
    mutationFn: () =>
      fetchJson<any>('/api/keyword/tasks', {
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
      showSuccess('关键词定时监控任务创建成功！');
      setTaskModalOpen(false);
      queryClient.invalidateQueries({ queryKey: ['keywordTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '创建任务失败');
    },
  });

  const handleAddWordString = (text: string) => {
    const words = text
      .replace(/[,，\n]/g, ' ')
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

  const handleToggleWord = (word: string) => {
    if (selectedWords.includes(word)) {
      handleRemoveWord(word);
    } else {
      setSelectedWords((prev) => [...prev, word]);
    }
  };

  // 严格限制日期间隔不超过90天并弹出Toast提示与自动纠偏
  const validateAndSetDateRange = (newStart: string, newEnd: string, changedField: 'start' | 'end') => {
    if (!newStart || !newEnd) {
      if (changedField === 'start') setStartDate(newStart);
      else setEndDate(newEnd);
      return false;
    }
    const s = new Date(newStart);
    const e = new Date(newEnd);
    const maxE = new Date(maxEndDate);

    if (e > maxE) {
      showError(`中午12:00前最多支持查询至 ${maxEndDate} (T-2)`);
      setEndDate(maxEndDate);
      return false;
    }
    if (s > e) {
      showError('开始日期不能大于结束日期');
      if (changedField === 'start') {
        setStartDate(newEnd);
      } else {
        setEndDate(newStart);
      }
      return false;
    }
    const daysDiff = Math.round((e.getTime() - s.getTime()) / (1000 * 3600 * 24)) + 1;
    if (daysDiff > 90) {
      showError('查询日期间隔不超过90天');
      if (changedField === 'start') {
        const clampedStart = new Date(e.getTime() - 89 * 86400 * 1000);
        setStartDate(clampedStart.toISOString().split('T')[0]);
      } else {
        const clampedEnd = new Date(s.getTime() + 89 * 86400 * 1000);
        const finalEnd = clampedEnd > maxE ? maxE : clampedEnd;
        setEndDate(finalEnd.toISOString().split('T')[0]);
      }
      return false;
    }

    setStartDate(newStart);
    setEndDate(newEnd);
    if (daysDiff === 7) setActivePresetPill(7);
    else if (daysDiff === 30) setActivePresetPill(30);
    else if (daysDiff === 90) setActivePresetPill(90);
    else setActivePresetPill(0);
    return true;
  };

  const handlePresetDays = (days: number) => {
    setActivePresetPill(days);
    const end = new Date(maxEndDate);
    const start = new Date(end.getTime() - (days - 1) * 86400 * 1000);
    setStartDate(start.toISOString().split('T')[0]);
    setEndDate(end.toISOString().split('T')[0]);
  };

  // 词库大类与细类
  const primeCategories = ['全部词库', '防晒衣', '冲锋衣', '户外鞋', '速干衣裤', '羽绒服', '背包配件'];
  const activeGroup = activePrimeCategory !== '全部词库' && libraryData?.categories[activePrimeCategory];
  const subCategories = activeGroup ? ['全部', ...Object.keys(activeGroup)] : ['全部'];

  const displayKeywords = React.useMemo(() => {
    if (!libraryData) return [];
    let words: string[] = [];
    if (activePrimeCategory === '全部词库') {
      words = libraryData.all_keywords || [];
    } else if (libraryData.categories[activePrimeCategory]) {
      const subCats = libraryData.categories[activePrimeCategory];
      if (activeSubCategory && activeSubCategory !== '全部' && subCats[activeSubCategory]) {
        words = subCats[activeSubCategory];
      } else {
        Object.values(subCats).forEach((wList) => {
          words.push(...wList);
        });
      }
    }

    if (libraryFilter.trim()) {
      const q = libraryFilter.trim().toLowerCase();
      words = words.filter((w) => w.toLowerCase().includes(q));
    }
    return Array.from(new Set(words));
  }, [libraryData, activePrimeCategory, activeSubCategory, libraryFilter]);

  const queryResult = searchMutation.data;
  const sortedDates = React.useMemo(() => {
    if (!queryResult?.dates) return [];
    return isDescending ? [...queryResult.dates].reverse() : queryResult.dates;
  }, [queryResult?.dates, isDescending]);

  const hasFailedKeywords = Boolean(queryResult && queryResult.failed_keywords?.length > 0);

  // 复制表格数据到剪贴板 (TSV格式直接无缝粘贴到 Excel)
  const handleCopyTableData = () => {
    if (!queryResult || !queryResult.keywords?.length) return;
    const row1 = ['关键词', '状态'];
    sortedDates.forEach((d: string) => {
      row1.push(d, '', '', '');
    });
    const row2 = ['', ''];
    sortedDates.forEach(() => {
      row2.push('搜索指数', '广告曝光量', '广告笔记数', '平均市场出价');
    });

    const lines: string[] = [row1.join('\t'), row2.join('\t')];

    queryResult.keywords.forEach((kw: string) => {
      const statusInfo = queryResult.keyword_statuses[kw] || { status: 'success' };
      const kwStatus = statusInfo.status === 'success' ? '成功' : statusInfo.status === 'empty' ? '暂无数据' : '获取失败';
      const kwData = queryResult.data[kw];
      const isFailed = statusInfo.status !== 'success' && statusInfo.status !== 'empty';

      const row = [kw, kwStatus];
      sortedDates.forEach((d: string) => {
        const item = kwData ? kwData[d] : null;
        if (isFailed) {
          row.push('-', '-', '-', '-');
        } else {
          row.push(
            item ? String(item.search_num ?? 0) : '0',
            item ? String(item.imp_num ?? 0) : '0',
            item ? String(item.note_num ?? 0) : '0',
            item && item.bid !== undefined ? String(Number(item.bid).toFixed(2)) : '0.00'
          );
        }
      });
      lines.push(row.join('\t'));
    });

    const tsvContent = lines.join('\r\n');
    navigator.clipboard
      .writeText(tsvContent)
      .then(() => {
        showSuccess('📋 表格内容已复制到剪贴板，可直接在 Excel 中粘贴 (Ctrl+V)！');
      })
      .catch((err) => {
        showError('复制失败，请手动复制: ' + err.message);
      });
  };

  return (
    <>
      {/* 框选矩形浮层 */}
      <div
        ref={dragBoxRef}
        id="dragSelectionBox"
        style={{
          position: 'fixed',
          border: '1.5px dashed var(--primary)',
          background: 'rgba(239, 43, 58, 0.12)',
          pointerEvents: 'none',
          zIndex: 9999,
          display: 'none',
          borderRadius: '4px',
        }}
      />
      {/* 页面标题 */}
      <div className="page-heading">
        <div>
          <h2>关键词洞察</h2>
          <p>查询小红书关键词热度与投放数据，辅助选词和预算决策</p>
        </div>
        <span className="platform-badge">
          <Sparkles className="icon" size={14} /> 小红书聚光
        </span>
      </div>

      {/* 原版搜索卡片 */}
      <div className="card search-card">
        <div className="search-card-head">
          <h3>查询关键词数据</h3>
          <p>选择时间范围并输入一个或多个关键词</p>
        </div>
        <div className="search-card-body">
          <form
            id="searchForm"
            onSubmit={(e) => {
              e.preventDefault();
              if (selectedWords.length > 0) searchMutation.mutate(selectedWords);
            }}
          >
            <div className="search-flex-row">
              {/* 时间选择器 (统一胶囊容器 + 快捷分段Pill，高度统一 38px) */}
              <div className="filter-field">
                <span className="filter-label">
                  时间范围
                  <span style={{ fontSize: '12px', fontWeight: 'normal', color: 'var(--text-muted)', marginLeft: '6px' }}>
                    (中午12:00起支持T-1)
                  </span>
                </span>
                <div className="date-picker-box">
                  <div className="date-range-capsule">
                    <span className="date-icon">
                      <Calendar className="icon" size={14} />
                    </span>
                    <input
                      type="date"
                      id="startDate"
                      className="date-input"
                      value={startDate}
                      max={endDate}
                      onChange={(e) => validateAndSetDateRange(e.target.value, endDate, 'start')}
                    />
                    <span className="date-separator">至</span>
                    <input
                      type="date"
                      id="endDate"
                      className="date-input"
                      value={endDate}
                      max={maxEndDate}
                      onChange={(e) => validateAndSetDateRange(startDate, e.target.value, 'end')}
                    />
                  </div>
                  <div className="pill-segmented ms-1">
                    <button
                      type="button"
                      className={`pill-btn ${activePresetPill === 7 ? 'active' : ''}`}
                      onClick={() => handlePresetDays(7)}
                    >
                      近7天
                    </button>
                    <button
                      type="button"
                      className={`pill-btn ${activePresetPill === 30 ? 'active' : ''}`}
                      onClick={() => handlePresetDays(30)}
                    >
                      近30天
                    </button>
                    <button
                      type="button"
                      className={`pill-btn ${activePresetPill === 90 ? 'active' : ''}`}
                      id="pill90"
                      onClick={() => handlePresetDays(90)}
                    >
                      近90天
                    </button>
                  </div>
                </div>
              </div>

              {/* 关键词输入框 (高度统一 38px，与时间选择器等高整齐) */}
              <div className="filter-field kw-input-box">
                <div className="keyword-label-row">
                  <span className="filter-label">关键词</span>
                  <span className="search-selected-count" style={{ color: 'var(--primary)', fontWeight: 600, fontSize: '12px' }}>
                    已选 {selectedWords.length} 个
                  </span>
                </div>
                <div
                  className="keyword-search-editor"
                  id="keywordSearchEditor"
                  onClick={() => inputRef.current?.focus()}
                >
                  <span className="search-icon">
                    <Search className="icon" size={14} />
                  </span>
                  <input
                    ref={inputRef}
                    type="text"
                    id="keywordInput"
                    className="form-control-custom"
                    placeholder="输入关键词，按空格或回车添加"
                    autoComplete="off"
                    value={inputWord}
                    onChange={(e) => setInputWord(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        if (inputWord.trim()) handleAddWordString(inputWord);
                      }
                    }}
                    onPaste={(e) => {
                      const text = e.clipboardData.getData('text');
                      if (text && (text.includes(' ') || text.includes(',') || text.includes('\n'))) {
                        e.preventDefault();
                        handleAddWordString(text);
                      }
                    }}
                  />
                  {selectedWords.length > 0 && (
                    <button
                      type="button"
                      className="keyword-clear-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedWords([]);
                      }}
                      aria-label="清空已选关键词"
                    >
                      <X size={12} className="icon" />
                      <span>清空</span>
                    </button>
                  )}
                </div>
              </div>

              {/* 查询按钮 (高度统一 38px，基线对齐) */}
              <button
                type="submit"
                className="btn btn-primary search-submit"
                id="btnSearch"
                disabled={selectedWords.length === 0 || searchMutation.isPending}
              >
                <span>{searchMutation.isPending ? '查询中…' : '查询数据'}</span>
              </button>
            </div>

            {/* 已选关键词展示区域 (自动换行，带滚动条与清空，不破坏上方38px控件对齐) */}
            {selectedWords.length > 0 && (
              <div
                id="selectedKeywordsBar"
                style={{
                  marginTop: '12px',
                  padding: '10px 14px',
                  background: '#fff7f7',
                  border: '1px solid #ffd6de',
                  borderRadius: '8px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span style={{ fontSize: '13px', fontWeight: 600, color: '#4e5969', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Tags className="icon" size={14} color="var(--primary)" />
                    <span>已选关键词 (<strong style={{ color: 'var(--primary)' }}>{selectedWords.length}</strong>)</span>
                  </span>
                  <button
                    type="button"
                    className="keyword-clear-btn"
                    onClick={() => setSelectedWords([])}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      border: '1px solid var(--border)',
                      background: '#fff',
                      fontSize: '12px',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                    }}
                  >
                    <X size={12} className="icon" />
                    <span>清空全部</span>
                  </button>
                </div>
                <div
                  className="search-selected-list"
                  style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', maxHeight: '120px', overflowY: 'auto', paddingRight: '4px' }}
                >
                  {selectedWords.map((word) => (
                    <span key={word} className="selected-chip">
                      <span>{word}</span>
                      <span className="remove-btn" onClick={() => handleRemoveWord(word)}>
                        ✕
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="input-hint-text" style={{ marginTop: '10px' }}>
              <span>💡 可在下方关键词库中直接选择，也可以在输入框自定义添加；已选关键词会显示为可删除标签。</span>
            </div>
          </form>
        </div>
      </div>

      {/* 原版关键词库卡片 */}
      <div className="card empty-insight keyword-library" id="searchEmptyState">
        <div className="library-head">
          <div>
            <h3>关键词库</h3>
            <p>先选择大类，再按细类筛选关键词；点击即可添加，也支持自定义输入。</p>
          </div>
          <div className="library-search">
            <Search className="icon" size={14} />
            <input
              id="libraryFilterInput"
              className="form-control-custom"
              type="search"
              placeholder="筛选关键词"
              value={libraryFilter}
              onChange={(e) => setLibraryFilter(e.target.value)}
            />
          </div>
        </div>
        <div className="library-taxonomy">
          <div className="taxonomy-row">
            <span className="taxonomy-label">大类</span>
            <div className="library-categories" id="keywordPrimaryTabs">
              {primeCategories.map((cat) => {
                const count =
                  cat === '全部词库'
                    ? (libraryData?.counts?.total || 205)
                    : (libraryData?.counts?.[cat]?.['_total'] || 0);
                return (
                  <button
                    key={cat}
                    type="button"
                    className={`category-btn primary-category-btn${activePrimeCategory === cat ? ' active' : ''}`}
                    onClick={() => {
                      setActivePrimeCategory(cat);
                      setActiveSubCategory('全部');
                    }}
                  >
                    {cat} {count}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="taxonomy-row">
            <span className="taxonomy-label">细类</span>
            <div className="library-categories" id="keywordSecondaryTabs">
              {subCategories.map((sub) => {
                const subCount =
                  sub === '全部'
                    ? displayKeywords.length
                    : (activeGroup && typeof activeGroup === 'object' && sub in activeGroup ? (activeGroup[sub]?.length || 0) : 0);
                return (
                  <button
                    key={sub}
                    type="button"
                    className={`category-btn${activeSubCategory === sub ? ' active' : ''}`}
                    onClick={() => setActiveSubCategory(sub)}
                  >
                    {sub} {subCount}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
        <div
          ref={libraryListRef}
          className="library-keywords"
          id="keywordLibraryList"
          style={{ height: `${libraryHeight}px`, overflowY: 'auto' }}
        >
          {displayKeywords.map((word) => {
            const isSelected = selectedWords.includes(word);
            return (
              <button
                key={word}
                type="button"
                data-keyword={word}
                className={`library-keyword${isSelected ? ' selected' : ''}`}
                onClick={() => handleToggleWord(word)}
              >
                {word}
              </button>
            );
          })}
        </div>
        <div
          className="library-resize-bar"
          id="libraryResizeBar"
          title="上下拖拽可调整词库列表高度"
          onPointerDown={handlePointerDownResize}
          onPointerMove={handlePointerMoveResize}
          onPointerUp={handlePointerUpResize}
        >
          <div className="library-resize-handle-grip" />
        </div>
      </div>

      {/* 原版查询结果卡片 */}
      {queryResult && (
        <div className="card result-card" id="resultCard" style={{ animation: 'uiFadeUp .28s both' }}>
          <div className="result-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div>
              <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#1d2129' }}>
                查询结果 <span style={{ fontSize: '13px', fontWeight: 'normal', color: 'var(--text-muted)' }}>({queryResult.keywords.length} 关键词，{queryResult.dates.length} 自然日)</span>
              </h3>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={handleCopyTableData}
                title="复制表格内容，可直接在 Excel 中按 Ctrl+V 粘贴"
              >
                <Copy size={13} style={{ marginRight: '4px' }} /> 复制表格数据
              </button>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={() => setIsDescending(!isDescending)}
              >
                <span>{isDescending ? '📅 最新在前 (降序)' : '📅 最早在前 (升序)'}</span>
              </button>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                disabled={hasFailedKeywords}
                onClick={() => {
                  setDirectSheetTitle(`关键词搜索指数监控_${new Date().toISOString().slice(0, 10)}`);
                  setDirectSheetOpen(true);
                }}
              >
                直接生成飞书表
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={hasFailedKeywords}
                onClick={() => {
                  setTaskName(`关键词监控任务_${new Date().toISOString().slice(0, 10)}`);
                  setTaskModalOpen(true);
                }}
              >
                创建定时任务
              </button>
            </div>
          </div>

          <div className="table-scroll-wrap" style={{ overflowX: 'auto', maxHeight: '550px' }}>
            <table className="custom-grid">
              <thead>
                <tr>
                  <th style={{ minWidth: '140px' }}>关键词</th>
                  <th style={{ minWidth: '100px' }}>状态</th>
                  {sortedDates.map((d: string) => (
                    <th key={d} colSpan={4} style={{ textAlign: 'center', borderLeft: '1px solid var(--border)' }}>
                      {d}
                    </th>
                  ))}
                </tr>
                <tr style={{ background: '#fdfbfa', fontSize: '11px', color: 'var(--text-muted)' }}>
                  <th></th>
                  <th></th>
                  {sortedDates.map((d: string) => (
                    <React.Fragment key={d}>
                      <th style={{ textAlign: 'right', borderLeft: '1px solid var(--border)' }}>搜索</th>
                      <th style={{ textAlign: 'right' }}>曝光</th>
                      <th style={{ textAlign: 'right' }}>笔记</th>
                      <th style={{ textAlign: 'right' }}>出价</th>
                    </React.Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {queryResult.keywords.map((kw: string) => {
                  const statusInfo = queryResult.keyword_statuses[kw] || { status: 'success' };
                  const kwStatus = statusInfo.status;
                  const kwData = queryResult.data[kw];
                  const isFailed = kwStatus !== 'success' && kwStatus !== 'empty';

                  return (
                    <tr key={kw}>
                      <td style={{ fontWeight: 600 }}>{kw}</td>
                      <td>
                        <span
                          className={`badge ${
                            kwStatus === 'success'
                              ? 'badge-success'
                              : kwStatus === 'empty'
                              ? 'badge-gray'
                              : 'badge-danger'
                          }`}
                        >
                          {kwStatus === 'success' ? '成功' : kwStatus === 'empty' ? '暂无数据' : '获取失败'}
                        </span>
                      </td>
                      {sortedDates.map((d: string) => {
                        const dayItem = kwData ? kwData[d] : null;
                        return (
                          <React.Fragment key={d}>
                            <td style={{ textAlign: 'right', borderLeft: '1px solid var(--border)' }}>
                              {isFailed ? '-' : (dayItem ? dayItem.search_num : 0)}
                            </td>
                            <td style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>
                              {isFailed ? '-' : (dayItem ? dayItem.imp_num : 0)}
                            </td>
                            <td style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>
                              {isFailed ? '-' : (dayItem ? dayItem.note_num : 0)}
                            </td>
                            <td style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>
                              {isFailed ? '-' : (dayItem && dayItem.bid ? `¥${Number(dayItem.bid).toFixed(2)}` : '¥0.00')}
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

      {/* 原版直接生成飞书表 Dialog */}
      <Dialog
        isOpen={directSheetOpen}
        onClose={() => setDirectSheetOpen(false)}
        title="直接生成飞书表格"
        width="460px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>
              表格标题
            </label>
            <input
              type="text"
              className="form-control"
              value={directSheetTitle}
              onChange={(e) => setDirectSheetTitle(e.target.value)}
            />
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            写入 <strong>{selectedWords.length}</strong> 个关键词，时间跨度：{startDate} 至 {endDate}。
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button className="btn btn-outline" type="button" onClick={() => setDirectSheetOpen(false)}>
              取消
            </button>
            <button
              className="btn btn-primary"
              type="button"
              disabled={directCreateMutation.isPending || !directSheetTitle.trim()}
              onClick={() => directCreateMutation.mutate()}
            >
              {directCreateMutation.isPending ? '生成中…' : '立即生成'}
            </button>
          </div>

          {directCreateMutation.data?.spreadsheet_url && (
            <div
              style={{
                marginTop: '10px',
                padding: '12px',
                background: '#e8ffea',
                border: '1px solid #b7eb8f',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span style={{ fontSize: '13px', color: '#00b42a', fontWeight: 500 }}>飞书在线表格已生成！</span>
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
                  color: '#00b42a',
                }}
              >
                打开飞书表格 ↗
              </a>
            </div>
          )}
        </div>
      </Dialog>

      {/* 原版创建定时任务 Dialog */}
      <Dialog
        isOpen={taskModalOpen}
        onClose={() => setTaskModalOpen(false)}
        title="创建关键词监控定时任务"
        width="460px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>
              任务名称
            </label>
            <input
              type="text"
              className="form-control"
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
            />
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>
              写入模式
            </label>
            <select
              className="form-control"
              value={taskUpdateMode}
              onChange={(e) => setTaskUpdateMode(e.target.value)}
            >
              <option value="overwrite">全量滚动覆写 (保持最近90天滚动)</option>
              <option value="append">增量历史累加 (保留历史旧日期并右侧追加新日期)</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>
              调度频率 (RRULE)
            </label>
            <select
              className="form-control"
              value={taskRrule}
              onChange={(e) => setTaskRrule(e.target.value)}
            >
              <option value="FREQ=DAILY;BYHOUR=12;BYMINUTE=30">每天 12:30 执行 (推荐，T-1数据就绪)</option>
              <option value="FREQ=DAILY;BYHOUR=18;BYMINUTE=0">每天 18:00 执行</option>
              <option value="FREQ=DAILY;BYHOUR=9;BYMINUTE=0">每天 09:00 执行 (T-2数据)</option>
            </select>
          </div>

          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            将监控当前选中的 <strong>{selectedWords.length}</strong> 个关键词。
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button className="btn btn-outline" type="button" onClick={() => setTaskModalOpen(false)}>
              取消
            </button>
            <button
              className="btn btn-primary"
              type="button"
              disabled={createTaskMutation.isPending || !taskName.trim()}
              onClick={() => createTaskMutation.mutate()}
            >
              {createTaskMutation.isPending ? '创建中…' : '确认创建'}
            </button>
          </div>
        </div>
      </Dialog>
    </>
  );
};

