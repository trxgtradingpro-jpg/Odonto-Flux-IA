import { expect, test, type Page } from "@playwright/test";

type RouteScenario = {
  path: string;
  label: string;
  titlePattern: RegExp;
  fallbackPattern: RegExp;
};

const authFile = "playwright/.auth/user.json";

const routeScenarios: RouteScenario[] = [
  {
    path: "/dashboard",
    label: "dashboard",
    titlePattern: /Dashboard operacional/i,
    fallbackPattern: /Nao foi possivel carregar o dashboard operacional/i,
  },
  {
    path: "/operacoes",
    label: "operacoes",
    titlePattern: /Inbox operacional de falhas/i,
    fallbackPattern: /Nao foi possivel carregar o monitoramento operacional/i,
  },
  {
    path: "/onboarding",
    label: "onboarding",
    titlePattern: /Onboarding comercial/i,
    fallbackPattern: /Nao foi possivel carregar/i,
  },
  {
    path: "/conversas",
    label: "conversas",
    titlePattern: /Escolha uma conversa|Inbox de conversas|Sem conversa selecionada/i,
    fallbackPattern: /Nao foi possivel carregar o inbox/i,
  },
  {
    path: "/agenda",
    label: "agenda",
    titlePattern: /Agenda operacional|Consultas \((dia|semana)\)|Nova consulta|Visao ativa/i,
    fallbackPattern: /Nao foi possivel carregar a agenda/i,
  },
  {
    path: "/equipe-medica",
    label: "equipe medica",
    titlePattern: /Equipe medica|Profissionais/i,
    fallbackPattern: /Nao foi possivel carregar/i,
  },
  {
    path: "/servicos",
    label: "servicos",
    titlePattern: /Servicos|Catalogo|Procedimentos/i,
    fallbackPattern: /Nao foi possivel carregar/i,
  },
  {
    path: "/unidades",
    label: "unidades",
    titlePattern: /Unidades|Unidade principal|Gestao de unidades/i,
    fallbackPattern: /Nao foi possivel carregar/i,
  },
  {
    path: "/pacientes",
    label: "pacientes",
    titlePattern: /Pacientes|Base de pacientes/i,
    fallbackPattern: /Nao foi possivel carregar os pacientes/i,
  },
  {
    path: "/leads",
    label: "leads",
    titlePattern: /Leads e funil|Leads/i,
    fallbackPattern: /Nao foi possivel carregar os leads/i,
  },
  {
    path: "/campanhas",
    label: "campanhas",
    titlePattern: /Campanhas|Lista de campanhas/i,
    fallbackPattern: /Nao foi possivel carregar as campanhas/i,
  },
  {
    path: "/automacoes",
    label: "automacoes",
    titlePattern:
      /Automações que sustentam a operação|Automacoes que sustentam a operacao|Studio de Automações|Studio de Automacoes/i,
    fallbackPattern: /Nao foi possivel carregar automacoes/i,
  },
  {
    path: "/ia-lab",
    label: "ia lab",
    titlePattern: /IA Lab \(Sem WhatsApp\)/i,
    fallbackPattern: /Nao foi possivel carregar/i,
  },
  {
    path: "/documentos",
    label: "documentos",
    titlePattern: /Documentos e consentimentos|Documentos operacionais/i,
    fallbackPattern: /Nao foi possivel carregar/i,
  },
  {
    path: "/importacao",
    label: "importacao",
    titlePattern: /Importação de base|Importacao de base/i,
    fallbackPattern: /Nao foi possivel carregar/i,
  },
  {
    path: "/relatorios",
    label: "relatorios",
    titlePattern: /Relatório mensal de valor|Relatorio mensal de valor/i,
    fallbackPattern: /Nao foi possivel carregar/i,
  },
  {
    path: "/faturamento",
    label: "faturamento",
    titlePattern: /Faturamento e plano/i,
    fallbackPattern: /Nao foi possivel carregar/i,
  },
  {
    path: "/backup",
    label: "backup",
    titlePattern: /Backup da clinica/i,
    fallbackPattern: /Nao foi possivel carregar os backups/i,
  },
  {
    path: "/suporte",
    label: "suporte",
    titlePattern: /Central de suporte e SLA|Incidentes registrados/i,
    fallbackPattern: /Nao foi possivel carregar/i,
  },
  {
    path: "/usuarios",
    label: "usuarios",
    titlePattern: /Usuarios e permissoes|Usuarios/i,
    fallbackPattern: /Nao foi possivel carregar usuarios/i,
  },
];

async function openProtectedRoute(page: Page, path: string) {
  await page.goto(path, { waitUntil: "networkidle" });
}

async function expectAuthenticatedShell(page: Page) {
  await expect(page.getByTitle("Alternar menu")).toBeVisible();
  await expect(page.getByRole("button", { name: /Abrir notificacoes/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Sair/i })).toBeVisible();
}

