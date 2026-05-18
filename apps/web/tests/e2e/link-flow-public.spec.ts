import { expect, test } from '@playwright/test';

const branding = {
  primary_color: '#0f766e',
  secondary_color: '#0ea5a4',
  accent_color: '#f59e0b',
  background_color: '#f2f4f7',
  card_color: '#ffffff',
  text_color: '#1c1917',
  muted_text_color: '#475569',
  border_color: '#d6d3d1',
};

test.describe('public link flow landing', () => {
  test('does not create a session or render CTA when link flow is unavailable', async ({ page }) => {
    let sessionCalls = 0;

    await page.route('**/api/v1/public/booking/tenant-a/sessions', async (route) => {
      sessionCalls += 1;
      await route.fulfill({ status: 503, json: { error: { message: 'unavailable' } } });
    });
    await page.route('**/api/v1/public/booking/tenant-a', async (route) => {
      await route.fulfill({
        json: {
          clinic: { slug: 'tenant-a', name: 'Clínica A', logo_data_url: null },
          branding,
          link_flow: {
            enabled: false,
            operational: false,
            cta_mode: 'whatsapp_redirect',
            headline: 'Agendamento oficial da clínica',
            trust_message: 'Continue pelo canal oficial.',
            button_label: 'Continuar pelo WhatsApp',
            unavailable_message: 'Agendamento por link indisponível no momento.',
          },
        },
      });
    });

    await page.goto('/agendar/tenant-a');

    await expect(page.locator('main').getByText('Agendamento por link indisponível no momento.').first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Continuar pelo WhatsApp/i })).toHaveCount(0);
    expect(sessionCalls).toBe(0);
  });

  test('renders the WhatsApp CTA when backend marks link flow operational', async ({ page }) => {
    await page.route('**/api/v1/public/booking/tenant-a/sessions', async (route) => {
      await route.fulfill({
        json: {
          session_id: '00000000-0000-0000-0000-000000000001',
          expires_at: '2026-06-01T13:00:00Z',
          whatsapp_url: 'https://wa.me/5511999887766?text=CFX%3Atoken',
          clinic: { slug: 'tenant-a', name: 'Clínica A' },
        },
      });
    });
    await page.route('**/api/v1/public/booking/sessions/*/events', async (route) => {
      await route.fulfill({ json: { id: 'evt-1', event_name: 'landing_viewed' } });
    });
    await page.route('**/api/v1/public/booking/tenant-a', async (route) => {
      await route.fulfill({
        json: {
          clinic: { slug: 'tenant-a', name: 'Clínica A', logo_data_url: null },
          branding,
          link_flow: {
            enabled: true,
            operational: true,
            cta_mode: 'whatsapp_redirect',
            headline: 'Agende com a Clínica A',
            trust_message: 'Atendimento oficial pelo WhatsApp.',
            button_label: 'Continuar pelo WhatsApp',
            unavailable_message: null,
          },
        },
      });
    });

    await page.goto('/agendar/tenant-a');

    await expect(page.getByRole('button', { name: /Continuar pelo WhatsApp/i })).toBeVisible();
    await expect(page.getByText('Seu link oficial esta pronto para abrir o WhatsApp da operacao.')).toBeVisible();
  });

  test('renders webchat, sends a message and polls assistant replies', async ({ page }) => {
    let postMessageCalls = 0;

    await page.route('**/api/v1/public/booking/tenant-a/sessions', async (route) => {
      await route.fulfill({
        json: {
          session_id: '00000000-0000-0000-0000-000000000003',
          expires_at: '2026-06-01T13:00:00Z',
          cta_mode: 'webchat',
          whatsapp_url: null,
          public_access_token: 'public-token',
          clinic: { slug: 'tenant-a', name: 'ClÃ­nica A' },
        },
      });
    });
    await page.route('**/api/v1/public/booking/sessions/*/events', async (route) => {
      await route.fulfill({ json: { id: 'evt-webchat', event_name: 'webchat_opened' } });
    });
    await page.route('**/api/v1/public/booking/sessions/*/chat/messages**', async (route) => {
      if (route.request().method() === 'POST') {
        postMessageCalls += 1;
        await route.fulfill({
          json: {
            status: 'accepted',
            message: {
              id: 'msg-patient-1',
              role: 'patient',
              text: 'Quero agendar',
              created_at: '2026-06-01T12:00:00Z',
              status: 'received',
            },
          },
        });
        return;
      }
      await route.fulfill({
        json: {
          data:
            postMessageCalls > 0
              ? [
                  {
                    id: 'msg-patient-1',
                    role: 'patient',
                    text: 'Quero agendar',
                    created_at: '2026-06-01T12:00:00Z',
                    status: 'received',
                  },
                  {
                    id: 'msg-ai-1',
                    role: 'assistant',
                    text: 'Claro, posso ajudar com seu agendamento.',
                    created_at: '2026-06-01T12:00:01Z',
                    status: 'sent',
                  },
                ]
              : [],
        },
      });
    });
    await page.route('**/api/v1/public/booking/tenant-a', async (route) => {
      await route.fulfill({
        json: {
          clinic: { slug: 'tenant-a', name: 'ClÃ­nica A', logo_data_url: null },
          branding,
          link_flow: {
            enabled: true,
            operational: true,
            cta_mode: 'webchat',
            headline: 'Agende com a ClÃ­nica A',
            trust_message: 'Atendimento oficial pela pagina.',
            button_label: 'Iniciar chat',
            unavailable_message: null,
          },
        },
      });
    });

    await page.goto('/agendar/tenant-a');

    await expect(page.getByText('Atendimento online')).toBeVisible();
    await expect(page.getByRole('button', { name: /Continuar pelo WhatsApp/i })).toHaveCount(0);
    await page.getByPlaceholder('Digite sua mensagem...').fill('Quero agendar');
    await page.getByRole('button', { name: /Enviar mensagem/i }).click();

    await expect(page.getByText('Claro, posso ajudar com seu agendamento.')).toBeVisible();
  });

  test('keeps the public webchat layout usable on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    await page.route('**/api/v1/public/booking/tenant-a/sessions', async (route) => {
      await route.fulfill({
        json: {
          session_id: '00000000-0000-0000-0000-000000000004',
          expires_at: '2026-06-01T13:00:00Z',
          cta_mode: 'webchat',
          whatsapp_url: null,
          public_access_token: 'public-token-mobile',
          clinic: { slug: 'tenant-a', name: 'ClÃ­nica A' },
        },
      });
    });
    await page.route('**/api/v1/public/booking/sessions/*/events', async (route) => {
      await route.fulfill({ json: { id: 'evt-webchat-mobile', event_name: 'webchat_opened' } });
    });
    await page.route('**/api/v1/public/booking/sessions/*/chat/messages**', async (route) => {
      await route.fulfill({
        json: {
          data: [],
        },
      });
    });
    await page.route('**/api/v1/public/booking/tenant-a', async (route) => {
      await route.fulfill({
        json: {
          clinic: { slug: 'tenant-a', name: 'ClÃ­nica A', logo_data_url: null },
          branding,
          link_flow: {
            enabled: true,
            operational: true,
            cta_mode: 'webchat',
            headline: 'Agende com a ClÃ­nica A',
            trust_message: 'Atendimento oficial pela pagina.',
            button_label: 'Iniciar chat',
            unavailable_message: null,
          },
        },
      });
    });

    await page.goto('/agendar/tenant-a');

    await expect(page.getByText('Atendimento online')).toBeVisible();
    await expect(page.getByText('Assistente de agendamento', { exact: true })).toBeVisible();
    await expect(page.getByPlaceholder('Digite sua mensagem...')).toBeVisible();
    await expect(page.getByRole('button', { name: /Enviar mensagem/i })).toBeVisible();

    const hasHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    expect(hasHorizontalOverflow).toBeFalsy();
  });
});
