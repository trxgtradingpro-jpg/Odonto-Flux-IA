export type SiteTemplatePalette = {
  primary: string;
  secondary: string;
  accent: string;
  background: string;
  surface: string;
  text: string;
  muted: string;
};

export type SiteTemplate = {
  slug: string;
  name: string;
  shortName: string;
  niche: string;
  style: string;
  offerLane: "website_seo" | "audit" | "conversion_landing";
  headline: string;
  subheadline: string;
  outcome: string;
  heroImage: string;
  palette: SiteTemplatePalette;
  idealFor: string[];
  badges: string[];
  metrics: Array<{ label: string; value: string }>;
  services: string[];
  sections: Array<{ title: string; body: string }>;
  trustSignals: string[];
  conversionHooks: string[];
  faqs: Array<{ question: string; answer: string }>;
};

export type SiteTemplateVisual = {
  archetype: string;
  heroImage: string;
  heroImagePosition: string;
  heroOverlay: string;
  layout: "boutique" | "signature" | "access" | "editorial" | "clinical" | "calm" | "performance" | "active" | "profile";
  catalogGradient: string;
  proofTitle: string;
  proofBody: string;
  ctaLabel: string;
  secondaryCtaLabel: string;
  serviceIntro: string;
  experienceTitle: string;
  experienceBody: string;
  experiencePoints: string[];
  patientJourney: string[];
};

export type SiteTemplateEliteBlock = {
  eyebrow: string;
  title: string;
  body: string;
  items: string[];
};

export type SiteTemplateShowcaseItem = {
  title: string;
  body: string;
};

export type SiteTemplateSocialProof = {
  title: string;
  quote: string;
  source: string;
};

export type SiteTemplateEliteDetails = {
  motion: "cinematic" | "direct" | "editorial" | "calm" | "performance" | "clinical";
  visualFocus: string;
  authority: SiteTemplateEliteBlock;
  showcase: {
    title: string;
    body: string;
    items: SiteTemplateShowcaseItem[];
  };
  socialProof: SiteTemplateSocialProof;
  localTrust: SiteTemplateEliteBlock;
  finalCta: {
    title: string;
    body: string;
  };
};

export type SiteTemplateSectionKey = "tratamentos" | "equipe" | "estrutura" | "contato";

export const SITE_TEMPLATE_LIBRARY_VERSION = "2026.05.31-elite-v2";
export const SITE_TEMPLATE_CATALOG_PATH = "/modelos-sites";

const DEFAULT_HERO_IMAGE = "/images/dental-floss-smile-background.png";

const CLINIC_HERO_IMAGE =
  "https://images.unsplash.com/photo-1629909613654-28e377c37b09?auto=format&fit=crop&w=1800&q=82";
const BEAUTY_HERO_IMAGE =
  "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?auto=format&fit=crop&w=1800&q=82";
const MEDICAL_HERO_IMAGE =
  "https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?auto=format&fit=crop&w=1800&q=82";
const WELLNESS_HERO_IMAGE =
  "https://images.unsplash.com/photo-1519823551278-64ac92734fb1?auto=format&fit=crop&w=1800&q=82";
const PERFORMANCE_HERO_IMAGE =
  "https://images.unsplash.com/photo-1571019613914-85f342c6a11e?auto=format&fit=crop&w=1800&q=82";