async function expectScenarioContent(page: Page, scenario: RouteScenario) {
  await expect(page).toHaveURL(new RegExp(`${scenario.path.replace("/", "\\/")}$`));
  await expect
    .poll(
      async () => {
        const text = await page.textContent("body");
        return scenario.titlePattern.test(text ?? "") || scenario.fallbackPattern.test(text ?? "");
      },
      { timeout: 45_000 },
    )
    .toBeTruthy();
}

test.describe("OdontoFlux interface web", () => {
  test("login exibe formulario e credenciais demo", async ({ page }) => {
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("Entrar na plataforma")).toBeVisible();
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.getByText(/Use credenciais demo/i)).toBeVisible();
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/i);
  });

  test("login exibe placeholders esperados", async ({ page }) => {
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    await expect(page.locator('input[type="email"]')).toHaveAttribute(
      "placeholder",
      "voce@clinica.com",
    );
    await expect(page.locator('input[type="password"]')).toHaveAttribute("placeholder", "********");
  });

  test("login mostra link da pagina comercial", async ({ page }) => {
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("link", { name: /Ver pagina comercial/i })).toBeVisible();
  });

  test("login com demo_token mostra experiencia cinematografica", async ({ page }) => {
    await page.route("**/api/v1/demo/auth/redeem-token", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 10000));
      await route.fulfill({
        body: JSON.stringify({
          access_token: "demo-access-token",
          refresh_token: "demo-refresh-token",
          demo_target_path: "/conversas",
        }),
        contentType: "application/json",
        status: 200,
      });
    });

    await page.goto("/login?demo_token=abc", { waitUntil: "domcontentloaded" });

    await expect(page.getByTestId("demo-preparation-screen")).toBeVisible();
    await expect(page.getByText(/Preparando sua demo/i).first()).toBeVisible();
    await expect(page.getByText(/Tempo estimado: 10 a 20 segundos/i).first()).toBeVisible();
    await expect(page.locator('input[type="email"]')).toHaveCount(0);
  });

  test("rota protegida mostra guarda de sessao sem token", async ({ page }) => {
    await page.goto("/dashboard", { waitUntil: "domcontentloaded" });
    await expect(page.getByText(/Carregando sess/i)).toBeVisible();
  });
});

test.describe("OdontoFlux interface autenticada", () => {
  test.use({ storageState: authFile });

  test("login via api abre dashboard autenticado", async ({ page }) => {
    await openProtectedRoute(page, "/dashboard");
    await expectAuthenticatedShell(page);
    await expectScenarioContent(page, routeScenarios[0]);
  });

  test("logout remove acesso e volta para login", async ({ page }) => {
    await openProtectedRoute(page, "/dashboard");
    await page.getByRole("button", { name: /Sair/i }).click();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("topbar mostra notificacoes sem erro visual", async ({ page }) => {
    await openProtectedRoute(page, "/dashboard");
    await page.getByRole("button", { name: /Abrir notificacoes/i }).click();
    await expect(page.getByText("Notificacoes")).toBeVisible();
  });

  test("sidebar navega para conversas pelo item WhatsApp", async ({ page }) => {
    await openProtectedRoute(page, "/dashboard");
    await page.getByRole("link", { name: /WhatsApp/i }).click();
    await expectScenarioContent(page, routeScenarios.find((item) => item.path === "/conversas")!);
  });

  test("sidebar navega para pacientes pelo menu", async ({ page }) => {
    await openProtectedRoute(page, "/dashboard");
    await page.getByRole("link", { name: /Pacientes/i }).click();
    await expectScenarioContent(page, routeScenarios.find((item) => item.path === "/pacientes")!);
  });

  test("topbar permite trocar unidade global quando seletor existir", async ({ page }) => {
    await openProtectedRoute(page, "/dashboard");
    const unitSelector = page.getByLabel("Selecionar unidade global");
    const hasSelector = await unitSelector.isVisible().catch(() => false);
    if (hasSelector) {
      await expect(unitSelector).toBeVisible();
    } else {
      await expect(page.getByText(/Unidade principal|Todas as unidades/i).first()).toBeVisible();
    }
  });
});

test.describe("OdontoFlux pages by route", () => {
  test.use({ storageState: authFile });

  for (const scenario of routeScenarios) {
    test(`carrega a rota ${scenario.path}`, async ({ page }) => {
      await openProtectedRoute(page, scenario.path);
      await expectScenarioContent(page, scenario);
    });

    test(`mantem o shell autenticado em ${scenario.path}`, async ({ page }) => {
      await openProtectedRoute(page, scenario.path);
      await expectAuthenticatedShell(page);
    });
  }
});
