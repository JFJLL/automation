import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { fetchJson } from '@/shared/api/client';
import { useToast } from '@/shared/components/Toast';

export function useKeywordSearch(searchApiUrl: string) {
  const { showSuccess, showError } = useToast();
  const [activeSearchedWords, setActiveSearchedWords] = useState<string[]>([]);
  const [queryResult, setQueryResult] = useState<any>(null);

  const searchMutation = useMutation({
    mutationFn: ({ keywords, startDate, endDate }: { keywords: string[]; startDate?: string; endDate?: string }) => {
      const payload: any = { keywords };
      if (startDate) payload.start_date = startDate;
      if (endDate) payload.end_date = endDate;
      return fetchJson<any>(searchApiUrl, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: (res, variables) => {
      setActiveSearchedWords(variables.keywords);
      setQueryResult(res);
      if (res?.failed_keywords?.length > 0) {
        showError(res.failed_keywords.length + ' 个关键词获取失败');
      } else {
        const count = res?.keywords?.length || variables.keywords.length;
        showSuccess('成功检索 ' + count + ' 个关键词数据');
      }
    },
    onError: (err: any) => {
      showError(err.message || '查询失败');
    },
  });

  return {
    searchMutation,
    activeSearchedWords,
    queryResult,
    setQueryResult,
  };
}
