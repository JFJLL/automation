import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Sparkles, Search, ExternalLink, CalendarPlus, Users, Flame, RefreshCw } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Dialog } from '@/shared/components/Dialog';
import { Button } from '@/shared/components/Button';
import { useToast } from '@/shared/components/Toast';

export const LingxiInsightPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();

  const [inputWord, setInputWord] = useState('');
  const [selectedWords, setSelectedWords] = useState<string[]>(['新生儿奶粉']);

  const [directSheetOpen, setDirectSheetOpen] = useState(false);
  const [directSheetTitle, setDirectSheetTitle] = useState('');
  const [directSheetResult, setDirectSheetResult] = useState<{ url: string; title: string } | null>(null);

  const [createTaskOpen, setCreateTaskOpen] = useState(false);
  const [taskName, setTaskName] = useState('');
  const [taskMode, setTaskMode] = useState('overwrite');
  const [taskRrule, setTaskRrule] = useState('FREQ=DAILY;BYHOUR=9;BYMINUTE=30');

  const { data: searchData, isFetching: isSearching, refetch } = useQuery<{
    results: Record<string, {
      keyword: string;
      status: string;
      message: string;
      user_cnt: number;
      recommend_words: Array<{ keyword: string; user_cnt: number }>;
    }>;
    successful_keywords: string[];
    failed_keywords: string[];
    total: number;
  }>({
    queryKey: ['lingxiSearch', selectedWords],
    queryFn: async () => {
      if (selectedWords.length === 0) return { results: {}, successful_keywords: [], failed_keywords: [], total: 0 };
      const res = await fetchJson<any>('/api/lingxi/search', {
        method: 'POST',
        body: JSON.stringify({ keywords: selectedWords })
      });
      return res.data;
    },
    enabled: selectedWords.length > 0,
    staleTime: 60000,
  });

  const handleAddInput = (e: React.FormEvent) => {
    e.preventDefault();
    const words = inputWord.replace(/,/g, ' ').split(/\s+/).map(w => w.trim()).filter(Boolean);
    if (words.length === 0) return;
    const next = Array.from(new Set([...selectedWords, ...words]));
    setSelectedWords(next);
    setInputWord('');
  };

  const handleRemoveWord = (word: string) => {
    setSelectedWords(selectedWords.filter(w => w !== word));
  };

  const handleAddRecommendWord = (recWord: string) => {
    if (!selectedWords.includes(recWord)) {
      setSelectedWords([...selectedWords, recWord]);
      showSuccess('已添加推荐词: ' + recWord);
    }
  };

  const directCreateMutation = useMutation({
    mutationFn: async () => {
      return fetchJson<any>('/api/lingxi/feishu/direct_create', {
        method: 'POST',
        body: JSON.stringify({
          keywords: selectedWords,
          title: directSheetTitle.trim() || undefined
        })
      });
    },
    onSuccess: (res) => {
      showSuccess('飞书表格创建成功');
      setDirectSheetResult({
        url: res.data.spreadsheet_url,
        title: res.data.title
      });
    },
    onError: (err: any) => {
      showError(err.message || '创建飞书表格失败');
    }
  });

  const createTaskMutation = useMutation({
    mutationFn: async () => {
      const sheetRes = await fetchJson<any>('/api/lingxi/feishu/direct_create', {
        method: 'POST',
        body: JSON.stringify({
          keywords: selectedWords,
          title: taskName.trim() + '_底表'
        })
      });

      return fetchJson<any>('/api/lingxi/tasks', {
        method: 'POST',
        body: JSON.stringify({
          task_name: taskName.trim(),
          keywords: selectedWords,
          spreadsheet_token: sheetRes.data.spreadsheet_token,
          spreadsheet_url: sheetRes.data.spreadsheet_url,
          update_mode: taskMode,
          rrule: taskRrule
        })
      });
    },
    onSuccess: () => {
      showSuccess('定时同步任务创建成功');
      setCreateTaskOpen(false);
      queryClient.invalidateQueries({ queryKey: ['lingxiTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '创建定时任务失败');
    }
  });

  const allRecWords = useMemo(() => {
    if (!searchData?.results) return [];
    const map = new Map<string, number>();
    Object.values(searchData.results).forEach(item => {
      (item.recommend_words || []).forEach(r => {
        if (!selectedWords.includes(r.keyword) && !map.has(r.keyword)) {
          map.set(r.keyword, r.user_cnt);
        }
      });
    });
    return Array.from(map.entries()).map(([keyword, user_cnt]) => ({ keyword, user_cnt }));
  }, [searchData, selectedWords]);

  return (
    <div className="tab-pane active" style={{ padding: '0 4px' }}>
      <div className="section-head" style={{ marginBottom: '16px' }}>
        <div className="section-title">
          <div className="title-icon" style={{ background: '#fef2f2', color: '#ef4444' }}>
            <Sparkles size={20} />
          </div>
          <div>
            <h2>小红书灵犀关键词洞察</h2>
            <div className="section-desc">
              即时分析小红书灵犀平台并集池搜索关键词覆盖人群体量，支持自动生成飞书报表与定时同步。
            </div>
          </div>
        </div>
        <div className="section-actions" style={{ gap: '8px', display: 'flex' }}>
          <Button
            variant="outline"
            onClick={() => {
              setDirectSheetTitle('灵犀搜索词覆盖人数_' + new Date().toLocaleDateString());
              setDirectSheetResult(null);
              setDirectSheetOpen(true);
            }}
            disabled={selectedWords.length === 0}
          >
            <ExternalLink size={15} style={{ marginRight: '6px' }} />
            生成飞书表格
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              setTaskName('灵犀关键词监控_' + new Date().toLocaleDateString());
              setCreateTaskOpen(true);
            }}
            disabled={selectedWords.length === 0}
          >
            <CalendarPlus size={15} style={{ marginRight: '6px' }} />
            保存为定时任务
          </Button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '16px', padding: '16px 20px' }}>
        <form onSubmit={handleAddInput} style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <div style={{ flex: 1, position: 'relative' }}>
            <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
            <input
              type="text"
              className="form-control"
              style={{ paddingLeft: '36px' }}
              placeholder="输入灵犀搜索关键词（支持空格分隔多个词，如：新生儿奶粉 婴儿奶粉推荐）"
              value={inputWord}
              onChange={(e) => setInputWord(e.target.value)}
            />
          </div>
          <Button type="submit" variant="primary" disabled={!inputWord.trim()}>
            添加词项
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => refetch()}
            disabled={isSearching || selectedWords.length === 0}
            title="刷新当前数据"
          >
            <RefreshCw size={15} className={isSearching ? 'animate-spin' : ''} />
          </Button>
        </form>

        {selectedWords.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '14px', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', color: '#64748b', fontWeight: 500 }}>已选词项 ({selectedWords.length})：</span>
            {selectedWords.map((kw) => (
              <span
                key={kw}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '4px 10px',
                  borderRadius: '20px',
                  backgroundColor: '#fee2e2',
                  color: '#991b1b',
                  fontSize: '12px',
                  fontWeight: 500
                }}
              >
                {kw}
                <button
                  type="button"
                  onClick={() => handleRemoveWord(kw)}
                  style={{
                    border: 'none',
                    background: 'transparent',
                    cursor: 'pointer',
                    color: '#dc2626',
                    padding: 0,
                    display: 'flex',
                    alignItems: 'center'
                  }}
                >
                  ×
                </button>
              </span>
            ))}
            <button
              type="button"
              onClick={() => setSelectedWords([])}
              style={{
                border: 'none',
                background: 'transparent',
                color: '#94a3b8',
                fontSize: '12px',
                cursor: 'pointer',
                marginLeft: '8px',
                textDecoration: 'underline'
              }}
            >
              清空全部
            </button>
          </div>
        )}
      </div>

      <div className="card" style={{ padding: '0', overflow: 'hidden', marginBottom: '20px' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '14px', color: '#1e293b' }}>
            <Users size={16} style={{ color: '#ef4444' }} />
            <span>单关键词覆盖人群数（灵犀实时人群池统计）</span>
          </div>
          {isSearching && (
            <span style={{ fontSize: '12px', color: '#64748b' }}>正在查询数据中...</span>
          )}
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table className="table" style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                <th style={{ padding: '12px 20px', fontSize: '13px', color: '#475569', fontWeight: 600, width: '40%' }}>搜索关键词</th>
                <th style={{ padding: '12px 20px', fontSize: '13px', color: '#475569', fontWeight: 600, width: '35%' }}>覆盖人群数量 (实时)</th>
                <th style={{ padding: '12px 20px', fontSize: '13px', color: '#475569', fontWeight: 600, width: '25%' }}>状态</th>
              </tr>
            </thead>
            <tbody>
              {selectedWords.length === 0 ? (
                <tr>
                  <td colSpan={3} style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
                    暂无查询关键词，请在上方输入框添加关键词
                  </td>
                </tr>
              ) : (
                selectedWords.map((kw) => {
                  const item = searchData?.results?.[kw];
                  const isOk = item?.status === 'success';
                  const cnt = item?.user_cnt;

                  return (
                    <tr key={kw} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '12px 20px', fontWeight: 500, color: '#1e293b' }}>
                        {kw}
                      </td>
                      <td style={{ padding: '12px 20px', fontSize: '14px', fontWeight: 600, color: '#ef4444' }}>
                        {isSearching && item === undefined ? (
                          <span style={{ color: '#94a3b8', fontWeight: 400 }}>加载中...</span>
                        ) : typeof cnt === 'number' ? (
                          cnt.toLocaleString() + ' 人'
                        ) : (
                          '-'
                        )}
                      </td>
                      <td style={{ padding: '12px 20px' }}>
                        {isSearching && item === undefined ? (
                          <span className="badge badge-gray">查询中</span>
                        ) : isOk ? (
                          <span className="badge badge-success">正常</span>
                        ) : (
                          <span className="badge badge-danger">{item?.message || '获取失败'}</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {allRecWords.length > 0 && (
        <div className="card" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px', fontWeight: 600, fontSize: '14px', color: '#1e293b' }}>
            <Flame size={16} style={{ color: '#f59e0b' }} />
            <span>灵犀智能推荐关联搜索词（点击即可快速添加）</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {allRecWords.slice(0, 30).map((rw) => (
              <button
                key={rw.keyword}
                type="button"
                onClick={() => handleAddRecommendWord(rw.keyword)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 12px',
                  borderRadius: '16px',
                  border: '1px solid #e2e8f0',
                  background: '#ffffff',
                  fontSize: '12px',
                  color: '#334155',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
              >
                <span>{rw.keyword}</span>
                <span style={{ fontSize: '11px', color: '#94a3b8' }}>{rw.user_cnt.toLocaleString()}人</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <Dialog
        isOpen={directSheetOpen}
        onClose={() => setDirectSheetOpen(false)}
        title="一键生成飞书在线表格 (灵犀关键词)"
        width="480px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {directSheetResult ? (
            <div style={{ padding: '16px', backgroundColor: '#f0fdf4', borderRadius: '8px', border: '1px solid #bbf7d0', textAlign: 'center' }}>
              <h3 style={{ fontSize: '15px', color: '#166534', marginBottom: '8px', fontWeight: 600 }}>飞书在线表格生成成功！</h3>
              <p style={{ fontSize: '13px', color: '#15803d', marginBottom: '14px' }}>{directSheetResult.title}</p>
              <a
                href={directSheetResult.url}
                target="_blank"
                rel="noreferrer"
                className="btn btn-primary"
                style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', textDecoration: 'none' }}
              >
                <ExternalLink size={16} />
                立即前往飞书查看表格
              </a>
            </div>
          ) : (
            <>
              <div>
                <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
                  表格标题
                </label>
                <input
                  type="text"
                  className="form-control"
                  placeholder="默认使用时间戳命名"
                  value={directSheetTitle}
                  onChange={(e) => setDirectSheetTitle(e.target.value)}
                />
              </div>
              <div style={{ fontSize: '13px', color: '#64748b' }}>
                将包含当前选中的 <strong>{selectedWords.length}</strong> 个关键词及其即时覆盖人数统计。
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
                <Button variant="outline" onClick={() => setDirectSheetOpen(false)}>取消</Button>
                <Button
                  variant="primary"
                  onClick={() => directCreateMutation.mutate()}
                  disabled={directCreateMutation.isPending}
                >
                  {directCreateMutation.isPending ? '正在创建表格...' : '立即生成'}
                </Button>
              </div>
            </>
          )}
        </div>
      </Dialog>

      <Dialog
        isOpen={createTaskOpen}
        onClose={() => setCreateTaskOpen(false)}
        title="创建灵犀关键词定时监控任务"
        width="500px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              任务名称
            </label>
            <input
              type="text"
              className="form-control"
              placeholder="如：灵犀核心搜索词日更监控"
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
            />
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              写入模式
            </label>
            <div style={{ display: 'flex', gap: '16px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="taskMode"
                  value="overwrite"
                  checked={taskMode === 'overwrite'}
                  onChange={() => setTaskMode('overwrite')}
                />
                <span>覆盖原表（每日刷新最新人群数）</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="taskMode"
                  value="append"
                  checked={taskMode === 'append'}
                  onChange={() => setTaskMode('append')}
                />
                <span>历史追加（保留历史每天的人群数量趋势）</span>
              </label>
            </div>
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              执行周期 (RRULE)
            </label>
            <input
              type="text"
              className="form-control"
              placeholder="FREQ=DAILY;BYHOUR=9;BYMINUTE=30"
              value={taskRrule}
              onChange={(e) => setTaskRrule(e.target.value)}
            />
            <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px' }}>
              默认每天 09:30 自动执行一次并更新飞书表格
            </div>
          </div>

          <div style={{ fontSize: '13px', color: '#64748b' }}>
            将为选中的 <strong>{selectedWords.length}</strong> 个词项自动创建对应的飞书底表并配置定时调度。
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
            <Button variant="outline" onClick={() => setCreateTaskOpen(false)}>取消</Button>
            <Button
              variant="primary"
              onClick={() => createTaskMutation.mutate()}
              disabled={createTaskMutation.isPending || !taskName.trim()}
            >
              {createTaskMutation.isPending ? '正在创建...' : '确认创建任务'}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
};

