import { expect, test } from '@playwright/test';

const authFile = 'playwright/.auth/user.json';

test.describe('demo branding background', () => {
  test.use({ storageState: authFile });

  test('falls back to the default demo background image in the dashboard shell', async ({ page }) => {
    await page.route('**/api/v1/settings', async (route) => {
      await route.fulfill({
        json: {
          data: [],
        },
      });
    });

    await page.goto('/dashboard', { waitUntil: 'networkidle' });
    await page.waitForSelector('.branded-content-frame', { timeout: 20000 });

    await expect
      .poll(async () => {
        return page.evaluate(() => {
          const frame = document.querySelector('.branded-content-frame');
          if (!frame) return null;
          const styles = window.getComputedStyle(frame);
          return {
            backgroundImage: styles.backgroundImage,
            opacityVar: document.documentElement.style.getPropertyValue('--branded-demo-background-opacity').trim(),
          };
        });
      })
      .toMatchObject({
        backgroundImage: expect.stringContaining('dental-floss-smile-background.png'),
        opacityVar: '0.18',
      });
  });

  test('applies the custom demo background image and opacity from branding settings', async ({ page }) => {
    await page.route('**/api/v1/settings', async (route) => {
      await route.fulfill({
        json: {
          data: [
            {
              id: 'branding-theme',
              key: 'branding.theme',
              value: {
                demo_background_image_url: '/images/whatsapp-chat-background.png',
                demo_background_opacity: 0.63,
              },
              is_secret: false,
            },
          ],
        },
      });
    });

    await page.goto('/dashboard', { waitUntil: 'networkidle' });
    await page.waitForSelector('.branded-content-frame', { timeout: 20000 });

    await expect
      .poll(async () => {
        return page.evaluate(() => {
          const frame = document.querySelector('.branded-content-frame');
          if (!frame) return null;
          const styles = window.getComputedStyle(frame);
          return {
            backgroundImage: styles.backgroundImage,
            opacityVar: document.documentElement.style.getPropertyValue('--branded-demo-background-opacity').trim(),
          };
        });
      })
      .toMatchObject({
        backgroundImage: expect.stringContaining('whatsapp-chat-background.png'),
        opacityVar: '0.63',
      });
  });

  test('accepts uploaded-style data urls for the demo background image', async ({ page }) => {
    const dataUrl =
      'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiI+PHJlY3Qgd2lkdGg9IjE2IiBoZWlnaHQ9IjE2IiBmaWxsPSIjMTBiOTgxIi8+PC9zdmc+';

    await page.route('**/api/v1/settings', async (route) => {
      await route.fulfill({
        json: {
          data: [
            {
              id: 'branding-theme',
              key: 'branding.theme',
              value: {
                demo_background_image_url: dataUrl,
                demo_background_opacity: 0.41,
              },
              is_secret: false,
            },
          ],
        },
      });
    });

    await page.goto('/dashboard', { waitUntil: 'networkidle' });
    await page.waitForSelector('.branded-content-frame', { timeout: 20000 });

    await expect
      .poll(async () => {
        return page.evaluate(() => ({
          backgroundVar: document.documentElement.style.getPropertyValue('--branded-demo-background-image').trim(),
          opacityVar: document.documentElement.style.getPropertyValue('--branded-demo-background-opacity').trim(),
        }));
      })
      .toMatchObject({
        backgroundVar: expect.stringContaining('data:image/svg+xml;base64'),
        opacityVar: '0.41',
      });
  });
});
