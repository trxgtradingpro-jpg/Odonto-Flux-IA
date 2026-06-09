import { expect, test } from "@playwright/test";

const prospect = {
  id: "prospect-affiliate-contact",
  slug: null,
  clinic_name: "Clinica Amiga",
  affiliate_owner_user_id: null,
  affiliate_owner_user_name: null,
  affiliate_owner_user_email: null,
  affiliate_claimed_at: null,
  created_by_user_id: null,
  created_by_user_name: null,
  created_by_user_email: null,
  created_by_user_is_affiliate: false,
  owner_name: null,
  manager_name: null,
  phone: "+55 11 99999-8888",
  whatsapp_phone: "+55 11 99999-8888",
  email: null,
  website: null,
  city: "Sao Paulo",
  state: "SP",
  main_address: null,
  notes: "",
  lead_source: "google_places",
  first_contact_channel: null,
  first_contact_at: null,
  uses_whatsapp_heavily: true,
  estimated_volume: null,
  main_pain: "Atendimento no WhatsApp",
  score: 72,
  temperature: "quente",
  status: "novo",
  tags: [],
  test_phone_number: null,
  do_not_contact: false,
  demo_tenant_id: null,
  demo_user_id: null,
  demo_login_email: null,
  demo_sent_at: null,
  demo_first_login_at: null,
  demo_last_login_at: null,
  demo_status: "nao_criada",
  demo_expires_at: null,
  demo_booking_path: null,
  demo_checklist: {},
  last_activity_at: null,
  score_explanation: {},
  proposal_snapshot: {},
  roi_inputs: {},
  created_at: "2026-06-09T12:00:00Z",
  updated_at: "2026-06-09T12:00:00Z",
  units: [],
  services: [],
};

const contactMessages = {
  first_messages: Array.from({ length: 5 }, (_, index) => `Mensagem inicial ${index + 1}`),
  second_messages: Array.from({ length: 5 }, (_, index) => `Mensagem de acompanhamento ${index + 1}`),
  third_messages: Array.from({ length: 5 }, (_, index) => `Mensagem depois da resposta ${index + 1}`),
};