export const SITE_TEMPLATE_VISUALS: Record<string, SiteTemplateVisual> = {
  "clinica-odontologica-premium": {
    archetype: "Boutique odontologica de alto ticket",
    heroImage: CLINIC_HERO_IMAGE,
    heroImagePosition: "center",
    heroOverlay: "linear-gradient(90deg, rgba(250,250,247,0.97) 0%, rgba(250,250,247,0.88) 43%, rgba(250,250,247,0.24) 100%)",
    layout: "boutique",
    catalogGradient: "linear-gradient(135deg, rgba(15,118,110,0.92), rgba(217,119,6,0.72))",
    proofTitle: "Percepcao de valor antes do WhatsApp",
    proofBody: "A primeira dobra combina especialidade, tecnologia, avaliacao e prova local para vender tratamentos de maior decisao.",
    ctaLabel: "Agendar avaliacao premium",
    secondaryCtaLabel: "Ver tratamentos",
    serviceIntro: "Tratamentos de alto valor aparecem com contexto, indicacao e uma chamada de avaliacao sem parecer panfleto.",
    experienceTitle: "Experiencia de decisao premium",
    experienceBody: "O paciente entende porque a clinica e diferente antes de comparar preco.",
    experiencePoints: ["Especialistas e CRO visiveis", "Bloco de tecnologia e estrutura", "Prova social no fluxo de leitura"],
    patientJourney: ["Busca no Google", "Confere autoridade", "Entende o tratamento", "Chama no WhatsApp"],
  },
  "clinica-odontologica-popular": {
    archetype: "Unidade acessivel de alto volume",
    heroImage: DEFAULT_HERO_IMAGE,
    heroImagePosition: "center",
    heroOverlay: "linear-gradient(90deg, rgba(248,250,252,0.98) 0%, rgba(248,250,252,0.9) 48%, rgba(248,250,252,0.45) 100%)",
    layout: "access",
    catalogGradient: "linear-gradient(135deg, rgba(37,99,235,0.9), rgba(249,115,22,0.74))",
    proofTitle: "Rapido para entender e chamar",
    proofBody: "A pagina prioriza servicos, horario, localizacao e CTA claro para pacientes que querem resolver logo.",
    ctaLabel: "Chamar a clinica agora",
    secondaryCtaLabel: "Ver servicos",
    serviceIntro: "Cards objetivos reduzem duvida e deixam os principais procedimentos prontos para conversa.",
    experienceTitle: "Jornada sem friccao",
    experienceBody: "O visitante encontra preco percebido, endereco e atendimento sem precisar garimpar informacao.",
    experiencePoints: ["Servicos populares acima da dobra", "Urgencia responsavel", "Endereco e horario em destaque"],
    patientJourney: ["Sente dor ou procura limpeza", "Confere atendimento", "Ve como chegar", "Chama no WhatsApp"],
  },
  "estetica-facial-moderna": {
    archetype: "Clinica visual e aspiracional",
    heroImage: BEAUTY_HERO_IMAGE,
    heroImagePosition: "center",
    heroOverlay: "linear-gradient(90deg, rgba(255,247,247,0.98) 0%, rgba(255,247,247,0.86) 44%, rgba(255,247,247,0.28) 100%)",
    layout: "editorial",
    catalogGradient: "linear-gradient(135deg, rgba(190,18,60,0.88), rgba(8,145,178,0.72))",
    proofTitle: "Desejo com responsabilidade",
    proofBody: "O visual valoriza pele, cuidado e resultado possivel sem promessas exageradas.",
    ctaLabel: "Avaliar meu caso",
    secondaryCtaLabel: "Ver protocolos",
    serviceIntro: "Cada procedimento ganha beneficio, indicacao e caminho para avaliacao profissional.",
    experienceTitle: "Vitrine de protocolos",
    experienceBody: "A estrutura permite mostrar antes/depois, depoimentos e orientacao sem perder elegancia.",
    experiencePoints: ["Tratamentos explicados por objetivo", "Galeria controlada", "Agenda de manutencao"],
    patientJourney: ["Deseja melhorar algo", "Compara protocolos", "Confere prova", "Agenda avaliacao"],
  },
  "dermatologia-premium": {
    archetype: "Autoridade medica elegante",
    heroImage: MEDICAL_HERO_IMAGE,
    heroImagePosition: "center",
    heroOverlay: "linear-gradient(90deg, rgba(250,250,255,0.98) 0%, rgba(250,250,255,0.88) 45%, rgba(250,250,255,0.25) 100%)",
    layout: "clinical",
    catalogGradient: "linear-gradient(135deg, rgba(124,58,237,0.88), rgba(14,116,144,0.72))",
    proofTitle: "Tecnica sem esfriar a experiencia",
    proofBody: "Consulta, tratamentos e tecnologia aparecem com linguagem medica acessivel.",
    ctaLabel: "Marcar consulta",
    secondaryCtaLabel: "Conhecer tratamentos",
    serviceIntro: "A pagina separa queixas, tratamentos e orientacoes para pacientes que pesquisam antes de marcar.",
    experienceTitle: "Autoridade para decisao medica",
    experienceBody: "O paciente entende especialidade, metodo e criterios antes do contato.",
    experiencePoints: ["CRM e area de atuacao visiveis", "Tecnologia contextualizada", "Orientacoes pre-consulta"],
    patientJourney: ["Pesquisa sintomas", "Confere especialista", "Entende conduta", "Marca consulta"],
  },
  "psicologia-humanizada": {
    archetype: "Acolhimento privado e calmo",
    heroImage: WELLNESS_HERO_IMAGE,
    heroImagePosition: "center",
    heroOverlay: "linear-gradient(90deg, rgba(250,250,249,0.98) 0%, rgba(250,250,249,0.9) 45%, rgba(250,250,249,0.3) 100%)",
    layout: "calm",
    catalogGradient: "linear-gradient(135deg, rgba(79,70,229,0.82), rgba(13,148,136,0.68))",
    proofTitle: "Acolhimento antes da primeira sessao",
    proofBody: "O layout transmite privacidade, metodo e facilidade para marcar sem pressao.",
    ctaLabel: "Falar com a psicologa",
    secondaryCtaLabel: "Ver abordagem",
    serviceIntro: "Temas e formatos de atendimento aparecem com cuidado, sem linguagem alarmista.",
    experienceTitle: "Decisao sensivel e segura",
    experienceBody: "A pagina ajuda a pessoa a sentir clareza sobre abordagem, sigilo e primeiro passo.",
    experiencePoints: ["Tom acolhedor", "Online e presencial claros", "FAQ para reduzir ansiedade"],
    patientJourney: ["Busca apoio", "Le abordagem", "Confere sigilo", "Envia mensagem"],
  },
  "fisioterapia-reabilitacao": {
    archetype: "Performance, recuperacao e movimento",
    heroImage: PERFORMANCE_HERO_IMAGE,
    heroImagePosition: "center",
    heroOverlay: "linear-gradient(90deg, rgba(247,250,252,0.98) 0%, rgba(247,250,252,0.88) 42%, rgba(247,250,252,0.26) 100%)",
    layout: "active",
    catalogGradient: "linear-gradient(135deg, rgba(14,165,233,0.88), rgba(22,163,74,0.72))",
    proofTitle: "Plano claro para voltar a se mover",
    proofBody: "Dor, recuperacao e performance aparecem com promessa responsavel e orientada a tratamento.",
    ctaLabel: "Agendar avaliacao",
    secondaryCtaLabel: "Ver programas",
    serviceIntro: "Programas organizados por objetivo facilitam a leitura de quem procura reabilitacao.",
    experienceTitle: "Do problema ao plano",
    experienceBody: "O visitante entende causa, abordagem e proximo passo em poucos blocos.",
    experiencePoints: ["Objetivos por perfil", "Evolucao e acompanhamento", "Blocos para atletas e dores"],
    patientJourney: ["Sente dor", "Identifica programa", "Entende plano", "Agenda avaliacao"],
  },
  "nutricionista-autoridade": {
    archetype: "Consultoria de resultado sustentavel",
    heroImage: "https://images.unsplash.com/photo-1490645935967-10de6ba17061?auto=format&fit=crop&w=1800&q=82",
    heroImagePosition: "center",
    heroOverlay: "linear-gradient(90deg, rgba(250,250,247,0.98) 0%, rgba(250,250,247,0.88) 45%, rgba(250,250,247,0.25) 100%)",
    layout: "editorial",
    catalogGradient: "linear-gradient(135deg, rgba(22,101,52,0.86), rgba(202,138,4,0.72))",
    proofTitle: "Metodo acima de dieta pronta",
    proofBody: "A pagina vende acompanhamento, estrategia e autoridade sem cair em promessa milagrosa.",
    ctaLabel: "Quero acompanhamento",
    secondaryCtaLabel: "Ver objetivos",
    serviceIntro: "Objetivos alimentares ficam organizados por contexto de vida, rotina e acompanhamento.",
    experienceTitle: "Plano alimentar com contexto",
    experienceBody: "O visitante percebe metodo, acompanhamento e personalizacao desde a primeira dobra.",
    experiencePoints: ["Objetivos por perfil", "Acompanhamento recorrente", "Prova de autoridade"],
    patientJourney: ["Define objetivo", "Conhece metodo", "Confere acompanhamento", "Marca consulta"],
  },
  "clinica-medica-multiespecialidade": {
    archetype: "Centro medico organizado",
    heroImage: MEDICAL_HERO_IMAGE,
    heroImagePosition: "center",
    heroOverlay: "linear-gradient(90deg, rgba(248,250,252,0.98) 0%, rgba(248,250,252,0.9) 45%, rgba(248,250,252,0.24) 100%)",
    layout: "clinical",
    catalogGradient: "linear-gradient(135deg, rgba(30,64,175,0.9), rgba(13,148,136,0.7))",
    proofTitle: "Multiespecialidade sem confusao",
    proofBody: "O modelo organiza especialidades, horarios e fluxo de agendamento para familias e empresas.",
    ctaLabel: "Encontrar especialidade",
    secondaryCtaLabel: "Ver agenda",
    serviceIntro: "Especialidades aparecem agrupadas para o paciente achar o atendimento certo rapidamente.",
    experienceTitle: "Navegacao para muitas demandas",
    experienceBody: "A arquitetura evita que uma clinica grande pareca baguncada.",
    experiencePoints: ["Especialidades por categoria", "Fluxo de agendamento simples", "Localizacao e convenios"],
    patientJourney: ["Procura medico", "Escolhe especialidade", "Confere horarios", "Agenda atendimento"],
  },
  "consultorio-especialista": {
    archetype: "Especialista de referencia",
    heroImage: CLINIC_HERO_IMAGE,
    heroImagePosition: "center",
    heroOverlay: "linear-gradient(90deg, rgba(255,255,255,0.98) 0%, rgba(255,255,255,0.88) 45%, rgba(255,255,255,0.2) 100%)",
    layout: "profile",
    catalogGradient: "linear-gradient(135deg, rgba(79,70,229,0.86), rgba(15,118,110,0.72))",
    proofTitle: "Nome, metodo e autoridade em foco",
    proofBody: "Ideal para profissionais que precisam parecer referencia antes do primeiro contato.",
    ctaLabel: "Solicitar avaliacao",
    secondaryCtaLabel: "Conhecer metodo",
    serviceIntro: "A pagina da espaco para especialidade, criterios de atendimento e resultados esperados.",
    experienceTitle: "Posicionamento de especialista",
    experienceBody: "O visitante entende porque aquele profissional e a escolha certa para um caso especifico.",
    experiencePoints: ["Bio profissional forte", "Metodo proprietario", "Casos e indicacoes"],
    patientJourney: ["Busca especialista", "Avalia curriculo", "Entende metodo", "Solicita consulta"],
  },
  "landing-page-conversao-rapida": {
    archetype: "Campanha direta de alta conversao",
    heroImage: DEFAULT_HERO_IMAGE,
    heroImagePosition: "center",
    heroOverlay: "linear-gradient(90deg, rgba(12,12,12,0.88) 0%, rgba(12,12,12,0.72) 48%, rgba(12,12,12,0.18) 100%)",
    layout: "performance",
    catalogGradient: "linear-gradient(135deg, rgba(12,12,12,0.9), rgba(245,158,11,0.76))",
    proofTitle: "Uma oferta, uma acao",
    proofBody: "Feita para trafego pago, campanha de WhatsApp ou promocao com proximo passo nitido.",
    ctaLabel: "Quero essa oferta",
    secondaryCtaLabel: "Ver prova",
    serviceIntro: "Os blocos priorizam uma campanha central, beneficios rapidos e CTA repetido no ponto certo.",
    experienceTitle: "Velocidade para campanha",
    experienceBody: "Menos navegacao, mais clareza de oferta e conversao.",
    experiencePoints: ["Oferta unica", "Prova curta", "CTA em todos os blocos"],
    patientJourney: ["Clica no anuncio", "Entende oferta", "Confere prova", "Chama no WhatsApp"],
  },
  "clinica-saude-familiar": {
    archetype: "Cuidado familiar e recorrente",
    heroImage: "https://images.unsplash.com/photo-1584515933487-779824d29309?auto=format&fit=crop&w=1800&q=82",
    heroImagePosition: "center",
    heroOverlay: "linear-gradient(90deg, rgba(255,251,235,0.98) 0%, rgba(255,251,235,0.88) 45%, rgba(255,251,235,0.24) 100%)",
    layout: "calm",
    catalogGradient: "linear-gradient(135deg, rgba(13,148,136,0.86), rgba(234,88,12,0.7))",
    proofTitle: "Confianca para a familia inteira",
    proofBody: "A pagina valoriza rotina, prevencao, localizacao e proximidade com linguagem calorosa.",
    ctaLabel: "Agendar para minha familia",
    secondaryCtaLabel: "Ver cuidados",
    serviceIntro: "Servicos recorrentes ficam agrupados para pais, filhos e pacientes de acompanhamento.",
    experienceTitle: "Cuidado continuo",
    experienceBody: "O visitante percebe que a clinica resolve demandas recorrentes com organizacao e carinho.",
    experiencePoints: ["Rotina preventiva", "Atendimento para varias idades", "Mapa e horarios claros"],
    patientJourney: ["Procura cuidado confiavel", "Confere servicos", "Ve localizacao", "Agenda horario"],
  },
};

