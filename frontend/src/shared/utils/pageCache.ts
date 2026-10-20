// -*- coding: utf-8 -*-
/**
 * 内存级页面状态与查询结果缓存 (SPA 内跨板块切换不丢失数据，刷新网页或重新打开后自动清空)
 */

const inMemoryStore: Record<string, any> = {};

export function getPageCache<T>(key: string, defaultValue: T): T {
  if (inMemoryStore[key] !== undefined) {
    return inMemoryStore[key] as T;
  }
  return defaultValue;
}

export function setPageCache<T>(key: string, value: T): void {
  inMemoryStore[key] = value;
}

export function updatePageCache(key: string, partial: Record<string, any>): void {
  inMemoryStore[key] = { ...(inMemoryStore[key] || {}), ...partial };
}

export function clearPageCache(key?: string): void {
  if (key) {
    delete inMemoryStore[key];
  } else {
    for (const k of Object.keys(inMemoryStore)) {
      delete inMemoryStore[k];
    }
  }
}
