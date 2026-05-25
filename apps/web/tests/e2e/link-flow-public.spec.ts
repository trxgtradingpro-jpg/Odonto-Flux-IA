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

const mobileLongMessage =
  'Ate vc esta precisando usar a API do WhatsApp mas nao sabe como fazer kkk imagina as clinicas que recebe varias msgs todo dia';

const emptySummary: {
  session_status: string;
  progress: { complete_count: number; total_count: number };
  status: { label: string; tone: 'success' | 'progress' | 'pending'; appointment_created: boolean };
  fields: {
    patient_name: { value: string | null; complete: boolean; source: string | null };
    email: { value: string | null; complete: boolean; source: string | null };
    birth_date: { value: string | null; complete: boolean; source: string | null };
    unit: { value: string | null; complete: boolean; source: string | null; unit_id: string | null };
    procedure: { value: string | null; complete: boolean; source: string | null };
    preferred_date: { value: string | null; complete: boolean; source: string | null };
    confirmed_slot: { value: string | null; complete: boolean; source: string | null };
  };
  appointment: { id: string | null; starts_at: string | null; confirmation_status: string | null };
  options: {
    units: Array<{ id: string; name: string }>;
    services: Array<{ id: string; name: string }>;
    preferred_dates: Array<{ id: string; date: string; label: string; description?: string | null }>;
    preferred_times: Array<{ id: string; label: string; time?: string | null }>;
  };
} = {
  session_status: 'linked',
  progress: { complete_count: 0, total_count: 6 },
  status: { label: 'Coletando dados', tone: 'pending', appointment_created: false },
  fields: {
    patient_name: { value: null, complete: false, source: null },
    email: { value: null, complete: false, source: null },
    birth_date: { value: null, complete: false, source: null },
    unit: { value: null, complete: false, source: null, unit_id: null },
    procedure: { value: null, complete: false, source: null },
    preferred_date: { value: null, complete: false, source: null },
    confirmed_slot: { value: null, complete: false, source: null },
  },
  appointment: { id: null, starts_at: null, confirmation_status: null },
  options: {
    units: [{ id: 'unit-1', name: 'Unidade principal' }],
    services: [{ id: 'service-1', name: 'Avaliacao inicial' }],
    preferred_dates: [{ id: 'day-1', date: '2026-06-10', label: 'Quarta, 10/06', description: 'A partir de 09:00' }],
    preferred_times: [{ id: 'time-1', label: '10/06 09:30', time: '09:30' }],
  },
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
          clinic: { slug: 'tenant-a', name: 'Clinica A', logo_data_url: null },
          branding,
          link_flow: {
            enabled: false,
            operational: false,
            cta_mode: 'whatsapp_redirect',
            headline: 'Agendamento oficial da clinica',
            trust_message: 'Continue pelo canal oficial.',
            button_label: 'Continuar pelo WhatsApp',
            unavailable_message: 'Agendamento por link indisponivel no momento.',
          },
        },
      });
    });

    await page.goto('/agendar/tenant-a');

    await expect(page.locator('main').getByText('Agendamento por link indisponivel no momento.').first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Continuar pelo WhatsApp/i })).toHaveCount(0);
    expect(sessionCalls).toBe(0);
  });

  test('requires a phone number before releasing the WhatsApp CTA', async ({ page }) => {
    await page.route('**/api/v1/public/booking/tenant-a/sessions', async (route) => {
      await route.fulfill({
        json: {
          session_id: '00000000-0000-0000-0000-000000000001',
          expires_at: '2026-06-01T13:00:00Z',
          cta_mode: 'whatsapp_redirect',
          whatsapp_url: 'https://wa.me/5511999887766?text=CFX%3Atoken',
          public_access_token: null,
          contact_phone: null,
          contact_phone_required: true,
          clinic: { slug: 'tenant-a', name: 'Clinica A' },
        },
      });
    });
    await page.route('**/api/v1/public/booking/sessions/*/contact', async (route) => {
      await route.fulfill({
        json: {
          session_id: '00000000-0000-0000-0000-000000000001',
          contact_phone: '(11) 99999-1111',
          contact_phone_required: false,
        },
      });
    });
    await page.route('**/api/v1/public/booking/sessions/*/events', async (route) => {
      await route.fulfill({ json: { id: 'evt-1', event_name: 'landing_viewed' } });
    });
    await page.route('**/api/v1/public/booking/tenant-a', async (route) => {
      await route.fulfill({
        json: {
          clinic: { slug: 'tenant-a', name: 'Clinica A', logo_data_url: null },
          branding,
          link_flow: {
            enabled: true,
            operational: true,
            cta_mode: 'whatsapp_redirect',
            headline: 'Agende com a Clinica A',
            trust_message: 'Atendimento oficial pelo WhatsApp.',
            button_label: 'Continuar pelo WhatsApp',
            unavailable_message: null,
          },
        },
      });
    });

    await page.goto('/agendar/tenant-a');

    await expect(page.getByText('Antes de continuar, me passe seu celular')).toBeVisible();
    await page.getByPlaceholder('Ex.: (11) 99999-1111').fill('(11) 99999-1111');
    await page.getByRole('button', { name: /Continuar atendimento/i }).click();
    await expect(page.getByRole('button', { name: /Continuar pelo WhatsApp/i })).toBeVisible();
    await expect(page.getByText('WhatsApp oficial do sistema')).toBeVisible();
  });

  test('shows a loading panel while the public webchat session is still bootstrapping', async ({ page }) => {
    await page.route('**/api/v1/public/booking/tenant-a/sessions', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1800));
      await route.fulfill({
        json: {
          session_id: '00000000-0000-0000-0000-000000000016',
          expires_at: '2026-06-01T13:00:00Z',
          cta_mode: 'webchat',
          whatsapp_url: null,
          public_access_token: 'public-token-loading',
          contact_phone: '5511999991111',
          contact_phone_required: false,
          clinic: { slug: 'tenant-a', name: 'Clinica A' },
        },
      });
    });
    await page.route('**/api/v1/public/booking/sessions/*/events', async (route) => {
      await route.fulfill({ json: { id: 'evt-webchat-loading', event_name: 'webchat_opened' } });
    });
    await page.route('**/api/v1/public/booking/sessions/*/summary', async (route) => {
      await route.fulfill({ json: emptySummary });
    });
    await page.route('**/api/v1/public/booking/sessions/*/chat/messages**', async (route) => {
      await route.fulfill({ json: { data: [] } });
    });
    await page.route('**/api/v1/public/booking/tenant-a', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      await route.fulfill({
        json: {
          clinic: { slug: 'tenant-a', name: 'Clinica A', logo_data_url: null },
          branding,
          link_flow: {
            enabled: true,
            operational: true,
            cta_mode: 'webchat',
            headline: 'Agende com a Clinica A',
            trust_message: 'Atendimento oficial pela pagina.',
            button_label: 'Iniciar chat',
            unavailable_message: null,
          },
        },
      });
    });

    await page.goto('/agendar/tenant-a?embed=demo-webchat');

    await expect(page.getByText('Carregando atendimento...')).toBeVisible();
    await expect(page.getByText('Nao foi possivel iniciar o atendimento agora.')).toHaveCount(0);
    await expect(page.getByText('Atendimento online')).toBeVisible();
  });

  test('renders webchat, asks for phone first, sends a message and polls assistant replies', async ({ page }) => {
    let postMessageCalls = 0;

    await page.route('**/api/v1/public/booking/tenant-a/sessions', async (route) => {
      await route.fulfill({
        json: {
          session_id: '00000000-0000-0000-0000-000000000003',
          expires_at: '2026-06-01T13:00:00Z',
          cta_mode: 'webchat',
          whatsapp_url: null,
          public_access_token: 'public-token',
          contact_phone: null,
          contact_phone_required: true,
          clinic: { slug: 'tenant-a', name: 'Clinica A' },
        },
      });
    });
    await page.route('**/api/v1/public/booking/sessions/*/contact', async (route) => {
      await route.fulfill({
        json: {
          session_id: '00000000-0000-0000-0000-000000000003',
          contact_phone: '(11) 98888-7777',
          contact_phone_required: false,
        },
      });
    });
    await page.route('**/api/v1/public/booking/sessions/*/events', async (route) => {
      await route.fulfill({ json: { id: 'evt-webchat', event_name: 'webchat_opened' } });
    });
    await page.route('**/api/v1/public/booking/sessions/*/summary', async (route) => {
      await route.fulfill({ json: emptySummary });
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
          clinic: { slug: 'tenant-a', name: 'Clinica A', logo_data_url: null },
          branding,
          link_flow: {
            enabled: true,
            operational: true,
            cta_mode: 'webchat',
            headline: 'Agende com a Clinica A',
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
    await page.getByPlaceholder('Ex.: (11) 99999-1111').fill('(11) 98888-7777');
    await page.getByRole('button', { name: /Continuar atendimento/i }).click();
    await page.getByPlaceholder('Digite sua mensagem...').fill('Quero agendar');
    await page.getByRole('button', { name: /Enviar mensagem/i }).click();

    await expect(page.getByText('Claro, posso ajudar com seu agendamento.')).toBeVisible();
  });

  test('keeps the public webchat layout usable on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.addInitScript(() => {
      const listeners = new Map<string, Set<() => void>>();
      const viewport = {
        width: window.innerWidth,
        height: window.innerHeight,
        offsetTop: 0,
        offsetLeft: 0,
        pageTop: 0,
        pageLeft: 0,
        scale: 1,
        addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
          const callback =
            typeof listener === 'function' ? listener : () => listener.handleEvent(new Event(type));
          const current = listeners.get(type) ?? new Set<() => void>();
          current.add(callback);
          listeners.set(type, current);
        },
        removeEventListener(type: string, listener: EventListenerOrEventListenerObject) {
          const callback =
            typeof listener === 'function' ? listener : () => listener.handleEvent(new Event(type));
          listeners.get(type)?.forEach((registered) => {
            if (registered === callback) {
              listeners.get(type)?.delete(registered);
            }
          });
        },
        dispatch(type: string) {
          listeners.get(type)?.forEach((listener) => listener());
        },
      };

      Object.defineProperty(window, 'visualViewport', {
        configurable: true,
        value: viewport,
      });

      (window as typeof window & {
        __setVisualViewportHeight?: (height: number) => void;
      }).__setVisualViewportHeight = (height: number) => {
        viewport.height = height;
        viewport.dispatch('resize');
        viewport.dispatch('scroll');
      };
    });

    await page.route('**/api/v1/public/booking/tenant-a/sessions', async (route) => {
      await route.fulfill({
        json: {
          session_id: '00000000-0000-0000-0000-000000000004',
          expires_at: '2026-06-01T13:00:00Z',
          cta_mode: 'webchat',
          whatsapp_url: null,
          public_access_token: 'public-token-mobile',
          contact_phone: '5511999991111',
          contact_phone_required: false,
          clinic: { slug: 'tenant-a', name: 'Clinica A' },
        },
      });
    });
    await page.route('**/api/v1/public/booking/sessions/*/events', async (route) => {
      await route.fulfill({ json: { id: 'evt-webchat-mobile', event_name: 'webchat_opened' } });
    });
    await page.route('**/api/v1/public/booking/sessions/*/summary', async (route) => {
      await route.fulfill({ json: emptySummary });
    });
    await page.route('**/api/v1/public/booking/sessions/*/chat/messages**', async (route) => {
      await route.fulfill({
        json: {
          data: [
            {
              id: 'mobile-long-patient-message',
              role: 'patient',
              text: mobileLongMessage,
              created_at: '2026-05-25T03:55:00Z',
              status: 'sent',
            },
            {
              id: 'mobile-assistant-reply',
              role: 'assistant',
              text: 'Sabe eu sei ne anjo',
              created_at: '2026-05-25T03:59:00Z',
              status: 'sent',
            },
          ],
        },
      });
    });
    await page.route('**/api/v1/public/booking/tenant-a', async (route) => {
      await route.fulfill({
        json: {
          clinic: { slug: 'tenant-a', name: 'Clinica A', logo_data_url: null },
          branding,
          link_flow: {
            enabled: true,
            operational: true,
            cta_mode: 'webchat',
            headline: 'Agende com a Clinica A',
            trust_message: 'Atendimento oficial pela pagina.',
            button_label: 'Iniciar chat',
            unavailable_message: null,
          },
        },
      });
    });

    await page.goto('/agendar/tenant-a');

    const viewportMeta = await page.locator('meta[name="viewport"]').getAttribute('content');
    expect(viewportMeta).toContain('width=device-width');
    expect(viewportMeta).toContain('initial-scale=1');
    expect(viewportMeta).toContain('maximum-scale=1');
    expect(viewportMeta).toMatch(/user-scalable=(no|false|0)/);
    await expect(page.getByText('Atendimento online - canal oficial da clinica')).toBeVisible();
    await expect
      .poll(async () =>
        page.getByTestId('public-webchat-mobile-title').evaluate((node) => getComputedStyle(node).color),
      )
      .toBe('rgb(233, 237, 239)');
    await expect(page.getByPlaceholder('Digite sua mensagem...')).toBeVisible();
    await expect(page.getByRole('button', { name: /Enviar mensagem/i })).toBeVisible();
    await expect(page.getByTestId('booking-summary-mobile-drawer')).toHaveAttribute('data-state', 'closed');
    await expect(page.getByRole('button', { name: /Abrir resumo do atendimento/i })).toBeVisible();
    const longBubble = page.getByTestId('public-webchat-message-bubble').first();
    await expect(longBubble).toContainText(mobileLongMessage);

    const metricsBeforeKeyboard = await longBubble.locator('p').first().evaluate((node) => {
      const range = document.createRange();
      range.selectNodeContents(node);
      const rect = node.getBoundingClientRect();
      const lineCount = Array.from(range.getClientRects()).filter((item) => item.width > 0).length;
      range.detach();
      return { bubbleWidth: node.parentElement?.getBoundingClientRect().width ?? 0, textWidth: rect.width, lineCount };
    });

    const summaryHandle = page.getByTestId('booking-summary-mobile-handle');
    const handleBox = await summaryHandle.boundingBox();
    if (!handleBox) {
      throw new Error('Nao foi possivel localizar a aba do resumo mobile.');
    }

    await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(handleBox.x + handleBox.width / 2 + 140, handleBox.y + handleBox.height / 2, { steps: 12 });
    await page.mouse.up();

    await expect(page.getByTestId('booking-summary-mobile-drawer')).toHaveAttribute('data-state', 'open');
    await page.getByRole('button', { name: /Fechar resumo do atendimento/i }).click();
    await expect(page.getByTestId('booking-summary-mobile-drawer')).toHaveAttribute('data-state', 'closed');

    const messageInput = page.getByPlaceholder('Digite sua mensagem...');
    await messageInput.focus();
    await page.evaluate(() => {
      (
        window as typeof window & {
          __setVisualViewportHeight?: (height: number) => void;
        }
      ).__setVisualViewportHeight?.(520);
    });
    await expect(page.getByRole('button', { name: /Enviar mensagem/i })).toBeVisible();
    await expect
      .poll(async () => {
        const sendButtonBox = await page.getByRole('button', { name: /Enviar mensagem/i }).boundingBox();
        return sendButtonBox ? sendButtonBox.y + sendButtonBox.height : null;
      })
      .toBeLessThanOrEqual(520);
    const metricsAfterKeyboard = await longBubble.locator('p').first().evaluate((node) => {
      const range = document.createRange();
      range.selectNodeContents(node);
      const rect = node.getBoundingClientRect();
      const lineCount = Array.from(range.getClientRects()).filter((item) => item.width > 0).length;
      range.detach();
      return { bubbleWidth: node.parentElement?.getBoundingClientRect().width ?? 0, textWidth: rect.width, lineCount };
    });
    expect(Math.abs(metricsAfterKeyboard.bubbleWidth - metricsBeforeKeyboard.bubbleWidth)).toBeLessThanOrEqual(1);
    expect(Math.abs(metricsAfterKeyboard.textWidth - metricsBeforeKeyboard.textWidth)).toBeLessThanOrEqual(1);
    expect(metricsAfterKeyboard.lineCount).toBe(metricsBeforeKeyboard.lineCount);

    const [hasHorizontalOverflow, pageScrolled] = await page.evaluate(() => {
      const hasX = document.documentElement.scrollWidth > window.innerWidth + 1;
      window.scrollTo(0, 9999);
      return [hasX, window.scrollY > 0];
    });
    expect(hasHorizontalOverflow).toBeFalsy();
    expect(pageScrolled).toBeFalsy();
  });

  test('keeps the demo-embedded webchat shell visible on desktop', async ({ page }) => {
    await page.route('**/api/v1/public/booking/tenant-a/sessions', async (route) => {
      await route.fulfill({
        json: {
          session_id: '00000000-0000-0000-0000-000000000014',
          expires_at: '2026-06-01T13:00:00Z',
          cta_mode: 'webchat',
          whatsapp_url: null,
          public_access_token: 'public-token-embed-desktop',
          contact_phone: '5511999991111',
          contact_phone_required: false,
          clinic: { slug: 'tenant-a', name: 'Clinica A' },
        },
      });
    });
    await page.route('**/api/v1/public/booking/sessions/*/events', async (route) => {
      await route.fulfill({ json: { id: 'evt-webchat-embed-desktop', event_name: 'webchat_opened' } });
    });
    await page.route('**/api/v1/public/booking/sessions/*/summary', async (route) => {
      await route.fulfill({ json: emptySummary });
    });
    await page.route('**/api/v1/public/booking/sessions/*/chat/messages**', async (route) => {
      await route.fulfill({ json: { data: [] } });
    });
    await page.route('**/api/v1/public/booking/tenant-a', async (route) => {
      await route.fulfill({
        json: {
          clinic: { slug: 'tenant-a', name: 'Clinica A', logo_data_url: null },
          branding,
          link_flow: {
            enabled: true,
            operational: true,
            cta_mode: 'webchat',
            headline: 'Agende com a Clinica A',
            trust_message: 'Atendimento oficial pela pagina.',
            button_label: 'Iniciar chat',
            unavailable_message: null,
          },
        },
      });
    });

    await page.goto('/agendar/tenant-a?embed=demo-webchat');

    const desktopSidePanel = page.getByRole('complementary');
    await expect(page.getByText('Agendamento oficial', { exact: true })).toBeVisible();
    await expect(page.getByText('Link verificado da clinica', { exact: true })).toBeVisible();
    await expect(desktopSidePanel.getByText('Canal protegido', { exact: true })).toBeVisible();
    await expect(desktopSidePanel.getByText('Agendamento oficial da clinica')).toBeVisible();
    await expect(page.getByText('Atendimento online')).toBeVisible();
    await expect(page.getByRole('button', { name: /Abrir painel do agendamento oficial/i })).toHaveCount(0);
  });

  test('keeps the demo-embedded webchat side panel toggleable on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    await page.route('**/api/v1/public/booking/tenant-a/sessions', async (route) => {
      await route.fulfill({
        json: {
          session_id: '00000000-0000-0000-0000-000000000015',
          expires_at: '2026-06-01T13:00:00Z',
          cta_mode: 'webchat',
          whatsapp_url: null,
          public_access_token: 'public-token-embed-mobile',
          contact_phone: '5511999991111',
          contact_phone_required: false,
          clinic: { slug: 'tenant-a', name: 'Clinica A' },
        },
      });
    });
    await page.route('**/api/v1/public/booking/sessions/*/events', async (route) => {
      await route.fulfill({ json: { id: 'evt-webchat-embed-mobile', event_name: 'webchat_opened' } });
    });
    await page.route('**/api/v1/public/booking/sessions/*/summary', async (route) => {
      await route.fulfill({ json: emptySummary });
    });
    await page.route('**/api/v1/public/booking/sessions/*/chat/messages**', async (route) => {
      await route.fulfill({ json: { data: [] } });
    });
    await page.route('**/api/v1/public/booking/tenant-a', async (route) => {
      await route.fulfill({
        json: {
          clinic: { slug: 'tenant-a', name: 'Clinica A', logo_data_url: null },
          branding,
          link_flow: {
            enabled: true,
            operational: true,
            cta_mode: 'webchat',
            headline: 'Agende com a Clinica A',
            trust_message: 'Atendimento oficial pela pagina.',
            button_label: 'Iniciar chat',
            unavailable_message: null,
          },
        },
      });
    });

    await page.goto('/agendar/tenant-a?embed=demo-webchat');

    const mobileDrawer = page.getByTestId('booking-summary-mobile-drawer');
    await expect(page.getByText('Agendamento oficial', { exact: true })).toBeVisible();
    await expect(page.getByText('Link verificado da clinica', { exact: true })).toBeVisible();
    await expect(mobileDrawer).toHaveAttribute('data-state', 'closed');
    await expect(page.getByRole('button', { name: /Abrir painel do agendamento oficial/i })).toBeVisible();

    await page.getByRole('button', { name: /Abrir painel do agendamento oficial/i }).click();
    await expect(mobileDrawer).toHaveAttribute('data-state', 'open');
    await expect(mobileDrawer.getByText('Canal protegido', { exact: true })).toBeVisible();
    await expect(mobileDrawer.getByText('Agendamento oficial da clinica')).toBeVisible();

    await page.getByRole('button', { name: /Fechar painel do agendamento oficial/i }).click();
    await expect(mobileDrawer).toHaveAttribute('data-state', 'closed');
  });

  test('shows booking checklist progress and manual save states in the left panel', async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.clear();
    });

    let currentSummary = {
      ...emptySummary,
      progress: { complete_count: 2, total_count: 6 },
      fields: {
        ...emptySummary.fields,
        patient_name: { value: 'Maria Souza', complete: true, source: 'manual' },
        email: { value: 'maria@example.com', complete: true, source: 'manual' },
      },
    };

    await page.route('**/api/v1/public/booking/tenant-a/sessions', async (route) => {
      await route.fulfill({
        json: {
          session_id: '00000000-0000-0000-0000-000000000005',
          expires_at: '2026-06-01T13:00:00Z',
          cta_mode: 'webchat',
          whatsapp_url: null,
          public_access_token: 'public-token-summary',
          contact_phone: '5511999991111',
          contact_phone_required: false,
          clinic: { slug: 'tenant-a', name: 'Clinica A' },
        },
      });
    });
    await page.route('**/api/v1/public/booking/sessions/*/events', async (route) => {
      await route.fulfill({ json: { id: 'evt-webchat-summary', event_name: 'webchat_opened' } });
    });
    await page.route('**/api/v1/public/booking/sessions/*/chat/messages**', async (route) => {
      await route.fulfill({ json: { data: [] } });
    });
    await page.route('**/api/v1/public/booking/sessions/*/summary', async (route) => {
      if (route.request().method() === 'PATCH') {
        currentSummary = {
          ...currentSummary,
          progress: { complete_count: 5, total_count: 6 },
          status: { label: 'Em andamento', tone: 'progress', appointment_created: false },
          fields: {
            ...currentSummary.fields,
            unit: { value: 'Unidade principal', complete: true, source: 'manual', unit_id: 'unit-1' },
            procedure: { value: 'Avaliacao inicial', complete: true, source: 'manual' },
            preferred_date: { value: '2026-06-10', complete: true, source: 'manual' },
            confirmed_slot: { value: '10/06 09:30', complete: true, source: 'manual' },
          },
        };
      }
      await route.fulfill({ json: currentSummary });
    });
    await page.route('**/api/v1/public/booking/tenant-a', async (route) => {
      await route.fulfill({
        json: {
          clinic: { slug: 'tenant-a', name: 'Clinica A', logo_data_url: null },
          branding,
          link_flow: {
            enabled: true,
            operational: true,
            cta_mode: 'webchat',
            headline: 'Agende com a Clinica A',
            trust_message: 'Atendimento oficial pela pagina.',
            button_label: 'Iniciar chat',
            unavailable_message: null,
          },
        },
      });
    });

    await page.goto('/agendar/tenant-a');

    const desktopSummary = page.getByRole('complementary');

    await expect(desktopSummary.getByText('Maria Souza')).toBeVisible();
    await desktopSummary.getByTestId('summary-action-procedure').click();
    await desktopSummary.getByTestId('summary-select-procedure').selectOption({ label: 'Avaliacao inicial' });
    await desktopSummary.getByTestId('summary-action-unit').click();
    await desktopSummary.getByTestId('summary-select-unit').selectOption('unit-1');
    await desktopSummary.getByTestId('summary-action-preferred_date').click();
    await desktopSummary.getByTestId('summary-select-preferred_date').selectOption('2026-06-10');
    await desktopSummary.getByTestId('summary-action-confirmed_slot').click();
    await desktopSummary.getByTestId('summary-select-confirmed_slot').selectOption({ label: '10/06 09:30' });

    await expect(desktopSummary.getByText('Unidade principal')).toBeVisible();
    await expect(desktopSummary.getByText('Avaliacao inicial')).toBeVisible();
    await expect(desktopSummary.getByText('10/06/2026')).toBeVisible();
    await expect(desktopSummary.getByText('10/06 09:30')).toBeVisible();
  });
});