export function getSiteTemplateVisual(template: Pick<SiteTemplate, "slug" | "heroImage">): SiteTemplateVisual {
  return (
    SITE_TEMPLATE_VISUALS[template.slug] ?? {
      archetype: "Site profissional para clinicas",
      heroImage: template.heroImage || DEFAULT_HERO_IMAGE,
      heroImagePosition: "center",
      heroOverlay: "linear-gradient(90deg, rgba(255,255,255,0.97) 0%, rgba(255,255,255,0.88) 46%, rgba(255,255,255,0.32) 100%)",
      layout: "clinical",
      catalogGradient: "linear-gradient(135deg, rgba(15,118,110,0.88), rgba(217,119,6,0.7))",
      proofTitle: "Estrutura pronta para vender",
      proofBody: "O modelo combina clareza, confianca e chamadas para WhatsApp.",
      ctaLabel: "Selecionar template",
      secondaryCtaLabel: "Ver estrutura",
      serviceIntro: "Servicos organizados para o paciente entender rapido.",
      experienceTitle: "Experiencia profissional",
      experienceBody: "Uma pagina preparada para apresentar a clinica com credibilidade.",
      experiencePoints: ["Oferta clara", "Prova social", "Contato sem friccao"],
      patientJourney: ["Busca local", "Confere prova", "Entende oferta", "Chama no WhatsApp"],
    }
  );
}

