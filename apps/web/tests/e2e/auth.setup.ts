import fs from 'node:fs/promises';
import path from 'node:path';

import { expect, test as setup } from '@playwright/test';

const authFile = path.resolve(__dirname, '../../playwright/.auth/user.json');
const apiBaseUrl = process.env.PLAYWRIGHT_API_URL || 'http://127.0.0.1:8000/api/v1';

setup('authenticate dashboard session', async ({ request, baseURL }) => {
  const loginResponse = await request.post(`${apiBaseUrl}/auth/login`, {
    data: {
      email: 'owner@sorrisosul.com',
      password: 'Odonto@123',
    },
  });

  expect(loginResponse.ok()).toBeTruthy();
  const payload = (await loginResponse.json()) as {
    access_token: string;
    refresh_token?: string | null;
  };

  await fs.mkdir(path.dirname(authFile), { recursive: true });
  const origin = new URL(baseURL ?? 'http://127.0.0.1:3100').origin;
  const localStorage = [
    { name: 'odontoflux_access_token', value: payload.access_token },
  ];
  if (typeof payload.refresh_token === 'string' && payload.refresh_token.length) {
    localStorage.push({ name: 'odontoflux_refresh_token', value: payload.refresh_token });
  }
  await fs.writeFile(
    authFile,
    JSON.stringify(
      {
        cookies: [],
        origins: [
          {
            origin,
            localStorage,
          },
        ],
      },
      null,
      2,
    ),
    'utf8',
  );
});
