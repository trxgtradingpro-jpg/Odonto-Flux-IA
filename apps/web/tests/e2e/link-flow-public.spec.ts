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
          data: [],
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
    await expect(page.getByText('Assistente de agendamento', { exact: true })).toBeVisible();
    await expect(page.getByPlaceholder('Digite sua mensagem...')).toBeVisible();
    await expect(page.getByRole('button', { name: /Enviar mensagem/i })).toBeVisible();
    await expect(page.getByTestId('booking-summary-mobile-drawer')).toHaveAttribute('data-state', 'closed');
    await expect(page.getByRole('button', { name: /Abrir resumo do atendimento/i })).toBeVisible();

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

    const [hasHorizontalOverflow, pageScrolled] = await page.evaluate(() => {
      const hasX = document.documentElement.scrollWidth > window.innerWidth + 1;
      window.scrollTo(0, 9999);
      return [hasX, window.scrollY > 0];
    });
    expect(hasHorizontalOverflow).toBeFalsy();
    expect(pageScrolled).toBeFalsy();
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

    await expect(page.getByText('Maria Souza')).toBeVisible();
    await page.getByTestId('summary-action-procedure').click();
    await page.getByTestId('summary-select-procedure').selectOption({ label: 'Avaliacao inicial' });
    await page.getByTestId('summary-action-unit').click();
    await page.getByTestId('summary-select-unit').selectOption('unit-1');
    await page.getByTestId('summary-action-preferred_date').click();
    await page.getByTestId('summary-select-preferred_date').selectOption('2026-06-10');
    await page.getByTestId('summary-action-confirmed_slot').click();
    await page.getByTestId('summary-select-confirmed_slot').selectOption({ label: '10/06 09:30' });

    await expect(page.getByText('Unidade principal')).toBeVisible();
    await expect(page.getByText('Avaliacao inicial')).toBeVisible();
    await expect(page.getByText('10/06/2026')).toBeVisible();
    await expect(page.getByText('10/06 09:30')).toBeVisible();
  });
});
