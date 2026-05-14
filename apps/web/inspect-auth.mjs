import { chromium, request } from '@playwright/test';

const api = await request.newContext();
const login = await api.post('http://nginx/api/v1/auth/login', { data: { email: 'owner@sorrisosul.com', password: 'Odonto@123' } });
const payload = await login.json();
const browser = await chromium.launch({ executablePath: '/usr/bin/chromium', headless: true });
const page = await browser.newPage();
page.on('console', (msg) => console.log('console', msg.type(), msg.text()));
page.on('pageerror', (err) => console.log('pageerror', err.message));
page.on('requestfailed', (req) => console.log('requestfailed', req.url(), req.failure()?.errorText));
await page.goto('http://nginx/login', { waitUntil: 'domcontentloaded' });
await page.evaluate((token) => window.localStorage.setItem('odontoflux_access_token', token), payload.access_token);
await page.goto('http://nginx/dashboard', { waitUntil: 'load' });
await page.waitForTimeout(10000);
console.log('url', page.url());
console.log('body', (await page.textContent('body'))?.slice(0, 500));
await browser.close();
await api.dispose();
