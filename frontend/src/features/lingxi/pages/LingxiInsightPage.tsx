import React, { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Sparkles, Search, X, Tags } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Dialog } from '@/shared/components/Dialog';
import { useToast } from '@/shared/components/Toast';

export const LingxiInsightPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);

  const [inputWord, setInputWord] = useState('');
  const [selectedWords, setSelectedWords] = useState<string[]>(['新生儿奶粉']);

  // 弹窗状态
  const [directSheetOpen, setDirectSheetOpen] = useState(false);
  const [directSheetTitle, setDirectSheetTitle] = useState('');
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [taskName, setTaskName] = useState('');
  const [taskUpdateMode, setTaskUpdateMode] = useState('overwrite');
  const [taskRrule, setTaskRrule] = useState('FREQ=DAILY;BYHOUR=09;BYMINUTE=30');

  // 搜索 Mutation
  const searchMutation = useMutation({
    mutationFn: (kws: string[]) =>
      fetchJson<any>('/api/lingxi/search', {
        method: 'POST',
        body: JSON.stringify({ keywords: kws }),
      }),
    onSuccess: (res) => {
      if (res.data?.failed_keywords?.length > 0) {
        showError(String(res.data.failed_keywords.length) + ' 个关键词获取失败，可在表格中查看错误详情');
      } else {
        const count = res.data?.successful_keywords?.length || selectedWords.length;
        showSuccess('成功检索 ' + count + ' 个关键词数据');
      }
    },
    onError: (err: any) => {
      showError(err.message || '查询失败');
    },
  });

  // 直接建表 Mutation
  const directCreateMutation = useMutation({
    mutationFn: () =>
      fetchJson<any>('/api/lingxi/feishu/direct_create', {
        method: 'POST',
        body: JSON.stringify({
          keywords: selectedWords,
          title: directSheetTitle || undefined,
        }),
      }),
    onSuccess: () => {
      showSuccess('飞书在线表格生成完成！已配置全员可读写。');
      queryClient.invalidateQueries({ queryKey: ['lingxiRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '生成飞书表格失败');
    },
  });

  // 创建定时任务 Mutation
  const createTaskMutation = useMutation({
    mutationFn: async () => {
      // 先创建飞书表格底表
      const sheetRes = await fetchJson<any>('/api/lingxi/feishu/direct_create', {
        method: 'POST',
        body: JSON.stringify({
          keywords: selectedWords,
          title: `${taskName}_底表`,
        }),
      });
      // 再绑定定时同步任务
      return fetchJson<any>('/api/lingxi/tasks', {
        method: 'POST',
        body: JSON.stringify({
          task_name: taskName,
          keywords: selectedWords,
          spreadsheet_token: sheetRes.data.spreadsheet_token,
          spreadsheet_url: sheetRes.data.spreadsheet_url,
          update_mode: taskUpdateMode,
          rrule: taskRrule,
        }),
      });
    },
    onSuccess: () => {
      showSuccess('灵犀定时监控任务创建成功！');
      setTaskModalOpen(false);
      queryClient.invalidateQueries({ queryKey: ['lingxiTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '创建任务失败');
    },
  });

  const handleAddWord = (word: string) => {
    const trimmed = word.trim();
    if (!trimmed) return;
    if (!selectedWords.includes(trimmed)) {
      setSelectedWords([...selectedWords, trimmed]);
    }
    setInputWord('');
  };

  const handleRemoveWord = (word: string) => {
    setSelectedWords(selectedWords.filter((w) => w !== word));
  };

  const queryResult = searchMutation.data?.data;
  const hasFailedKeywords = Boolean(queryResult && queryResult.failed_keywords?.length > 0);

  // 提取智能推荐词列表
  const recommendedKeywords = React.useMemo(() => {
    if (!queryResult?.results) return [];
    const recs: Array<{ keyword: string; user_cnt: number }> = [];
    const seen = new Set(selectedWords);
    Object.values(queryResult.results).forEach((r: any) => {
      (r.recommend_words || []).forEach((rw: any) => {
        if (!seen.has(rw.keyword)) {
          seen.add(rw.keyword);
          recs.push(rw);
        }
      });
    });
    return recs;
  }, [queryResult, selectedWords]);

  return (
    <>
      {/* 页面标题 */}
      <div className="page-heading">
        <div>
          <h2>灵犀关键词洞察</h2>
          <p>查询小红书灵犀平台并集池单关键词即时覆盖人数与智能扩词建议</p>
        </div>
        <span className="platform-badge" style={{ backgroundColor: '#fff1f0', borderColor: '#ffa39e', color: '#cf1322' }}>
          <Sparkles className="icon" size={14} /> 小红书灵犀
        </span>
      </div>

      {/* 搜索卡片 (完全继承聚光一致的卡片风格与栅格) */}
      <div className="card search-card">
        <div className="search-card-head">
          <h3>查询灵犀关键词数据</h3>
          <p>输入一个或多个关键词，自动并集圈选并检索即时覆盖人群体量</p>
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
              {/* 关键词输入框 (与聚光关键词输入框统一结构与等高设计) */}
              <div className="filter-field kw-input-box" style={{ flex: 1 }}>
                <div className="keyword-label-row">
                  <span className="filter-label">搜索关键词</span>
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
                    placeholder="输入关键词，按空格或回车添加多个"
                    autoComplete="off"
                    value={inputWord}
                    onChange={(e) => setInputWord(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === ' ' || e.key === 'Enter') {
                        e.preventDefault();
                        handleAddWord(inputWord);
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

              {/* 查询按钮 */}
              <button
                type="submit"
                className="btn btn-primary search-submit"
                id="btnSearch"
                disabled={selectedWords.length === 0 || searchMutation.isPending}
              >
                <span>{searchMutation.isPending ? '查询中…' : '查询数据'}</span>
              </button>
            </div>

            {/* 已选关键词标签展示区 (与聚光关键词保持统一视觉) */}
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
              <span>💡 灵犀关键词无日期维度，直接统计当前即时人群覆盖人数；点击下方智能推荐词亦可快速加入。</span>
            </div>
          </form>
        </div>
      </div>

      {/* 智能推荐词卡片 */}
      {recommendedKeywords.length > 0 && (
        <div className="card empty-insight keyword-library" style={{ marginBottom: '20px' }}>
          <div className="library-head">
            <div>
              <h3>灵犀智能推荐词池</h3>
              <p>小红书灵犀算法根据已选词智能推荐的高热度关联词，点击即可快捷添加至查询清单。</p>
            </div>
          </div>
          <div className="library-keywords" style={{ maxHeight: '180px', overflowY: 'auto' }}>
            {recommendedKeywords.map((rw) => (
              <button
                key={rw.keyword}
                type="button"
                className="library-keyword"
                onClick={() => handleAddWord(rw.keyword)}
                title={`覆盖人数: ${rw.user_cnt.toLocaleString()} 人`}
              >
                <span>{rw.keyword}</span>
                <span className="cat-count" style={{ marginLeft: '4px', opacity: 0.8 }}>
                  {rw.user_cnt.toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 查询结果卡片 (完全复用聚光一致的 result-card 样式) */}
      {queryResult && (
        <div className="card result-card" id="resultCard" style={{ animation: 'uiFadeUp .28s both' }}>
          <div className="result-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div>
              <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#1d2129' }}>
                查询结果 <span style={{ fontSize: '13px', fontWeight: 'normal', color: 'var(--text-muted)' }}>({selectedWords.length} 个关键词，灵犀即时人群池数据)</span>
              </h3>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                disabled={hasFailedKeywords}
                onClick={() => {
                  setDirectSheetTitle(`灵犀关键词覆盖人数_${new Date().toISOString().slice(0, 10)}`);
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
                  setTaskName(`灵犀关键词监控任务_${new Date().toISOString().slice(0, 10)}`);
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
                  <th style={{ minWidth: '220px' }}>关键词</th>
                  <th style={{ minWidth: '120px' }}>状态</th>
                  <th style={{ minWidth: '200px', textAlign: 'right' }}>覆盖人群数量 (即时)</th>
                  <th style={{ minWidth: '200px' }}>说明</th>
                </tr>
              </thead>
              <tbody>
                {selectedWords.map((kw: string) => {
                  const item = queryResult.results?.[kw];
                  const isOk = item?.status === 'success';
                  const cnt = item?.user_cnt;

                  return (
                    <tr key={kw}>
                      <td style={{ fontWeight: 600 }}>{kw}</td>
                      <td>
                        <span className={`badge ${isOk ? 'badge-success' : 'badge-danger'}`}>
                          {isOk ? '成功' : '失败'}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--primary)' }}>
                        {typeof cnt === 'number' ? `${cnt.toLocaleString()} 人` : '-'}
                      </td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>
                        {isOk ? '灵犀并集池即时覆盖' : (item?.message || '获取失败')}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 直接生成飞书表 Dialog */}
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
            写入 <strong>{selectedWords.length}</strong> 个灵犀关键词即时覆盖人数统计。
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

          {directCreateMutation.data?.data?.spreadsheet_url && (
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
                href={directCreateMutation.data.data.spreadsheet_url}
                target="_blank"
                rel="noreferrer"
                style={{
                  color: 'var(--primary)',
                  fontWeight: 600,
                  fontSize: '13px',
                  textDecoration: 'none',
                }}
              >
                打开表格 ↗
              </a>
            </div>
          )}
        </div>
      </Dialog>

      {/* 创建定时任务 Dialog */}
      <Dialog
        isOpen={taskModalOpen}
        onClose={() => setTaskModalOpen(false)}
        title="创建灵犀关键词监控任务"
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
              更新模式
            </label>
            <div style={{ display: 'flex', gap: '20px', marginTop: '6px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="updateMode"
                  value="overwrite"
                  checked={taskUpdateMode === 'overwrite'}
                  onChange={(e) => setTaskUpdateMode(e.target.value)}
                />
                <span>全量覆写 (刷新最新覆盖人数)</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="updateMode"
                  value="append"
                  checked={taskUpdateMode === 'append'}
                  onChange={(e) => setTaskUpdateMode(e.target.value)}
                />
                <span>增量追加 (按天留存历史)</span>
              </label>
            </div>
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>
              调度频率 (RRULE 规则)
            </label>
            <input
              type="text"
              className="form-control"
              value={taskRrule}
              onChange={(e) => setTaskRrule(e.target.value)}
            />
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
              默认每天 09:30 定时抓取并同步至飞书表格
            </div>
          </div>

          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            将为当前 <strong>{selectedWords.length}</strong> 个关键词自动创建并绑定专属飞书表格。
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
              {createTaskMutation.isPending ? '创建中…' : '确认创建任务'}
            </button>
          </div>
        </div>
      </Dialog>
    </>
  );
};
