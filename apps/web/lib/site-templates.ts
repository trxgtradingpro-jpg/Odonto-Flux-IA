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

export const SITE_TEMPLATE_LIBRARY_VERSION = "2026.05.30-initial-10";
export const SITE_TEMPLATE_CATALOG_PATH = "/modelos-sites";

const DEFAULT_HERO_IMAGE = "/images/dental-floss-smile-background.png";

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
