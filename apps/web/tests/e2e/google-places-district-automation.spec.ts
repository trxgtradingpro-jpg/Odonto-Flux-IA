import { expect, test } from "@playwright/test";

test("imports clinics district by district until the configured limit", async ({ page }) => {
  const searchedQueries: string[] = [];
  const importedPlaceIds: string[] = [];

  await page.route("**/api/v1/admin/auth/me", async (route) => {
    await route.fulfill({
      json: {
        id: "admin-user",
        email: "admin@clinicflux.test",
        full_name: "Admin ClinicFlux",
        phone: null,
        roles: ["admin_platform"],
        is_active: true,
        force_password_change: false,
        page_permissions: {},
        adm_page_permissions: {},
        is_affiliate: false,
        last_login_at: null,
        created_at: "2026-06-09T12:00:00Z",
        updated_at: "2026-06-09T12:00:00Z",
      },
    });
  });

  await page.route("**/api/v1/admin/google-places/automation-plan", async (route) => {
    await route.fulfill({
      json: {
        state: "SP",
        city: "Sao Paulo",
        municipality_id: 3550308,
        target_limit: 2,
        source: "ibge_districts",
        areas: ["Agua Rasa", "Vila Mariana"],
        queries: [
          {
            area: "Agua Rasa",
            term: "clinica odontologica",
            query: "clinica odontologica em Agua Rasa, Sao Paulo - SP",
          },
          {
            area: "Vila Mariana",
            term: "clinica odontologica",
            query: "clinica odontologica em Vila Mariana, Sao Paulo - SP",
          },
        ],
        estimated_max_search_calls: 2,
      },
    });
  });

  await page.route("**/api/v1/admin/google-places/search", async (route) => {
    const payload = route.request().postDataJSON() as { query: string };
    searchedQueries.push(payload.query);
    const index = searchedQueries.length;
    await route.fulfill({
      json: {
        query: payload.query,
        limit: 20,
        field_mask: "places.id",
        cost_mode: "search_basic_only",
        results: [
          {
            place_id: `place-${index}`,
            name: `Clinica ${index}`,
            formatted_address: `Rua ${index}`,
            city: "Sao Paulo",
            state: "SP",
            google_maps_url: null,
            business_status: "OPERATIONAL",
            types: ["dentist"],
            duplicate_prospect_id: null,
            duplicate_clinic_name: null,
          },
        ],
      },
    });
  });

  await page.route("**/api/v1/admin/google-places/import", async (route) => {
    const payload = route.request().postDataJSON() as { place_ids: string[] };
    importedPlaceIds.push(...payload.place_ids);
    const placeId = payload.place_ids[0];
    await route.fulfill({
      json: {
        created_count: 1,
        duplicate_count: 0,
        failed_count: 0,
        requested_count: 1,
        include_rating: false,
        results: [
          {
            place_id: placeId,
            status: "created",
            message: "Clinica importada para o CRM comercial.",
            name: `Clinica ${importedPlaceIds.length}`,
            prospect: {
              id: `prospect-${importedPlaceIds.length}`,
              clinic_name: `Clinica ${importedPlaceIds.length}`,
              phone: "5511999999999",
              whatsapp_phone: "5511999999999",
              city: "Sao Paulo",
              state: "SP",
              website: null,
            },
          },
        ],
      },
    });
  });

  await page.goto("/adm/importar-clinicas", { waitUntil: "domcontentloaded" });
  await page.evaluate(() => {
    window.localStorage.setItem("odontoflux_adm_access_token", "admin-e2e-token");
  });
  await page.reload({ waitUntil: "domcontentloaded" });

  await expect(page.getByText("Automacao por distritos")).toBeVisible();
  await page.getByLabel("Limite de clinicas").fill("2");
  await page.getByRole("button", { name: "Buscar bairros e cadastrar" }).click();

  await expect(page.getByText("Varredura concluida")).toBeVisible();
  await expect(page.getByText("2/2")).toBeVisible();
  await expect(page.getByText("Cadastradas").locator("..").getByText("2")).toBeVisible();
  expect(searchedQueries).toHaveLength(2);
  expect(importedPlaceIds).toEqual(["place-1", "place-2"]);
});