export const SITE_TEMPLATE_ELITE_DETAILS: Record<string, SiteTemplateEliteDetails> = {
  "clinica-odontologica-premium": {
    motion: "cinematic",
    visualFocus: "luxo discreto, tecnologia e sorriso de alto valor",
    authority: {
      eyebrow: "Autoridade premium",
      title: "Especialistas, estrutura e decisao de alto ticket no mesmo fluxo.",
      body: "O modelo prepara o paciente para implantes, lentes e estetica dental com uma narrativa de confianca antes de falar em preco.",
      items: ["CRO e especialidades em destaque", "Tecnologia como prova de valor", "CTA de avaliacao sem pressao"],
    },
    showcase: {
      title: "Tratamentos apresentados como experiencia premium",
      body: "Cada bloco combina indicacao, valor percebido e proximo passo para pacientes que pesquisam antes de decidir.",
      items: [
        { title: "Implantes planejados", body: "Explica avaliacao, planejamento digital e seguranca do processo." },
        { title: "Estetica do sorriso", body: "Apresenta lentes, clareamento e harmonizacao com linguagem elegante." },
        { title: "Estrutura boutique", body: "Mostra ambiente, equipe e atendimento consultivo como diferencial." },
      ],
    },
    socialProof: {
      title: "Prova social de alto valor",
      quote: "Modelo de depoimento para destacar confianca, acolhimento e clareza no plano de tratamento.",
      source: "Espaco para Google Reviews e casos autorizados",
    },
    localTrust: {
      eyebrow: "SEO local premium",
      title: "Busca local conectada a uma experiencia de marca.",
      body: "Cidade, bairro, mapa e WhatsApp entram como prova de presenca, nao apenas informacao operacional.",
      items: ["Bairro e cidade no primeiro scroll", "Mapa contextualizado", "Perguntas de alto ticket respondidas"],
    },
    finalCta: {
      title: "Transforme interesse em avaliacao premium.",
      body: "O CTA final fecha a pagina com foco em clareza, autoridade e um convite direto para WhatsApp.",
    },
  },
  "clinica-odontologica-popular": {
    motion: "direct",
    visualFocus: "clareza, volume e atendimento rapido",
    authority: {
      eyebrow: "Confianca acessivel",
      title: "Servicos simples de entender para o paciente chamar sem friccao.",
      body: "O modelo valoriza preco percebido, urgencia responsavel, horario e localizacao antes do visitante abandonar a pagina.",
      items: ["Servicos populares acima da dobra", "Endereco e horario visiveis", "WhatsApp como caminho principal"],
    },
    showcase: {
      title: "Oferta direta para demanda local",
      body: "Os blocos reduzem duvida para quem precisa resolver limpeza, dor, extracao ou restauracao.",
      items: [
        { title: "Atendimento rapido", body: "Mostra como chamar, onde ir e qual o proximo passo." },
        { title: "Urgencia responsavel", body: "Comunica dor e emergencia sem prometer resultado imediato." },
        { title: "Servicos populares", body: "Organiza procedimentos comuns em linguagem direta." },
      ],
    },
    socialProof: {
      title: "Confianca de bairro",
      quote: "Modelo de depoimento curto para reforcar atendimento claro, preco justo e equipe atenciosa.",
      source: "Espaco para avaliacoes locais",
    },
    localTrust: {
      eyebrow: "Presenca local",
      title: "Localizacao, horario e contato no caminho natural da leitura.",
      body: "A pagina foi pensada para paciente de alto volume que decide rapido pelo celular.",
      items: ["Mapa sem esconder CTA", "Horario objetivo", "Contato em todos os blocos"],
    },
    finalCta: {
      title: "Facilite a chamada agora.",
      body: "A pagina fecha com um convite simples para falar com a recepcao pelo WhatsApp.",
    },
  },
  "estetica-facial-moderna": {
    motion: "editorial",
    visualFocus: "beleza editorial, pele e desejo responsavel",
    authority: {
      eyebrow: "Estetica com criterio",
      title: "Protocolos apresentados com desejo, cuidado e responsabilidade.",
      body: "A experiencia valoriza transformacao possivel sem prometer resultado garantido ou parecer anuncio agressivo.",
      items: ["Profissional responsavel", "Protocolos por objetivo", "Galeria controlada"],
    },
    showcase: {
      title: "Protocolos que parecem uma vitrine premium",
      body: "Cada card ajuda o visitante a entender indicacao, beneficio e necessidade de avaliacao.",
      items: [
        { title: "Pele e textura", body: "Blocos para limpeza de pele, bioestimuladores e rotina de cuidado." },
        { title: "Harmonizacao leve", body: "Copy com foco em avaliacao individual e naturalidade." },
        { title: "Manutencao", body: "Agenda recorrente para retorno e acompanhamento." },
      ],
    },
    socialProof: {
      title: "Desejo com prova",
      quote: "Modelo de depoimento para destacar atendimento cuidadoso, orientacao clara e seguranca no procedimento.",
      source: "Espaco para depoimentos autorizados",
    },
    localTrust: {
      eyebrow: "Agenda local",
      title: "Avaliacao e manutencao com caminho claro pelo WhatsApp.",
      body: "Cidade, agenda e orientacao pre-procedimento aparecem sem quebrar o clima editorial.",
      items: ["CTA de avaliacao", "Orientacao pre-procedimento", "Prova visual com cuidado"],
    },
    finalCta: {
      title: "Convide o paciente a avaliar o caso.",
      body: "O fechamento reforca desejo, seguranca e proximo passo com tom elegante.",
    },
  },
  "dermatologia-premium": {
    motion: "clinical",
    visualFocus: "medicina limpa, autoridade e tecnologia",
    authority: {
      eyebrow: "Autoridade medica",
      title: "Dermatologia com organizacao clinica e experiencia premium.",
      body: "O modelo combina consulta, queixas, estetica e tecnologia com linguagem acessivel para paciente criterioso.",
      items: ["CRM e especialidade visiveis", "Tecnologia explicada sem exagero", "Conduta por queixa"],
    },
    showcase: {
      title: "Tratamentos por problema e decisao",
      body: "A estrutura ajuda o paciente a se reconhecer na demanda antes de marcar consulta.",
      items: [
        { title: "Pele, acne e manchas", body: "Organiza queixas comuns com orientacao responsavel." },
        { title: "Estetica medica", body: "Apresenta procedimentos com seguranca e criterio." },
        { title: "Consulta especializada", body: "Mostra como acontece avaliacao, exame e acompanhamento." },
      ],
    },
    socialProof: {
      title: "Credibilidade antes da agenda",
      quote: "Modelo de depoimento para reforcar explicacao clara, cuidado medico e acompanhamento.",
      source: "Espaco para avaliacoes e credenciais",
    },
    localTrust: {
      eyebrow: "Consulta local",
      title: "Cidade, agenda e orientacoes sem perder sobriedade.",
      body: "O paciente encontra especialidade, proximo passo e localizacao sem excesso visual.",
      items: ["Orientacoes pre-consulta", "Agenda por WhatsApp", "Mapa e bairro discretos"],
    },
    finalCta: {
      title: "Feche com seguranca medica.",
      body: "O CTA final conduz para uma consulta, nao para promessa de resultado.",
    },
  },
  "psicologia-humanizada": {
    motion: "calm",
    visualFocus: "acolhimento, privacidade e primeira conversa leve",
    authority: {
      eyebrow: "Acolhimento seguro",
      title: "Uma pagina que reduz ansiedade antes do primeiro contato.",
      body: "A composicao evita pressao comercial e explica abordagem, sigilo e formatos de atendimento com calma.",
      items: ["Abordagem terapeutica", "Sigilo em destaque", "Online e presencial claros"],
    },
    showcase: {
      title: "Temas atendidos com cuidado",
      body: "Os blocos ajudam a pessoa a se orientar sem rotulos fortes ou linguagem alarmista.",
      items: [
        { title: "Ansiedade e rotina", body: "Texto leve para quem busca apoio no dia a dia." },
        { title: "Relacionamentos", body: "Explica escuta e processo sem prometer solucao rapida." },
        { title: "Primeira sessao", body: "Mostra como funciona o primeiro passo." },
      ],
    },
    socialProof: {
      title: "Seguranca emocional",
      quote: "Modelo de depoimento discreto para reforcar acolhimento, respeito e clareza no processo.",
      source: "Espaco opcional para prova social etica",
    },
    localTrust: {
      eyebrow: "Contato cuidadoso",
      title: "O WhatsApp entra como ponte, nao como pressao.",
      body: "A pagina deixa claro como chamar, onde atender e o que esperar da primeira conversa.",
      items: ["Tom calmo no CTA", "Endereco ou online", "FAQ para duvidas sensiveis"],
    },
    finalCta: {
      title: "Convide para uma primeira conversa.",
      body: "O fechamento mantem o tom humano e facilita o contato sem urgencia artificial.",
    },
  },
  "fisioterapia-reabilitacao": {
    motion: "performance",
    visualFocus: "movimento, recuperacao e evolucao funcional",
    authority: {
      eyebrow: "Plano de recuperacao",
      title: "Do problema ao plano, com evolucao visivel.",
      body: "O modelo organiza dores, reabilitacao e performance para mostrar metodo antes da avaliacao.",
      items: ["Avaliacao funcional", "Programas por objetivo", "Acompanhamento de evolucao"],
    },
    showcase: {
      title: "Programas por objetivo do paciente",
      body: "Cada bloco traduz a demanda em uma rota de tratamento clara.",
      items: [
        { title: "Dor e mobilidade", body: "Organiza sintomas comuns e proximo passo." },
        { title: "Pos-operatorio", body: "Mostra cuidado, fases e acompanhamento." },
        { title: "Performance", body: "Fala com atletas e pacientes ativos sem exagero." },
      ],
    },
    socialProof: {
      title: "Evolucao percebida",
      quote: "Modelo de depoimento para destacar progresso, acompanhamento e clareza nos exercicios.",
      source: "Espaco para casos autorizados",
    },
    localTrust: {
      eyebrow: "Atendimento proximo",
      title: "Avaliacao, frequencia e localizacao explicadas sem confusao.",
      body: "O paciente entende se a clinica atende sua dor, onde fica e como iniciar.",
      items: ["Objetivos por perfil", "Agenda de avaliacao", "Mapa e horarios"],
    },
    finalCta: {
      title: "Transforme dor em plano de acao.",
      body: "O CTA final chama para avaliacao funcional com foco em retorno seguro ao movimento.",
    },
  },
  "nutricionista-autoridade": {
    motion: "editorial",
    visualFocus: "metodo, rotina real e acompanhamento sustentavel",
    authority: {
      eyebrow: "Metodo nutricional",
      title: "Autoridade sem promessa milagrosa.",
      body: "A pagina vende acompanhamento, contexto e plano individualizado com linguagem confiavel.",
      items: ["CRN e metodo", "Objetivos por perfil", "Acompanhamento recorrente"],
    },
    showcase: {
      title: "Objetivos organizados por rotina",
      body: "O paciente entende como a consulta se adapta a vida real, nao a uma dieta pronta.",
      items: [
        { title: "Emagrecimento", body: "Copy responsavel com foco em processo e consistencia." },
        { title: "Performance", body: "Espaco para nutricao esportiva e ajustes de rotina." },
        { title: "Saude intestinal", body: "Bloco educativo para demandas especificas." },
      ],
    },
    socialProof: {
      title: "Metodo que gera confianca",
      quote: "Modelo de depoimento para mostrar orientacao, clareza e acompanhamento sem prometer resultado fixo.",
      source: "Espaco para relatos autorizados",
    },
    localTrust: {
      eyebrow: "Consulta local ou online",
      title: "A pagina explica formato, retorno e acompanhamento.",
      body: "O visitante entende como comecar e como sera acompanhado depois da primeira consulta.",
      items: ["Online ou presencial", "Retornos explicados", "CTA para acompanhamento"],
    },
    finalCta: {
      title: "Convide para um acompanhamento realista.",
      body: "O fechamento reforca metodo, rotina e conversa inicial.",
    },
  },
  "clinica-medica-multiespecialidade": {
    motion: "clinical",
    visualFocus: "organizacao institucional, especialidades e agenda",
    authority: {
      eyebrow: "Centro medico organizado",
      title: "Muitas especialidades sem parecer uma lista confusa.",
      body: "A arquitetura ajuda o paciente a encontrar area, medico, unidade e contato rapidamente.",
      items: ["Especialidades agrupadas", "Equipe e unidades", "Agenda pela recepcao"],
    },
    showcase: {
      title: "Navegacao por demanda",
      body: "A clinica ganha uma vitrine organizada para consultas, exames e acompanhamento.",
      items: [
        { title: "Especialidades", body: "Agrupadas para facilitar escolha." },
        { title: "Unidades", body: "Endereco, horario e recepcao sem friccao." },
        { title: "Exames e consultas", body: "Servicos operacionais com CTA claro." },
      ],
    },
    socialProof: {
      title: "Institucional com rosto humano",
      quote: "Modelo de depoimento para reforcar organizacao, atendimento da recepcao e clareza no agendamento.",
      source: "Espaco para avaliacoes locais",
    },
    localTrust: {
      eyebrow: "Operacao local",
      title: "Unidades, horarios e contatos no fluxo certo.",
      body: "O visitante nao precisa procurar informacao basica antes de chamar.",
      items: ["Horarios", "Convenios ou diferenciais", "Mapa por unidade"],
    },
    finalCta: {
      title: "Ajude o paciente a escolher a especialidade.",
      body: "O CTA final conduz para recepcao e triagem com clareza operacional.",
    },
  },
  "consultorio-especialista": {
    motion: "cinematic",
    visualFocus: "marca pessoal, metodo e autoridade individual",
    authority: {
      eyebrow: "Especialista de referencia",
      title: "A pagina coloca nome, curriculo e metodo no centro.",
      body: "Ideal para profissional que precisa ser escolhido pela autoridade, nao apenas pela localizacao.",
      items: ["Bio forte", "Credenciais", "Metodo proprietario"],
    },
    showcase: {
      title: "Casos, indicacoes e abordagem",
      body: "O visitante entende quando procurar o especialista e como a consulta funciona.",
      items: [
        { title: "Condicoes atendidas", body: "Demandas explicadas por criterio de atendimento." },
        { title: "Segunda opiniao", body: "Bloco para pacientes que pesquisam muito antes de decidir." },
        { title: "Metodo", body: "Diferencial autoral explicado com sobriedade." },
      ],
    },
    socialProof: {
      title: "Reputacao com sobriedade",
      quote: "Modelo de depoimento para mostrar seguranca, escuta e explicacao tecnica acessivel.",
      source: "Espaco para avaliacoes e credenciais",
    },
    localTrust: {
      eyebrow: "Agenda especializada",
      title: "Contato com proximo passo adequado ao caso.",
      body: "A pagina pode orientar envio de duvida, exames ou solicitacao de consulta.",
      items: ["Consulta especializada", "Envio de duvida", "Orientacao pre-atendimento"],
    },
    finalCta: {
      title: "Convide o paciente certo para consulta.",
      body: "O fechamento reforca autoridade e direciona para um contato qualificado.",
    },
  },
  "landing-page-conversao-rapida": {
    motion: "performance",
    visualFocus: "campanha, oferta unica e WhatsApp em destaque",
    authority: {
      eyebrow: "Conversao de campanha",
      title: "Uma pagina feita para uma oferta, uma acao e um canal.",
      body: "O modelo reduz navegacao e concentra energia em prova curta, beneficios e CTA repetido.",
      items: ["Oferta clara", "Prova curta", "CTA em todos os pontos"],
    },
    showcase: {
      title: "Blocos para trafego pago e WhatsApp",
      body: "A pagina ajuda a testar demanda sem construir um site gigante.",
      items: [
        { title: "Beneficio principal", body: "Headline direta e facil de entender no celular." },
        { title: "Regras da oferta", body: "Evita duvida e protege a equipe comercial." },
        { title: "FAQ curto", body: "Remove objecoes antes do clique." },
      ],
    },
    socialProof: {
      title: "Prova rapida",
      quote: "Modelo de depoimento curto para reforcar confianca sem quebrar o ritmo da campanha.",
      source: "Espaco para prova ou garantia de clareza",
    },
    localTrust: {
      eyebrow: "Lead local",
      title: "Contato, regra e proximo passo sempre visiveis.",
      body: "A estrutura funciona para mutirao, avaliacao inicial ou campanha sazonal.",
      items: ["Oferta com regras", "WhatsApp fixo", "Medicao de interesse"],
    },
    finalCta: {
      title: "Feche com uma acao sem distracao.",
      body: "O CTA final repete a oferta e leva direto para o WhatsApp.",
    },
  },
  "clinica-saude-familiar": {
    motion: "direct",
    visualFocus: "familia, prevencao e confianca de bairro",
    authority: {
      eyebrow: "Cuidado recorrente",
      title: "Uma clinica local com cara humana e organizada.",
      body: "O modelo valoriza atendimento familiar, prevencao, rotina e proximidade sem parecer frio.",
      items: ["Servicos por idade", "Prevencao", "Recepcao acessivel"],
    },
    showcase: {
      title: "Cuidado para a rotina da familia",
      body: "Blocos mostram consultas, exames simples e acompanhamento sem confundir o paciente.",
      items: [
        { title: "Criancas e adultos", body: "Organiza demandas de varias idades." },
        { title: "Prevencao", body: "Valoriza check-ups e acompanhamento." },
        { title: "Recepcao local", body: "WhatsApp, horario e endereco sempre acessiveis." },
      ],
    },
    socialProof: {
      title: "Proximidade que gera escolha",
      quote: "Modelo de depoimento para destacar cuidado, atendimento humano e facilidade para agendar.",
      source: "Espaco para avaliacoes da comunidade",
    },
    localTrust: {
      eyebrow: "Bairro e familia",
      title: "Endereco, horario e equipe conhecidos no centro da decisao.",
      body: "A pagina reforca que a clinica esta perto e resolve demandas recorrentes.",
      items: ["Endereco claro", "Horarios", "Atendimento familiar"],
    },
    finalCta: {
      title: "Convide a familia para agendar com facilidade.",
      body: "O fechamento prioriza recepcao, proximidade e confianca local.",
    },
  },
};

