import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { FileSpreadsheet, Clock } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Button } from '@/shared/components/Button';
import { useToast } from '@/shared/components/Toast';
import { KeywordSearchBar } from '../components/KeywordSearchBar';
import { KeywordLibrary } from '../components/KeywordLibrary';
import { KeywordResultTable } from '../components/KeywordResultTable';
import { DirectSheetDialog } from '../components/DirectSheetDialog';
import { CreateKeywordTaskDialog } from '../components/CreateKeywordTaskDialog';

export const KeywordInsightPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();

  const [inputWord, setInputWord] = useState('');
  const [selectedWords, setSelectedWords] = useState<string[]>(['凯乐石']);

  // 获取业务基准时区时间 (Section 二十八)
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
  const isAfterNoon = businessTime?.is_after_noon ?? true;

  const [endDate, setEndDate] = useState(maxEndDate);
  const [startDate, setStartDate] = useState(() => {
    const d = new Date(maxEndDate);
    d.setDate(d.getDate() - 29);
    return d.toISOString().split('T')[0];
  });

  useEffect(() => {
    if (businessTime?.latest_keyword_date) {
      setEndDate(businessTime.latest_keyword_date);
      const d = new Date(businessTime.latest_keyword_date);
      d.setDate(d.getDate() - 29);
      setStartDate(d.toISOString().split('T')[0]);
    }
  }, [businessTime?.latest_keyword_date]);

  // 弹窗状态
  const [directSheetOpen, setDirectSheetOpen] = useState(false);
  const [directSheetTitle, setDirectSheetTitle] = useState('');
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [taskName, setTaskName] = useState('');
  const [taskUpdateMode, setTaskUpdateMode] = useState('overwrite');
  const [taskRrule, setTaskRrule] = useState('FREQ=DAILY;BYHOUR=12;BYMINUTE=30');

  // 词库查询
  const { data: libraryData } = useQuery<{
    categories: Record<string, Record<string, string[]>>;
    counts: Record<string, any>;
    all_keywords: string[];
  }>({
    queryKey: ['keywordLibrary'],
    queryFn: () => fetchJson('/api/keyword/library'),
    staleTime: 5 * 60 * 1000,
  });

  // 关键词检索
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
        showError(`${res.failed_keywords.length} 个关键词抓取失败，请检查或点击“仅重试失败关键词”`);
      } else {
        showSuccess(`成功检索 ${res.keywords.length} 个关键词的官方真实指标`);
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

  const handleAddWords = (text: string) => {
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

  const handlePresetDays = (days: number) => {
    const end = new Date(maxEndDate);
    const start = new Date(end.getTime() - (days - 1) * 86400 * 1000);
    setStartDate(start.toISOString().split('T')[0]);
    setEndDate(end.toISOString().split('T')[0]);
  };

  const queryResult = searchMutation.data;
  const hasFailedKeywords = Boolean(queryResult && queryResult.failed_keywords?.length > 0);

  return (
    <div style={{ maxWidth: '1240px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* 顶部标题区 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>小红书聚光关键词深度洞察</h2>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
            分析搜索指数、广告曝光量、笔记数及市场出价，直接生成飞书在线表格或创建滚动定时任务
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <Button
            variant="outline"
            onClick={() => {
              setDirectSheetTitle(`关键词搜索指数监控_${new Date().toISOString().slice(0, 10)}`);
              setDirectSheetOpen(true);
            }}
            disabled={selectedWords.length === 0 || hasFailedKeywords}
            title={hasFailedKeywords ? '存在失败关键词，请重试或移除后再生成' : ''}
          >
            <FileSpreadsheet size={15} /> 直接生成飞书表
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              setTaskName(`关键词监控任务_${new Date().toISOString().slice(0, 10)}`);
              setTaskModalOpen(true);
            }}
            disabled={selectedWords.length === 0 || hasFailedKeywords}
            title={hasFailedKeywords ? '存在失败关键词，请重试或移除后再创建任务' : ''}
          >
            <Clock size={15} /> 创建定时任务
          </Button>
        </div>
      </div>

      {/* 搜索与日期控制栏 */}
      <KeywordSearchBar
        inputWord={inputWord}
        setInputWord={setInputWord}
        selectedWords={selectedWords}
        onAddWords={handleAddWords}
        onRemoveWord={handleRemoveWord}
        onClearWords={() => setSelectedWords([])}
        startDate={startDate}
        setStartDate={setStartDate}
        endDate={endDate}
        setEndDate={setEndDate}
        maxEndDate={maxEndDate}
        isAfterNoon={isAfterNoon}
        onPresetDays={handlePresetDays}
        onSearch={() => searchMutation.mutate(selectedWords)}
        isSearching={searchMutation.isPending}
      />

      {/* 词库分类索引 (完整词库、实时筛选、多级子类、高度拖拽与框选) */}
      <KeywordLibrary
        libraryData={libraryData}
        selectedWords={selectedWords}
        onToggleWord={handleToggleWord}
        onSelectMultipleWords={(words) => {
          const set = new Set([...selectedWords, ...words]);
          setSelectedWords(Array.from(set));
          showSuccess(`框选添加了 ${words.length} 个关键词`);
        }}
      />

      {/* 结果表格 (含失败词 - 展示与仅重试失败词功能) */}
      {queryResult && (
        <KeywordResultTable
          queryResult={queryResult}
          isRetrying={searchMutation.isPending}
          onRetryFailed={(failedWords) => {
            searchMutation.mutate(failedWords);
          }}
        />
      )}

      {/* 直接生成飞书表格弹窗 */}
      <DirectSheetDialog
        isOpen={directSheetOpen}
        onClose={() => setDirectSheetOpen(false)}
        title={directSheetTitle}
        setTitle={setDirectSheetTitle}
        keywordsCount={selectedWords.length}
        startDate={startDate}
        endDate={endDate}
        hasFailedKeywords={hasFailedKeywords}
        onSubmit={() => directCreateMutation.mutate()}
        isSubmitting={directCreateMutation.isPending}
        spreadsheetUrl={directCreateMutation.data?.spreadsheet_url}
      />

      {/* 创建关键词任务弹窗 */}
      <CreateKeywordTaskDialog
        isOpen={taskModalOpen}
        onClose={() => setTaskModalOpen(false)}
        taskName={taskName}
        setTaskName={setTaskName}
        updateMode={taskUpdateMode}
        setUpdateMode={setTaskUpdateMode}
        rrule={taskRrule}
        setRrule={setTaskRrule}
        keywordsCount={selectedWords.length}
        hasFailedKeywords={hasFailedKeywords}
        onSubmit={() => createTaskMutation.mutate()}
        isSubmitting={createTaskMutation.isPending}
      />
    </div>
  );
};

