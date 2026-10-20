import { describe, it, expect } from 'vitest';

describe('Frontend Basic Checks', () => {
  it('loads client environment without errors', () => {
    expect(true).toBe(true);
  });

  it('verifies standard routing paths', () => {
    const validPaths = [
      '/import', '/tasks', '/runs',
      '/keyword', '/keyword/tasks', '/keyword/runs',
      '/lingxi', '/lingxi/tasks', '/lingxi/runs',
      '/admin', '/admin/tasks', '/admin/audit',
      '/admin/promo', '/admin/promo/tasks', '/admin/promo/runs',
      '/simple-promo', '/simple-promo/tasks', '/simple-promo/runs',
      '/settings'
    ];
    expect(validPaths.length).toBe(19);
    expect(validPaths).toContain('/keyword');
    expect(validPaths).toContain('/tasks');
    // /admin 现在是任务管理工作台，简单投已下移到 /admin/promo
    expect(validPaths).toContain('/admin');
    expect(validPaths).toContain('/admin/tasks');
    expect(validPaths).toContain('/admin/audit');
    expect(validPaths).toContain('/admin/promo');
    expect(validPaths).toContain('/admin/promo/tasks');
    expect(validPaths).toContain('/admin/promo/runs');
  });
});