test("affiliate selects, edits, accepts the agreement and opens the prepared WhatsApp message", async ({ page }) => {
  let savedMessages = contactMessages;
  let preparePayload: Record<string, unknown> | null = null;

  await page.addInitScript(() => {
    window.localStorage.setItem("odontoflux_adm_access_token", "affiliate-e2e-token");
  });

  await page.route("**/api/v1/admin/auth/me", async (route) => {
    await route.fulfill({
      json: {
        id: "affiliate-user",
        email: "amigo@clinicflux.test",
        full_name: "Amigo da ClinicFlux",
        phone: null,
        roles: ["sales_affiliate"],
        is_active: true,
        force_password_change: false,
        page_permissions: {},
        adm_page_permissions: {},
        is_affiliate: true,
        last_login_at: null,
        created_at: "2026-06-09T12:00:00Z",
        updated_at: "2026-06-09T12:00:00Z",
      },
    });
  });
  await page.route("**/api/v1/admin/prospects/overview", async (route) => {
    await route.fulfill({
      json: {
        total_prospects: 0,
        demos_created: 0,
        demos_accessed: 0,
        hot_leads: 0,
        meetings_scheduled: 0,
        won: 0,
        recent_activity: [],
      },
    });
  });
  await page.route("**/api/v1/admin/outreach/runtime", async (route) => {
    await route.fulfill({
      json: {
        transport: "whatsapp_web_bridge",
        sender_tenant_slug: "sales",
        bridge_enabled: true,
        bridge_configured: true,
        bridge_pending: 0,
        bridge_processing: 0,
        bridge_failed: 0,
        bridge_dead_letter: 0,
        bridge_command: null,
      },
    });
  });
  await page.route("**/api/v1/admin/clinic-messages/templates", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/v1/admin/affiliate-crm/available", async (route) => {
    await route.fulfill({ json: { prospect, available: true } });
  });
  await page.route("**/api/v1/admin/affiliate-crm/mine**", async (route) => {
    await route.fulfill({ json: { data: [], total: 0, limit: 200, offset: 0 } });
  });
  await page.route("**/api/v1/admin/affiliate-crm/contact-messages", async (route) => {
    if (route.request().method() === "PUT") {
      savedMessages = route.request().postDataJSON() as typeof contactMessages;
    }
    await route.fulfill({ json: savedMessages });
  });
  await page.route("**/api/v1/admin/affiliate-crm/prospects/*/prepare-contact", async (route) => {
    preparePayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      json: {
        prospect: {
          ...prospect,
          affiliate_owner_user_id: "affiliate-user",
          affiliate_claimed_at: "2026-06-09T13:00:00Z",
          first_contact_at: "2026-06-09T13:00:00Z",
          status: "contato_iniciado",
        },
        stage: "first",
        message_index: 1,
        destination: prospect.whatsapp_phone,
        message_text: savedMessages.first_messages[1],
        whatsapp_url: "https://api.whatsapp.com/send/?phone=5511999998888&text=Mensagem+inicial+2+editada",
        claimed_now: true,
      },
    });
  });
  await page.route("https://api.whatsapp.com/send/**", async (route) => {
    await route.fulfill({
      contentType: "text/html",
      body: "<html><body>WhatsApp preparado</body></html>",
    });
  });

  await page.goto("/adm", { waitUntil: "domcontentloaded" });

  const startButton = page.getByRole("button", { name: "Enviar primeira mensagem e assumir clinica" });
  await expect(startButton).toBeVisible();
  await startButton.click();

  const selectionDialog = page.getByRole("dialog", { name: "Escolha a mensagem" });
  await expect(selectionDialog).toBeVisible();
  await expect(selectionDialog.getByRole("button", { name: /Segundo contato/ })).toBeDisabled();
  await expect(selectionDialog.getByRole("button", { name: /Terceiro contato/ })).toBeDisabled();

  await selectionDialog.getByRole("button", { name: "Editar mensagens" }).click();
  const editorDialog = page.getByRole("dialog", { name: "Editar suas mensagens" });
  await expect(editorDialog).toBeVisible();
  await editorDialog.getByLabel("Opcao 2").fill("Mensagem inicial 2 editada");
  await editorDialog.getByRole("button", { name: "Salvar as 15 mensagens" }).click();
  await expect(editorDialog).toBeHidden();

  await selectionDialog.getByRole("button", { name: /2 Mensagem inicial 2 editada/ }).click();
  await selectionDialog.getByRole("button", { name: "Continuar" }).click();

  const consentDialog = page.getByRole("dialog", { name: "Um combinado rapido" });
  await expect(consentDialog).toContainText("Guilherme Gomes");
  const confirmButton = consentDialog.getByRole("button", { name: "Confirmar e abrir WhatsApp" });
  await expect(confirmButton).toBeDisabled();

  await consentDialog.getByLabel("Entendo que esta clinica ficara somente na minha carteira.").check();
  await consentDialog.getByLabel("Vou acompanhar este contato com respeito ate concluir ou encerrar.").check();
  await expect(confirmButton).toBeEnabled();
  await page.screenshot({
    path: "tmp-codex-validation/affiliate-contact-consent.png",
    fullPage: true,
  });
  await confirmButton.click();

  await expect.poll(() => preparePayload).not.toBeNull();
  expect(preparePayload).toEqual({
    stage: "first",
    message_index: 1,
    consent_exclusive: true,
    consent_responsible_use: true,
    human_reply_confirmed: false,
  });
  await expect(page).toHaveURL(/api\.whatsapp\.com\/send\/\?phone=5511999998888&text=Mensagem\+inicial\+2\+editada/);
});