const DEFAULT_ELITE_DETAILS: SiteTemplateEliteDetails = {
  motion: "clinical",
  visualFocus: "site profissional com conversao local",
  authority: {
    eyebrow: "Autoridade",
    title: "Estrutura pronta para gerar confianca antes do contato.",
    body: "O modelo combina apresentacao, servicos, prova e CTA de WhatsApp em uma jornada clara.",
    items: ["Oferta clara", "Prova social", "Contato sem friccao"],
  },
  showcase: {
    title: "Blocos comerciais editaveis",
    body: "Cada area da pagina ajuda o visitante a entender valor e proximo passo.",
    items: [
      { title: "Servicos", body: "Procedimentos organizados em linguagem simples." },
      { title: "Confianca", body: "Sinais de prova, equipe e localizacao." },
      { title: "Conversao", body: "CTA visivel para WhatsApp ou agendamento." },
    ],
  },
  socialProof: {
    title: "Prova social",
    quote: "Modelo de depoimento para destacar confianca e clareza no atendimento.",
    source: "Espaco para avaliacoes reais",
  },
  localTrust: {
    eyebrow: "Local",
    title: "Cidade, mapa e contato juntos.",
    body: "A estrutura facilita a decisao de quem procura uma clinica perto.",
    items: ["Cidade em destaque", "Mapa", "WhatsApp"],
  },
  finalCta: {
    title: "Leve o visitante para o proximo passo.",
    body: "O fechamento da pagina reforca confianca e convida para uma conversa.",
  },
};

export function getSiteTemplateEliteDetails(template: Pick<SiteTemplate, "slug">): SiteTemplateEliteDetails {
  return SITE_TEMPLATE_ELITE_DETAILS[template.slug] ?? DEFAULT_ELITE_DETAILS;
}

