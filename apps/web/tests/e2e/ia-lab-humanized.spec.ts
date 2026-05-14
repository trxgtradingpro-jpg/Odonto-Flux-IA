import { expect, test, type Page } from "@playwright/test";

const authFile = "playwright/.auth/user.json";
const iaLabUrl = "/ia-lab";
const patientMessagePlaceholder = "Ex.: Oi, quero agendar uma avaliacao para esta semana.";
const extraContextPlaceholder = "Ex.: paciente ja perguntou sobre clareamento e quer horario de manha.";
const editedReplyPlaceholder = "Ajuste aqui a resposta final que voce aprova para este tipo de mensagem.";

const scenarios = [
  {
    name: "agendamento inicial",
    message: "Oi, quero agendar uma avaliacao para esta semana.",
    expected: [/hor[aá]rio|agenda|avalia[cç][aã]o/i],
  },
  {
    name: "preco de clareamento",
    message: "Quanto custa clareamento dental?",
    expected: [/clareamento/i, /avalia[cç][aã]o|valor|caso/i],
  },
  {
    name: "remarcacao",
    message: "Preciso remarcar minha consulta de amanha.",
    expected: [/remarc|novo hor[aá]rio|consulta/i],
  },
  {
    name: "urgencia",
    message: "Estou com dor forte e sangramento, e urgente.",
    expected: [/atendente|equipe|urgente|encaixe/i],
  },
  {
    name: "pedido de humano",
    message: "Quero falar com um atendente humano.",
    expected: [/atendente|equipe|recep[cç][aã]o/i],
  },
  {
    name: "convenio",
    message: "Voces aceitam OdontoPlus?",
    expected: [/odontoplus|convenio|avali/i],
  },
  {
    name: "unidades",
    message: "Quais unidades voces atendem?",
    expected: [/unidade|centro|paulista|zona sul/i],
  },
  {
    name: "horario no fim do dia",
    message: "Pode me mostrar horario amanha depois das 18h na unidade Centro?",
    expected: [/\d{2}:\d{2}/, /unidade centro|hor[aá]rio/i],
  },
  {
    name: "acolhimento consultivo",
    message: "Tenho medo de dentista e queria entender com calma como funciona a avaliacao.",
    expected: [/avalia[cç][aã]o|calma|entender|hor[aá]rio/i],
  },
  {
    name: "retorno",
    message: "Quero agendar um retorno para semana que vem de manha.",
    expected: [/retorno|hor[aá]rio|manh[aã]/i],
  },
];

function normalizeText(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function expectHumanizedReply(reply: string) {
  const normalized = normalizeText(reply);
  const forbiddenMarkers = [
    "perfeito perfeito",
    "otimo otimo",
    "certo certo",
    "claro claro",
    "qualquer duvida, estamos a disposicao",
    "qualquer duvida estamos a disposicao",
    "fico no aguardo",
    "aguardo seu retorno",
    "vou verificar para voce agora",
    " | ",
  ];

  expect(reply.trim().length).toBeGreaterThan(0);
  expect(reply.length).toBeLessThan(700);
  expect(reply).not.toContain("\n\n\n");

  for (const marker of forbiddenMarkers) {
    expect(normalized).not.toContain(marker);
  }

  const lines = reply
    .split("\n")
    .map((line) => normalizeText(line))
    .filter(Boolean);

  for (let index = 1; index < lines.length; index += 1) {
    expect(lines[index]).not.toBe(lines[index - 1]);
  }
}

async function openIaLab(page: Page) {
  await page.goto(iaLabUrl, { waitUntil: "networkidle" });
  await expect(page.getByText("IA Lab (Sem WhatsApp)")).toBeVisible();
}

async function runSimulation(page: Page, message: string, extraContext = "") {
  await openIaLab(page);
  await page.locator(`textarea[placeholder="${patientMessagePlaceholder}"]`).fill(message);
  await page.locator(`textarea[placeholder="${extraContextPlaceholder}"]`).fill(extraContext);
  await page.locator("select").nth(2).selectOption("structured");
  await page.getByRole("button", { name: "Simular resposta IA" }).click();

  const editedResponse = page.locator(`textarea[placeholder="${editedReplyPlaceholder}"]`);
  await expect
    .poll(async () => (await editedResponse.inputValue()).trim(), { timeout: 180_000 })
    .not.toBe("");

  await expect(page.getByText(/Fluxo estruturado validado/i)).toBeVisible();
  await expect(page.getByText(/fluxo: estruturado/i).first()).toBeVisible();
  return editedResponse.inputValue();
}

test.describe("IA Lab humanizado", () => {
  test.use({ storageState: authFile });
  test.describe.configure({ mode: "serial" });

  test("botoes de cenario carregam o texto no editor", async ({ page }) => {
    await openIaLab(page);
    await page.getByRole("button", { name: "Quanto custa clareamento dental?" }).click();
    await expect(page.locator(`textarea[placeholder="${patientMessagePlaceholder}"]`)).toHaveValue(
      "Quanto custa clareamento dental?",
    );
  });

  for (const scenario of scenarios) {
    test(`resposta exibida permanece humana em ${scenario.name}`, async ({ page }) => {
      const reply = await runSimulation(page, scenario.message);
      expectHumanizedReply(reply);
      for (const matcher of scenario.expected) {
        expect(reply).toMatch(matcher);
      }
    });
  }

  test("historico mostra a resposta da IA ja humanizada", async ({ page }) => {
    const reply = await runSimulation(page, "Oi, quero agendar uma avaliacao para esta semana.");
    expectHumanizedReply(reply);
    await expect(page.getByText("Historico de treino")).toBeVisible();
    await expect
      .poll(async () => page.getByText(reply, { exact: false }).count(), { timeout: 20_000 })
      .toBeGreaterThan(1);
  });

  test("operador consegue salvar uma edicao aprovada no historico", async ({ page }) => {
    await runSimulation(page, "Quanto custa clareamento dental?");
    const editedResponse = page.locator(`textarea[placeholder="${editedReplyPlaceholder}"]`);
    const customReply = "Claro, o valor depende da avaliacao, porque cada caso muda um pouco. Se quiser, eu te mostro os horarios livres para conversar com o dentista.";
    const customNote = `nota humanizada ${Date.now()}`;

    await editedResponse.fill(customReply);
    await page.getByPlaceholder("Ex.: usar tom mais consultivo e convidar para proximo passo.").fill(customNote);
    await page.getByRole("button", { name: "Salvar edicao" }).click();

    await expect(page.getByText(/Edicao salva no historico de treino/i)).toBeVisible();
    await expect
      .poll(async () => page.getByText(customReply, { exact: false }).count(), { timeout: 20_000 })
      .toBeGreaterThan(1);
    await expect(page.getByText(`Nota: ${customNote}`)).toBeVisible();
  });

  test("registro do historico pode voltar para o editor", async ({ page }) => {
    await runSimulation(page, "Quero falar com um atendente humano.");
    const firstReply = await page.locator(`textarea[placeholder="${editedReplyPlaceholder}"]`).inputValue();
    await page.getByRole("button", { name: "Usar no editor" }).first().click();
    await expect(page.locator(`textarea[placeholder="${editedReplyPlaceholder}"]`)).toHaveValue(firstReply);
  });
});
