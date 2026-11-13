import { defineConfig } from 'vitest/config';

// GD3 — môi trường `node` (KHÔNG jsdom): các test chỉ phủ module thuần
// (adapt/client/parseSrt). Test UI sống qua spa_audit (puppeteer) — không
// nhân bản nó trong vitest.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.js'],
  },
});
