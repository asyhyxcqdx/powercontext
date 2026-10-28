import { resolve } from 'node:path';
process.env.PLAYWRIGHT_BROWSERS_PATH ||= resolve('.cache/browsers');
const { chromium } = await import('playwright');
export const BASE = process.env.APP_URL || 'http://127.0.0.1:8787';
export async function browser(gpu = false) {
  return chromium.launch({ channel: 'chromium', headless: true, args: gpu ? (process.platform === 'linux' ? [
    '--enable-gpu', '--enable-unsafe-webgpu', '--use-angle=vulkan',
    '--enable-features=Vulkan', '--disable-vulkan-surface', '--ignore-gpu-blocklist',
  ] : ['--enable-gpu']) : ['--disable-gpu', '--disable-webgpu'] });
}
export async function pageFor(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  page.setDefaultTimeout(180000);
  page.on('pageerror', error => console.error('PAGE:', error.message));
  page.on('console', message => { if (message.type() === 'error') console.error('CONSOLE:', message.text()); });
  await page.goto(BASE);
  await page.waitForFunction(() => !!window.edgeLibrary);
  return page;
}