export const SITE_TEMPLATES: SiteTemplate[] = [
  {
    slug: "clinica-odontologica-premium",
    name: "Clinica Odontologica Premium",
    shortName: "Odonto Premium",
    niche: "Odontologia",
    style: "Autoridade, estetica e alto valor",
    offerLane: "website_seo",
    headline: "Um site premium para transformar busca local em consultas qualificadas.",
    subheadline:
      "Estrutura pensada para implantes, estetica dental, harmonizacao e tratamentos de maior ticket com WhatsApp sempre visivel.",
    outcome: "Mais confianca antes do primeiro contato.",
    heroImage: DEFAULT_HERO_IMAGE,
    palette: {
      primary: "#0f766e",
      secondary: "#115e59",
      accent: "#d97706",
      background: "#f7f7f2",
      surface: "#ffffff",
      text: "#1c1917",
      muted: "#57534e",
    },
    idealFor: ["clinicas com tratamentos premium", "dentistas especialistas", "implantodontia e estetica"],
    badges: ["SEO local", "WhatsApp fixo", "Prova social"],
    metrics: [
      { label: "Foco", value: "premium" },
      { label: "CTA", value: "WhatsApp" },
      { label: "Prova", value: "avaliacoes" },
    ],
    services: ["Implantes dentarios", "Clareamento", "Lentes de contato dental", "Harmonizacao facial"],
    sections: [
      {
        title: "Primeira dobra de alto valor",
        body: "Hero com promessa clara, especialidades e chamada direta para avaliacao pelo WhatsApp.",
      },
      {
        title: "Autoridade clinica",
        body: "Blocos para equipe, tecnologia, certificados, fotos da estrutura e tratamentos de referencia.",
      },
      {
        title: "Conversao local",
        body: "Mapa, cidade, bairro, prova social e perguntas que reduzem objecoes antes do contato.",
      },
    ],
    trustSignals: ["Google Reviews em destaque", "Equipe e CRO visiveis", "Mapa e bairro no primeiro scroll"],
    conversionHooks: ["Agendar avaliacao", "Enviar duvida no WhatsApp", "Ver tratamentos premium"],
    faqs: [
      {
        question: "Serve para clinicas que cobram tratamentos de maior valor?",
        answer: "Sim. O layout prioriza confianca, autoridade e prova antes do CTA.",
      },
      {
        question: "Da para adaptar para outra cidade?",
        answer: "Sim. O texto foi feito para SEO local com cidade, bairro e servicos editaveis.",
      },
    ],
  },
  {
    slug: "clinica-odontologica-popular",
    name: "Clinica Odontologica Popular",
    shortName: "Odonto Popular",
    niche: "Odontologia",
    style: "Rapido, acessivel e direto",
    offerLane: "conversion_landing",
    headline: "Um site simples e direto para pacientes chamarem no WhatsApp sem friccao.",
    subheadline:
      "Modelo focado em limpeza, avaliacao, urgencia odontologica e tratamentos populares com CTA de contato em todos os blocos.",
    outcome: "Mais chamadas pelo WhatsApp com explicacao simples.",
    heroImage: DEFAULT_HERO_IMAGE,
    palette: {
      primary: "#2563eb",
      secondary: "#0f766e",
      accent: "#f97316",
      background: "#f8fafc",
      surface: "#ffffff",
      text: "#111827",
      muted: "#4b5563",
    },
    idealFor: ["clinicas populares", "unidades de alto volume", "atendimento por WhatsApp"],
    badges: ["Contato rapido", "Servicos claros", "Localizacao forte"],
    metrics: [
      { label: "Foco", value: "volume" },
      { label: "CTA", value: "chamar" },
      { label: "Oferta", value: "avaliacao" },
    ],
    services: ["Limpeza dental", "Restauracao", "Extracao", "Avaliacao odontologica"],
    sections: [
      {
        title: "Servico e preco percebido",
        body: "Cards objetivos para o paciente entender rapidamente o que a clinica faz.",
      },
      {
        title: "Urgencia sem exagero",
        body: "Bloco para dor, emergencia e atendimento rapido com linguagem responsavel.",
      },
      {
        title: "Contato acima de tudo",
        body: "WhatsApp, endereco, horario e mapa aparecem sem obrigar o visitante a procurar.",
      },
    ],
    trustSignals: ["Horario de funcionamento", "Endereco claro", "Atendimento por ordem de prioridade"],
    conversionHooks: ["Chamar agora", "Pedir avaliacao", "Ver como chegar"],
    faqs: [
      {
        question: "Esse modelo serve para clinica com varios procedimentos?",
        answer: "Serve. A pagina organiza os principais servicos sem deixar o paciente perdido.",
      },
      {
        question: "Tem foco em SEO?",
        answer: "Sim. A estrutura usa termos locais e servicos buscados por pacientes.",
      },
    ],
  },
  {
    slug: "estetica-facial-moderna",
    name: "Estetica Facial Moderna",
    shortName: "Estetica Moderna",
    niche: "Estetica",
    style: "Visual, aspiracional e confiavel",
    offerLane: "website_seo",
    headline: "Uma vitrine moderna para procedimentos esteticos com agenda pelo WhatsApp.",
    subheadline:
      "Ideal para botox, bioestimuladores, limpeza de pele e protocolos faciais com prova social e explicacao elegante.",
    outcome: "Mais desejo com orientacao responsavel.",
    heroImage: DEFAULT_HERO_IMAGE,
    palette: {
      primary: "#be123c",
      secondary: "#9f1239",
      accent: "#0891b2",
      background: "#fff7f7",
      surface: "#ffffff",
      text: "#18181b",
      muted: "#52525b",
    },
    idealFor: ["clinicas de estetica", "harmonizacao facial", "procedimentos recorrentes"],
    badges: ["Agenda rapida", "Antes e depois", "Protocolos"],
    metrics: [
      { label: "Foco", value: "desejo" },
      { label: "CTA", value: "avaliar" },
      { label: "Tom", value: "elegante" },
    ],
    services: ["Botox", "Bioestimulador", "Limpeza de pele", "Preenchimento"],
    sections: [
      {
        title: "Tratamentos com contexto",
        body: "Cada procedimento tem beneficio, indicacao e CTA para avaliacao profissional.",
      },
      {
        title: "Galeria controlada",
        body: "Espaco para fotos reais, depoimentos e provas sem promessas exageradas.",
      },
      {
        title: "Agenda recorrente",
        body: "Chamada para retorno, manutencao e acompanhamento no WhatsApp.",
      },
    ],
    trustSignals: ["Profissional responsavel", "Orientacao pre-procedimento", "Depoimentos curtos"],
    conversionHooks: ["Quero avaliar meu caso", "Ver procedimentos", "Falar com especialista"],
    faqs: [
      {
        question: "Da para usar sem antes e depois?",
        answer: "Da. O template tambem funciona com textos educativos e depoimentos.",
      },
      {
        question: "Evita promessas arriscadas?",
        answer: "Sim. A copy fala em avaliacao e possibilidade, nao em resultado garantido.",
      },
    ],
  },
  {
    slug: "dermatologia-premium",
    name: "Dermatologia Premium",
    shortName: "Dermato Premium",
    niche: "Dermatologia",
    style: "Clinico, elegante e tecnico",
    offerLane: "audit",
    headline: "Site de dermatologia com autoridade medica e conversao limpa.",
    subheadline:
      "Organiza consultas, tratamentos esteticos, tecnologia e orientacoes com visual sobrio e confiavel.",
    outcome: "Mais autoridade para pacientes pesquisando antes de marcar.",
    heroImage: DEFAULT_HERO_IMAGE,
    palette: {
      primary: "#7c3aed",
      secondary: "#0f766e",
      accent: "#f59e0b",
      background: "#fafaf9",
      surface: "#ffffff",
      text: "#1f2937",
      muted: "#4b5563",
    },
    idealFor: ["dermatologistas", "clinicas premium", "procedimentos esteticos e clinicos"],
    badges: ["Autoridade medica", "Consulta", "Tecnologia"],
    metrics: [
      { label: "Foco", value: "confianca" },
      { label: "CTA", value: "consulta" },
      { label: "Tom", value: "medico" },
    ],
    services: ["Dermatologia clinica", "Laser", "Acne", "Rejuvenescimento"],
    sections: [
      {
        title: "Medicina e estetica separadas",
        body: "A pagina evita confusao e organiza linhas de atendimento por intencao do paciente.",
      },
      {
        title: "Perfil do especialista",
        body: "Curriculo, areas de atuacao e diferenciais aparecem antes das chamadas de venda.",
      },
      {
        title: "FAQ de seguranca",
        body: "Perguntas sobre avaliacao, indicacoes e acompanhamento reduzem medo e incerteza.",
      },
    ],
    trustSignals: ["CRM/RQE visivel", "Protocolos explicados", "Localizacao e estrutura"],
    conversionHooks: ["Marcar consulta", "Tirar duvida", "Conhecer tratamentos"],
    faqs: [
      {
        question: "Serve para dermatologia clinica e estetica?",
        answer: "Sim. O modelo separa as duas jornadas e melhora a leitura do paciente.",
      },
      {
        question: "Pode ter conteudo educativo?",
        answer: "Pode. Ha blocos prontos para guias curtos e perguntas frequentes.",
      },
    ],
  },
  {
    slug: "psicologia-humanizada",
    name: "Psicologia Humanizada",
    shortName: "Psicologia",
    niche: "Psicologia",
    style: "Acolhedor, discreto e etico",
    offerLane: "website_seo",
    headline: "Um site acolhedor para transformar pesquisa local em primeiro contato.",
    subheadline:
      "Modelo para psicologos e clinicas de terapia com linguagem cuidadosa, privacidade e chamada leve para agendamento.",
    outcome: "Mais seguranca para quem ainda esta decidindo pedir ajuda.",
    heroImage: DEFAULT_HERO_IMAGE,
    palette: {
      primary: "#3f6212",
      secondary: "#0f766e",
      accent: "#ca8a04",
      background: "#f7f9f2",
      surface: "#ffffff",
      text: "#1c1917",
      muted: "#57534e",
    },
    idealFor: ["psicologos", "clinicas de terapia", "atendimento online e presencial"],
    badges: ["Acolhimento", "Privacidade", "Agendamento"],
    metrics: [
      { label: "Foco", value: "confia" },
      { label: "CTA", value: "conversar" },
      { label: "Tom", value: "calmo" },
    ],
    services: ["Terapia individual", "Terapia online", "Ansiedade", "Acompanhamento"],
    sections: [
      {
        title: "Tom seguro",
        body: "Texto cuidadoso para nao soar agressivo nem comercial demais para saude mental.",
      },
      {
        title: "Modalidades claras",
        body: "Presencial, online, publico atendido e formas de agendamento ficam bem separadas.",
      },
      {
        title: "Privacidade no centro",
        body: "Blocos de sigilo, abordagem e primeiros passos ajudam a reduzir ansiedade.",
      },
    ],
    trustSignals: ["CRP visivel", "Sigilo profissional", "Primeiro contato sem pressao"],
    conversionHooks: ["Enviar mensagem", "Entender atendimento", "Agendar primeiro contato"],
    faqs: [
      {
        question: "O texto e discreto?",
        answer: "Sim. A pagina evita pressao e prioriza acolhimento e privacidade.",
      },
      {
        question: "Funciona para atendimento online?",
        answer: "Sim. O template tem secoes para atendimento online e presencial.",
      },
    ],
  },
  {
    slug: "fisioterapia-reabilitacao",
    name: "Fisioterapia e Reabilitacao",
    shortName: "Fisioterapia",
    niche: "Fisioterapia",
    style: "Tecnico, ativo e orientado a resultado",
    offerLane: "website_seo",
    headline: "Site para fisioterapia com foco em recuperacao, dor e agendamento local.",
    subheadline:
      "Organiza especialidades, equipamentos, equipe e planos de tratamento para pacientes que buscam solucao perto de casa.",
    outcome: "Mais clareza para quem procura alivio e reabilitacao.",
    heroImage: DEFAULT_HERO_IMAGE,
    palette: {
      primary: "#047857",
      secondary: "#1d4ed8",
      accent: "#ea580c",
      background: "#f3fbf8",
      surface: "#ffffff",
      text: "#172019",
      muted: "#4b6357",
    },
    idealFor: ["fisioterapia ortopedica", "pilates clinico", "reabilitacao"],
    badges: ["Dor", "Movimento", "Plano de cuidado"],
    metrics: [
      { label: "Foco", value: "recuperar" },
      { label: "CTA", value: "avaliar" },
      { label: "Busca", value: "local" },
    ],
    services: ["Dor lombar", "Pos-operatorio", "Pilates clinico", "Fisioterapia esportiva"],
    sections: [
      {
        title: "Problemas por sintoma",
        body: "Paciente entra por dor ou limitacao, entao os blocos partem desse contexto.",
      },
      {
        title: "Plano de tratamento",
        body: "Explica avaliacao, frequencia, acompanhamento e retorno sem prometer cura.",
      },
      {
        title: "Estrutura visivel",
        body: "Equipamentos, salas, endereco e acesso aumentam confianca no atendimento presencial.",
      },
    ],
    trustSignals: ["Crefito visivel", "Plano individual", "Estrutura e equipamentos"],
    conversionHooks: ["Agendar avaliacao", "Falar sobre dor", "Ver modalidades"],
    faqs: [
      {
        question: "Serve para pilates e fisio juntos?",
        answer: "Sim. O layout separa reabilitacao, prevencao e condicionamento.",
      },
      {
        question: "Pode usar para clinica com convenio?",
        answer: "Pode. Ha espaco para explicar formas de atendimento e orientacoes.",
      },
    ],
  },
  {
    slug: "nutricionista-autoridade",
    name: "Nutricionista Autoridade",
    shortName: "Nutricao",
    niche: "Nutricao",
    style: "Educativo, limpo e especialista",
    offerLane: "website_seo",
    headline: "Site para nutricionista que educa, gera confianca e leva ao agendamento.",
    subheadline:
      "Modelo para nutricao clinica, esportiva e emagrecimento com conteudo organizado e CTA de consulta.",
    outcome: "Mais autoridade para quem compara profissionais.",
    heroImage: DEFAULT_HERO_IMAGE,
    palette: {
      primary: "#16a34a",
      secondary: "#0891b2",
      accent: "#f59e0b",
      background: "#f7fff5",
      surface: "#ffffff",
      text: "#172019",
      muted: "#4b6357",
    },
    idealFor: ["nutricionistas", "emagrecimento", "nutricao esportiva"],
    badges: ["Conteudo", "Consulta", "Plano alimentar"],
    metrics: [
      { label: "Foco", value: "educar" },
      { label: "CTA", value: "consulta" },
      { label: "Tom", value: "leve" },
    ],
    services: ["Emagrecimento", "Nutricao esportiva", "Saude intestinal", "Reeducacao alimentar"],
    sections: [
      {
        title: "Metodo claro",
        body: "Mostra como funciona avaliacao, plano, acompanhamento e retorno.",
      },
      {
        title: "Conteudo que vende sem pressionar",
        body: "Blocos educativos posicionam o profissional como referencia local.",
      },
      {
        title: "Jornada simples",
        body: "O visitante entende se o atendimento e para ele e chama pelo WhatsApp.",
      },
    ],
    trustSignals: ["CRN visivel", "Metodo de acompanhamento", "Resultados tratados com responsabilidade"],
    conversionHooks: ["Agendar consulta", "Entender o metodo", "Chamar no WhatsApp"],
    faqs: [
      {
        question: "O modelo serve para nutricionista online?",
        answer: "Sim. Ha blocos para consulta online, presencial e acompanhamento.",
      },
      {
        question: "Evita promessa de emagrecimento garantido?",
        answer: "Sim. A comunicacao fala em acompanhamento e plano individual.",
      },
    ],
  },
  {
    slug: "clinica-medica-multiespecialidade",
    name: "Clinica Medica Multiespecialidade",
    shortName: "Multiespecialidade",
    niche: "Clinica medica",
    style: "Operacional, organizado e institucional",
    offerLane: "website_seo",
    headline: "Um site institucional para organizar especialidades e facilitar agendamentos.",
    subheadline:
      "Modelo para clinicas com varios profissionais, unidades e horarios, mantendo WhatsApp e mapa sempre acessiveis.",
    outcome: "Menos duvida para o paciente escolher o atendimento certo.",
    heroImage: DEFAULT_HERO_IMAGE,
    palette: {
      primary: "#0369a1",
      secondary: "#0f766e",
      accent: "#c2410c",
      background: "#f5f9fb",
      surface: "#ffffff",
      text: "#111827",
      muted: "#4b5563",
    },
    idealFor: ["clinicas com varias especialidades", "unidades locais", "atendimento por recepcao"],
    badges: ["Especialidades", "Unidades", "Agenda"],
    metrics: [
      { label: "Foco", value: "organizar" },
      { label: "CTA", value: "agenda" },
      { label: "Uso", value: "institucional" },
    ],
    services: ["Clinico geral", "Pediatria", "Ginecologia", "Exames"],
    sections: [
      {
        title: "Especialidades escaneaveis",
        body: "Paciente encontra rapidamente medico, servico e proximo passo.",
      },
      {
        title: "Unidades e horarios",
        body: "Informacao operacional vem antes da duvida virar abandono.",
      },
      {
        title: "Recepcao conectada",
        body: "WhatsApp aparece como caminho principal para triagem e agendamento.",
      },
    ],
    trustSignals: ["Lista de especialidades", "Equipe medica", "Endereco das unidades"],
    conversionHooks: ["Escolher especialidade", "Chamar recepcao", "Ver unidades"],
    faqs: [
      {
        question: "Serve para varias unidades?",
        answer: "Sim. O template tem bloco especifico para enderecos, horarios e contato.",
      },
      {
        question: "Pode destacar medicos?",
        answer: "Pode. A estrutura inclui equipe, especialidade e agenda por profissional.",
      },
    ],
  },
  {
    slug: "consultorio-especialista",
    name: "Consultorio de Especialista",
    shortName: "Especialista",
    niche: "Especialistas",
    style: "Pessoal, tecnico e confiavel",
    offerLane: "audit",
    headline: "Um site pessoal para especialista explicar valor e receber pacientes certos.",
    subheadline:
      "Perfeito para profissionais que precisam mostrar experiencia, abordagem, casos atendidos e proximo passo com sobriedade.",
    outcome: "Melhor encaixe entre paciente e profissional.",
    heroImage: DEFAULT_HERO_IMAGE,
    palette: {
      primary: "#4338ca",
      secondary: "#0f766e",
      accent: "#b45309",
      background: "#f8f7ff",
      surface: "#ffffff",
      text: "#1f2937",
      muted: "#4b5563",
    },
    idealFor: ["medicos especialistas", "dentistas especialistas", "profissionais premium"],
    badges: ["Perfil profissional", "Autoridade", "Agenda"],
    metrics: [
      { label: "Foco", value: "perfil" },
      { label: "CTA", value: "consulta" },
      { label: "Prova", value: "curriculo" },
    ],
    services: ["Consulta especializada", "Segunda opiniao", "Acompanhamento", "Procedimentos"],
    sections: [
      {
        title: "Historia profissional",
        body: "A pagina vende autoridade sem depender de slogans genericos.",
      },
      {
        title: "Casos e indicacoes",
        body: "Explica quando procurar o especialista e como funciona a primeira consulta.",
      },
      {
        title: "Proximo passo claro",
        body: "CTA discreto para agendar, tirar duvida ou enviar exames pelo canal correto.",
      },
    ],
    trustSignals: ["Registro profissional", "Formacao e areas de atuacao", "Perguntas clinicas comuns"],
    conversionHooks: ["Agendar consulta", "Enviar duvida", "Conhecer abordagem"],
    faqs: [
      {
        question: "Esse modelo e mais pessoal?",
        answer: "Sim. Ele destaca o profissional e a tomada de decisao do paciente.",
      },
      {
        question: "Funciona para varias areas?",
        answer: "Funciona para qualquer especialidade que dependa de autoridade e confianca.",
      },
    ],
  },
  {
    slug: "landing-page-conversao-rapida",
    name: "Landing Page de Conversao Rapida",
    shortName: "Conversao Rapida",
    niche: "Campanhas",
    style: "Direto, comercial e mensuravel",
    offerLane: "conversion_landing",
    headline: "Uma pagina de campanha para testar oferta, captar WhatsApp e vender rapido.",
    subheadline:
      "Feita para trafego pago, mutiroes, avaliacao inicial, campanha sazonal ou oferta de agenda limitada sem virar site gigante.",
    outcome: "Validar uma oferta antes de construir uma operacao maior.",
    heroImage: DEFAULT_HERO_IMAGE,
    palette: {
      primary: "#ea580c",
      secondary: "#0f766e",
      accent: "#2563eb",
      background: "#fffaf4",
      surface: "#ffffff",
      text: "#1c1917",
      muted: "#57534e",
    },
    idealFor: ["campanhas de WhatsApp", "trafego pago", "oferta especifica"],
    badges: ["Rapida", "Mensuravel", "CTA forte"],
    metrics: [
      { label: "Foco", value: "lead" },
      { label: "CTA", value: "WhatsApp" },
      { label: "Uso", value: "campanha" },
    ],
    services: ["Avaliacao inicial", "Campanha de clareamento", "Check-up", "Mutirao"],
    sections: [
      {
        title: "Oferta unica",
        body: "A pagina evita dispersao e concentra atencao em uma acao.",
      },
      {
        title: "Prova e objecoes",
        body: "Blocos curtos respondem duvidas antes do clique no WhatsApp.",
      },
      {
        title: "Tracking comercial",
        body: "Estrutura pensada para medir clique, interesse e origem da campanha.",
      },
    ],
    trustSignals: ["Oferta com regras claras", "Contato direto", "FAQ curto"],
    conversionHooks: ["Quero participar", "Chamar no WhatsApp", "Ver detalhes"],
    faqs: [
      {
        question: "Serve para campanha temporaria?",
        answer: "Sim. O modelo e ideal para testar uma oferta ou agenda especifica.",
      },
      {
        question: "Da para medir interesse?",
        answer: "Sim. Ele foi pensado para clicks, origem e selecao de template.",
      },
    ],
  },
  {
    slug: "clinica-saude-familiar",
    name: "Clinica Saude Familiar",
    shortName: "Saude Familiar",
    niche: "Clinica familiar",
    style: "Proximo, confiavel e local",
    offerLane: "website_seo",
    headline: "Um site local para familias encontrarem a clinica e chamarem no WhatsApp.",
    subheadline:
      "Modelo para clinicas de bairro que dependem de confianca, localizacao, atendimento humano e agenda simples.",
    outcome: "Mais presenca local sem parecer frio ou corporativo.",
    heroImage: DEFAULT_HERO_IMAGE,
    palette: {
      primary: "#0d9488",
      secondary: "#2563eb",
      accent: "#f97316",
      background: "#f4fbfa",
      surface: "#ffffff",
      text: "#172019",
      muted: "#4b6357",
    },
    idealFor: ["clinicas de bairro", "atendimento familiar", "consultorios locais"],
    badges: ["Bairro", "Familia", "WhatsApp"],
    metrics: [
      { label: "Foco", value: "local" },
      { label: "CTA", value: "recepcao" },
      { label: "Tom", value: "humano" },
    ],
    services: ["Atendimento familiar", "Consultas", "Exames simples", "Acompanhamento"],
    sections: [
      {
        title: "Confia no bairro",
        body: "A pagina mostra proximidade, endereco, horarios e canais de contato.",
      },
      {
        title: "Servicos sem confusao",
        body: "Organiza atendimentos principais em linguagem simples para o paciente.",
      },
      {
        title: "Recepcao facil",
        body: "O WhatsApp aparece como ponte natural para tirar duvidas e agendar.",
      },
    ],
    trustSignals: ["Endereco em destaque", "Equipe conhecida", "Horarios claros"],
    conversionHooks: ["Falar com a recepcao", "Ver endereco", "Agendar atendimento"],
    faqs: [
      {
        question: "Esse modelo e bom para clinica pequena?",
        answer: "Sim. Ele valoriza proximidade, confianca local e contato facil.",
      },
      {
        question: "Pode ser usado para varias especialidades?",
        answer: "Pode. Os blocos de servicos sao editaveis e escaneaveis.",
      },
    ],
  },
];

