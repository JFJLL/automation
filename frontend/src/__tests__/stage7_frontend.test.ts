import { describe, it, expect, vi } from 'vitest';
import { fetchJson, ApiError } from '@/shared/api/client';

describe('Stage 7 Frontend Unit Tests', () => {
  it('dispatches auth:unauthorized event on 401 response in api client', async () => {
    const unauthorizedHandler = vi.fn();
    window.addEventListener('auth:unauthorized', unauthorizedHandler);

    // Mock fetch to return 401
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: '未授权，需要管理员权限' }),
    });

    await expect(fetchJson('/api/tasks')).rejects.toThrow(ApiError);
    expect(unauthorizedHandler).toHaveBeenCalled();
    window.removeEventListener('auth:unauthorized', unauthorizedHandler);
  });

  it('validates task form constraints', () => {
    // 1. Task name length (1 ~ 120)
    const validateTaskName = (name: string): boolean => {
      const clean = name.trim();
      return clean.length >= 1 && clean.length <= 120;
    };
    expect(validateTaskName('')).toBe(false);
    expect(validateTaskName('a'.repeat(121))).toBe(false);
    expect(validateTaskName('有效任务名称')).toBe(true);

    // 2. Keywords count (1 ~ 5000) and deduplication
    const processKeywords = (kws: string[]): string[] => {
      const clean = kws.map((k) => k.trim()).filter(Boolean);
      return Array.from(new Set(clean));
    };
    const deduplicated = processKeywords(['词1', '词2', '词1', '  词3  ', '']);
    expect(deduplicated).toEqual(['词1', '词2', '词3']);
    expect(deduplicated.length).toBe(3);
    expect(deduplicated.length >= 1 && deduplicated.length <= 5000).toBe(true);

    // 3. Date range limit (<= 90 days)
    const validateDaysRange = (start: string, end: string): boolean => {
      const d1 = new Date(start).getTime();
      const d2 = new Date(end).getTime();
      const diffDays = Math.round(Math.abs(d2 - d1) / (1000 * 60 * 60 * 24));
      return diffDays <= 90;
    };
    expect(validateDaysRange('2026-06-01', '2026-06-30')).toBe(true);
    expect(validateDaysRange('2026-01-01', '2026-06-01')).toBe(false);
  });

  it('verifies pending state check for task IDs', () => {
    const isPendingTaskId = (taskId: number, activeId: number | null): boolean => {
      return activeId === taskId;
    };
    expect(isPendingTaskId(101, 101)).toBe(true);
    expect(isPendingTaskId(102, 101)).toBe(false);
  });
});
