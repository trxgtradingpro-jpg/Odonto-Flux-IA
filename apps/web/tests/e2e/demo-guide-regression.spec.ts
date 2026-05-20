import { expect, test } from "@playwright/test";

const matchingConversationPhone = "5511940431906";
const apiBaseUrl = process.env.PLAYWRIGHT_API_URL || "http://127.0.0.1:8000/api/v1";

test.describe("demo guide regression", () => {
  test("new demo entry does not jump to conversation before WhatsApp step", async ({ page, request }) => {
    const loginResponse = await request.post(`${apiBaseUrl}/auth/login`, {
      data: {
        email: "owner@sorrisosul.com",
        password: "Odonto@123",
      },
    });

    expect(loginResponse.ok()).toBeTruthy();
    const payload = (await loginResponse.json()) as {
      access_token: string;
      refresh_token?: string | null;
    };

    await page.route("**/api/v1/auth/me", async (route) => {
      const response = await route.fetch();
      const data = (await response.json()) as Record<string, unknown>;
      const roles = Array.isArray(data.roles) ? data.roles.map((item) => String(item)) : [];
      if (!roles.includes("demo_client")) {
        roles.push("demo_client");
      }

      await route.fulfill({
        response,
        json: {
          ...data,
          roles,
        },
      });
    });

    await page.addInitScript(
      ({ accessToken, refreshToken, phone }) => {
        window.localStorage.setItem("odontoflux_access_token", accessToken);
        if (typeof refreshToken === "string" && refreshToken.length > 0) {
          window.localStorage.setItem("odontoflux_refresh_token", refreshToken);
        }

        window.sessionStorage.setItem("odontoflux_demo_session_id", `demo-regression-${Date.now()}`);
        window.sessionStorage.setItem("odontoflux_demo_guided_override_enabled", "1");
        window.sessionStorage.setItem("odontoflux_demo_whatsapp_entry_active", "1");
        window.sessionStorage.setItem("odontoflux_demo_whatsapp_stage", "entry");
        window.sessionStorage.setItem("odontoflux_demo_whatsapp_entry_phone", phone);
        window.sessionStorage.setItem("odontoflux_demo_whatsapp_entry_link", "https://wa.me/5511999999999");
        window.sessionStorage.removeItem("odontoflux_demo_whatsapp_tracked_conversation_id");
        window.sessionStorage.removeItem("odontoflux_demo_whatsapp_tracked_patient_id");
        window.sessionStorage.removeItem("odontoflux_demo_whatsapp_started_at");
        window.sessionStorage.removeItem("odontoflux_demo_whatsapp_baseline_appointments");
      },
      {
        accessToken: payload.access_token,
        refreshToken: payload.refresh_token ?? null,
        phone: matchingConversationPhone,
      },
    );

    const demoEntryShortcut = page.locator('[data-demo-entry-shortcut="true"]').first();

    await page.goto("/conversas", { waitUntil: "domcontentloaded" });

    await expect(demoEntryShortcut).toBeVisible({ timeout: 30000 });
    await expect(page.getByText("Nova conversa recebida")).toHaveCount(0);

    await page.waitForTimeout(5000);

    await expect(demoEntryShortcut).toBeVisible();
    await expect(page.getByText("Nova conversa recebida")).toHaveCount(0);
  });

  test("webchat demo entry opens without rendering guide overlays", async ({ page, request }) => {
    const loginResponse = await request.post(`${apiBaseUrl}/auth/login`, {
      data: {
        email: "owner@sorrisosul.com",
        password: "Odonto@123",
      },
    });

    expect(loginResponse.ok()).toBeTruthy();
    const payload = (await loginResponse.json()) as {
      access_token: string;
      refresh_token?: string | null;
    };

    await page.route("**/api/v1/auth/me", async (route) => {
      const response = await route.fetch();
      const data = (await response.json()) as Record<string, unknown>;
      const roles = Array.isArray(data.roles) ? data.roles.map((item) => String(item)) : [];
      if (!roles.includes("demo_client")) {
        roles.push("demo_client");
      }

      await route.fulfill({
        response,
        json: {
          ...data,
          roles,
        },
      });
    });

    await page.addInitScript(
      ({ accessToken, refreshToken }) => {
        window.localStorage.setItem("odontoflux_access_token", accessToken);
        if (typeof refreshToken === "string" && refreshToken.length > 0) {
          window.localStorage.setItem("odontoflux_refresh_token", refreshToken);
        }
        Object.keys(window.localStorage)
          .filter((key) => key.startsWith("clinicflux.link_flow.webchat."))
          .forEach((key) => window.localStorage.removeItem(key));

        window.sessionStorage.setItem("odontoflux_demo_session_id", `demo-webchat-${Date.now()}`);
        window.sessionStorage.setItem("odontoflux_demo_guided_override_enabled", "1");
        window.sessionStorage.setItem("odontoflux_demo_whatsapp_entry_active", "1");
        window.sessionStorage.setItem("odontoflux_demo_whatsapp_stage", "entry");
        window.sessionStorage.setItem("odontoflux_demo_entry_channel", "webchat");
        window.sessionStorage.setItem("odontoflux_demo_public_entry_path", "/agendar/demo-webchat-clinica");
        window.sessionStorage.setItem("odontoflux_demo_entry_target_path", "/conversas");
        window.sessionStorage.removeItem("odontoflux_demo_whatsapp_entry_link");
        window.sessionStorage.removeItem("odontoflux_demo_whatsapp_entry_phone");
        window.sessionStorage.removeItem("odontoflux_demo_whatsapp_tracked_conversation_id");
        window.sessionStorage.removeItem("odontoflux_demo_whatsapp_tracked_patient_id");
        window.sessionStorage.removeItem("odontoflux_demo_whatsapp_started_at");
        window.sessionStorage.removeItem("odontoflux_demo_whatsapp_baseline_appointments");
      },
      {
        accessToken: payload.access_token,
        refreshToken: payload.refresh_token ?? null,
      },
    );

    const demoEntryShortcut = page.locator('[data-demo-entry-shortcut="true"]').first();
    const whatsappQuickFocusButton = page.locator('[data-quick-focus-key="conversas"]').first();

    await page.goto("/conversas", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle");

    await expect(demoEntryShortcut).toBeVisible({ timeout: 30000 });
    await expect(whatsappQuickFocusButton).toBeVisible({ timeout: 30000 });
    await expect(page.getByText("Esta demo ainda nao tem um numero real conectado")).toHaveCount(0);
    await expect(page.locator('[data-demo-webchat-workspace="true"]')).toHaveCount(1, { timeout: 30000 });
    await expect(page.getByText("Teste o webchat publico da demo")).toHaveCount(0);
    await expect(page.getByText("Nova conversa recebida")).toHaveCount(0);
    await expect(page.getByText("A IA entendeu o motivo do contato.")).toHaveCount(0);
    await expect(page.getByText("A IA respondeu com base nos dados reais da clinica.")).toHaveCount(0);
    await expect(page.getByText("Finalize um agendamento para atualizar a agenda ao vivo.")).toHaveCount(0);

    const shortcutBox = await demoEntryShortcut.boundingBox();
    const quickFocusBox = await whatsappQuickFocusButton.boundingBox();
    expect(shortcutBox).not.toBeNull();
    expect(quickFocusBox).not.toBeNull();
    expect((shortcutBox?.x ?? 0) + (shortcutBox?.width ?? 0)).toBeLessThanOrEqual((quickFocusBox?.x ?? 0) + 2);

    const workspace = page.locator('[data-demo-webchat-workspace="true"]').first();
    await expect(workspace).toHaveAttribute("data-demo-webchat-workspace-panel", "whatsapp");

    const workspaceBox = await workspace.boundingBox();
    expect(workspaceBox).not.toBeNull();
    const swipeStartX = (workspaceBox?.x ?? 0) + (workspaceBox?.width ?? 0) * 0.72;
    const swipeEndX = (workspaceBox?.x ?? 0) + (workspaceBox?.width ?? 0) * 0.18;
    const swipeY = (workspaceBox?.y ?? 0) + (workspaceBox?.height ?? 0) * 0.45;

    await page.mouse.move(swipeStartX, swipeY);
    await page.mouse.down();
    await page.mouse.move(swipeEndX, swipeY, { steps: 12 });
    await page.mouse.up();

    await expect(workspace).toHaveAttribute("data-demo-webchat-workspace-panel", "webchat");
    await expect(page.getByText("Abra o webchat da demo para iniciar a simulacao")).toHaveCount(0);
    const embeddedFrame = page.locator("iframe").first();
    await expect(embeddedFrame).toBeVisible({ timeout: 30000 });
    await expect(embeddedFrame).toHaveAttribute("src", /embed=demo-webchat/);
    await expect(embeddedFrame).not.toHaveAttribute("src", /demo-webchat-clinica/);
    const frameBox = await embeddedFrame.boundingBox();
    expect(frameBox).not.toBeNull();
    expect((frameBox?.width ?? 0) > ((page.viewportSize()?.width ?? 0) * 0.8)).toBeTruthy();
    await expect(page.getByText("Teste o webchat publico da demo")).toHaveCount(0);
    await expect(page.getByText("Nova conversa recebida")).toHaveCount(0);
    await expect(page.getByText("A IA entendeu o motivo do contato.")).toHaveCount(0);
    await expect(page.getByText("A IA respondeu com base nos dados reais da clinica.")).toHaveCount(0);
    await expect(page.getByText("Finalize um agendamento para atualizar a agenda ao vivo.")).toHaveCount(0);
    await expect(page.getByText("Voltar para Clínica", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Dashboard" })).not.toBeVisible();

    const webchatFrame = page.frameLocator("iframe").first();
    await expect(webchatFrame.getByText("Agendamento oficial", { exact: true })).toBeVisible();
    await expect(webchatFrame.getByText("Link verificado da clinica", { exact: true })).toBeVisible();
    await expect(webchatFrame.getByRole("complementary").getByText("Canal protegido", { exact: true })).toBeVisible();
    await expect(webchatFrame.getByText("Oi, eu sou a assistente de agendamento.")).toBeVisible();
    await expect(webchatFrame.getByText("Aqui a clinica vai simular um paciente")).toBeVisible();
    await expect(webchatFrame.getByText("Agendamento publico nao encontrado.")).toHaveCount(0);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1))
      .toBeTruthy();

    await page.getByText("Voltar para Clínica", { exact: true }).click();

    await expect(workspace).toHaveAttribute("data-demo-webchat-workspace-panel", "whatsapp");
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
    await expect(page.locator('[data-demo-entry-shortcut="true"]').first()).toBeVisible();
    await expect(page.getByRole("button", { name: /chat do site/i }).first()).toBeVisible();
  });
});