export function getSiteTemplateBySlug(slug: string | null | undefined) {
  const normalizedSlug = String(slug || "").trim();
  return SITE_TEMPLATES.find((template) => template.slug === normalizedSlug) ?? null;
}

export function buildSiteTemplatePreviewPath(
  template: SiteTemplate,
  params?: {
    clinic?: string | null;
    city?: string | null;
    whatsapp?: string | null;
  },
) {
  const query = new URLSearchParams();
  if (params?.clinic) query.set("clinic", params.clinic);
  if (params?.city) query.set("city", params.city);
  if (params?.whatsapp) query.set("whatsapp", params.whatsapp);
  const suffix = query.toString();
  return `${SITE_TEMPLATE_CATALOG_PATH}/${template.slug}${suffix ? `?${suffix}` : ""}`;
}

export function buildSiteTemplateSectionPath(
  template: SiteTemplate,
  section: SiteTemplateSectionKey,
  params?: {
    clinic?: string | null;
    city?: string | null;
    whatsapp?: string | null;
  },
) {
  const query = new URLSearchParams();
  if (params?.clinic) query.set("clinic", params.clinic);
  if (params?.city) query.set("city", params.city);
  if (params?.whatsapp) query.set("whatsapp", params.whatsapp);
  const suffix = query.toString();
  return `${SITE_TEMPLATE_CATALOG_PATH}/${template.slug}/${section}${suffix ? `?${suffix}` : ""}`;
}

export function buildSiteTemplateSelectionSnapshot(
  template: SiteTemplate,
  selectedAt: string,
  params?: {
    clinic?: string | null;
    city?: string | null;
    whatsapp?: string | null;
  },
) {
  return {
    version: SITE_TEMPLATE_LIBRARY_VERSION,
    selected_template_slug: template.slug,
    selected_template_name: template.name,
    offer_lane: template.offerLane,
    selected_at: selectedAt,
    source: "adm_site_template_studio",
    public_catalog_path: SITE_TEMPLATE_CATALOG_PATH,
    public_preview_path: `${SITE_TEMPLATE_CATALOG_PATH}/${template.slug}`,
    personalized_preview_path: buildSiteTemplatePreviewPath(template, params),
  };
}
