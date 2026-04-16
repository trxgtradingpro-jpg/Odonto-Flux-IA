const { chromium, request } = require("@playwright/test");

const routes = [
  "/dashboard",
  "/onboarding",
  "/conversas",
  "/pacientes",
  "/leads",
  "/agenda",
  "/equipe-medica",
  "/operacoes",
  "/campanhas",
  "/automacoes",
  "/documentos",
  "/importacao",
  "/relatorios",
  "/faturamento",
  "/suporte",
  "/usuarios",
  "/configuracoes",
  "/auditoria",
  "/admin",
];

async function main() {
  const api = await request.newContext({ baseURL: "http://localhost:3000" });
  const login = await api.post("/api/v1/auth/login", {
    data: { email: "owner@sorrisosul.com", password: "Odonto@123" },
  });

  if (!login.ok()) {
    throw new Error("Falha no login para smoke test.");
  }

  const { access_token } = await login.json();
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || "/usr/bin/chromium",
  });
  const page = await browser.newPage({ baseURL: "http://localhost:3000" });

  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.evaluate((token) => {
    localStorage.setItem("odontoflux_access_token", token);
  }, access_token);

  let hasFailure = false;
  for (const route of routes) {
    const response = await page.goto(route, { waitUntil: "networkidle" });
    const status = response ? response.status() : 0;
    const bodyText = (await page.textContent("body")) || "";
    const hasUiError = /Não foi possível|TypeError|Unprocessable Entity|erro ao carregar/i.test(
      bodyText,
    );

    console.log(`${route} -> status ${status} | erro-na-ui: ${hasUiError}`);
    if (status >= 500 || hasUiError) {
      hasFailure = true;
    }
  }

  await browser.close();
  await api.dispose();

  if (hasFailure) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
