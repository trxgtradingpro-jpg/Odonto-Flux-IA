import type { Metadata } from "next";

import { LegalPageShell } from "@/components/marketing/legal-page-shell";
import { BRAND_DESCRIPTION, BRAND_LEGAL_ENTITY, BRAND_NAME, BRAND_SUPPORT_EMAIL } from "@/lib/brand";

const UPDATED_AT = "16 de maio de 2026";
const VERSION = "v1.0";

const facts = [
  {
    label: "Fornecedor da plataforma",
    value: BRAND_LEGAL_ENTITY,
  },
  {
    label: "Suporte oficial",
    value: BRAND_SUPPORT_EMAIL,
  },
];

const sections = [
  {
    id: "aceite",
    title: "1. Aceite e vinculacao",
    paragraphs: [
      `Os presentes Termos de Uso regulam o acesso ao site, as demonstracoes, os ambientes administrativos e a plataforma SaaS da ${BRAND_NAME}.`,
      "Ao navegar no site, solicitar uma demonstracao, criar conta, acessar qualquer ambiente autenticado ou utilizar recursos da plataforma, o usuario declara que leu, compreendeu e concorda com estes termos, com a Politica de Privacidade e com os documentos comerciais e contratuais aplicaveis.",
    ],
  },
  {
    id: "objeto",
    title: "2. Objeto do servico",
    paragraphs: [
      `A ${BRAND_NAME} oferece software, automacoes, recursos de inteligencia artificial, integracoes, mensageria e ferramentas de operacao para clinicas e equipes que desejam organizar atendimento, qualificacao, agenda, recuperacao de oportunidades, governanca operacional e relacao com pacientes e leads.`,
      "O escopo efetivo do servico depende do plano contratado, da proposta comercial aceita, dos modulos habilitados e das integracoes configuradas em cada ambiente.",
    ],
  },
  {
    id: "cadastro",
    title: "3. Cadastro, credenciais e responsabilidade do usuario",
    paragraphs: [
      "O cliente e seus usuarios devem fornecer informacoes verdadeiras, atualizadas e completas, manter sigilo sobre credenciais e limitar o acesso a pessoas autorizadas.",
      "Cada conta responde pelas acoes realizadas com suas credenciais, inclusive configuracoes, envios, aprovacoes, integracoes, exportacoes, automacoes e alteracoes em registros operacionais.",
    ],
    bullets: [
      "E proibido compartilhar senha de forma insegura ou manter contas genericas sem governanca adequada.",
      "O cliente deve revogar acessos de ex-colaboradores e atualizar perfis sempre que houver mudanca de funcao.",
      "A ClinicFlux AI pode exigir redefinicao de senha, dupla validacao, ajuste de permissoes ou revisao de acesso quando identificar risco operacional ou de seguranca.",
    ],
  },
  {
    id: "uso-permitido",
    title: "4. Uso permitido e condutas proibidas",
    paragraphs: [
      "A plataforma deve ser utilizada apenas para finalidades licitas, legitimas e compativeis com a operacao do cliente, observando LGPD, regras do setor de saude, termos de provedores terceiros e politicas de comunicacao aplicaveis.",
    ],
    bullets: [
      "Nao utilizar o sistema para spam, fraude, assedio, desinformacao, envio em massa irregular, conteudo discriminatorio, ilegal ou violador de direitos de terceiros.",
      "Nao tentar acessar areas restritas, contornar limites tecnicos, interferir em integridade, disponibilidade ou seguranca da plataforma.",
      "Nao usar a IA para gerar conteudos enganosos, promessas clinicas nao autorizadas, orientacoes medicas indevidas ou comunicacoes que contrariem dados oficialmente cadastrados.",
      "Nao inserir, exportar ou compartilhar dados sem base legal, autorizacao interna ou necessidade operacional legitima.",
    ],
  },
  {
    id: "integracoes",
    title: "5. Integracoes, WhatsApp e servicos de terceiros",
    paragraphs: [
      "Parte das funcionalidades depende de provedores terceiros, como servicos de nuvem, IA, mensageria, WhatsApp, e-mail, telefonia, faturamento e monitoramento.",
      "O cliente e responsavel por manter chaves, contas, aprovacoes, saldos, politicas, remetentes, templates e permissoes exigidas por esses provedores, bem como por respeitar suas regras de uso.",
    ],
    bullets: [
      "Falhas, bloqueios, recusas, limites de janela, indisponibilidades ou restricoes impostas por terceiros podem impactar entregas, respostas automaticas e integracoes.",
      "A ClinicFlux AI podera suspender integracoes inseguras, inconsistentes ou sem autorizacao valida sempre que houver risco tecnico, juridico ou reputacional.",
    ],
  },
  {
    id: "ia",
    title: "6. Recursos de inteligencia artificial",
    paragraphs: [
      "A plataforma pode utilizar modelos de IA para apoiar triagem, respostas, resumo de conversas, organizacao de contexto, qualificacao, sugestoes operacionais e aceleracao de tarefas.",
      "Esses recursos sao auxiliares e nao substituem julgamento clinico, decisao medica, avaliacao juridica, governanca do cliente nem revisao humana quando a situacao exigir controle adicional.",
    ],
    bullets: [
      "O cliente deve revisar configuracoes, fluxos, tom de voz, dados institucionais e permissoes antes de operar em producao.",
      "A ClinicFlux AI pode impor limites, filtros ou revisoes preventivas em automacoes sensiveis para reduzir risco de resposta inadequada.",
    ],
  },
  {
    id: "propriedade",
    title: "7. Propriedade intelectual",
    paragraphs: [
      `A plataforma, o codigo, o design, a arquitetura, os fluxos, a documentacao, a marca ${BRAND_NAME}, seus materiais comerciais e os elementos proprietarios associados pertencem a ClinicFlux AI ou a seus licenciadores.`,
      "Nenhum uso da plataforma transfere titularidade de propriedade intelectual ao cliente, salvo quando houver previsao expressa por escrito em contrato especifico.",
    ],
    bullets: [
      "O cliente mantem titularidade sobre os dados, materiais e conteudos legitimamente inseridos por ele na plataforma.",
      "E vedado copiar, sublicenciar, revender, desmontar, traduzir, distribuir ou explorar comercialmente o software sem autorizacao expressa.",
    ],
  },
  {
    id: "dados-confidencialidade",
    title: "8. Dados, confidencialidade e privacidade",
    paragraphs: [
      "As partes devem tratar informacoes confidenciais com cuidado compativel com sua sensibilidade, limitando acesso interno e evitando uso fora do objeto contratado.",
      `O tratamento de dados pessoais segue estes termos, a Politica de Privacidade, o contrato aplicavel e a legislacao vigente. Quando atuar como operadora, a ${BRAND_NAME} tratara dados conforme instrucao do cliente controlador e medidas de seguranca proporcionais ao servico.`,
    ],
  },
  {
    id: "disponibilidade",
    title: "9. Disponibilidade, manutencao e suporte",
    paragraphs: [
      "A ClinicFlux AI busca manter a plataforma estavel e segura, mas nao garante operacao absolutamente ininterrupta ou livre de falhas. Manutencoes, atualizacoes, incidentes, dependencia de terceiros e eventos fora de controle razoavel podem afetar disponibilidade ou desempenho.",
      `Chamados operacionais podem ser direcionados para ${BRAND_SUPPORT_EMAIL} ou pelos canais definidos em contrato, onboarding ou painel administrativo.`,
    ],
  },
  {
    id: "condicoes-comerciais",
    title: "10. Planos, cobranca e adimplencia",
    paragraphs: [
      "Valores, escopo, franquias, implantacao, condicoes de reajuste, prazos, renovacao, uso excedente e regras de cancelamento serao definidos na proposta comercial, no pedido, no contrato ou no plano efetivamente aceito.",
      "A inadimplencia, o uso em desacordo com o contrato ou o descumprimento material destes termos podem resultar em restricao de funcionalidades, bloqueio de integracoes, limitacao de suporte, suspensao ou encerramento do acesso, respeitadas as regras comerciais aplicaveis.",
    ],
  },
  {
    id: "suspensao",
    title: "11. Suspensao e encerramento",
    paragraphs: [
      "A ClinicFlux AI podera restringir ou suspender o acesso total ou parcial quando identificar risco a seguranca, fraude, uso abusivo, ordem legal, violacao contratual, inadimplencia relevante, incidente grave ou necessidade tecnica urgente.",
      "Encerrado o relacionamento, os dados poderao permanecer retidos pelo periodo necessario para obrigacoes legais, auditoria, seguranca, exercicio regular de direitos e rotinas de descarte previstas na Politica de Privacidade e no contrato.",
    ],
  },
  {
    id: "responsabilidade",
    title: "12. Limitacao de responsabilidade",
    paragraphs: [
      "Na extensao permitida pela lei, a ClinicFlux AI nao responde por lucros cessantes indiretos, danos reputacionais, perda de oportunidade, indisponibilidade causada por terceiros, uso indevido pelo cliente, erro de configuracao interna do cliente ou fatos fora de seu controle razoavel.",
      "A responsabilidade da ClinicFlux AI sera interpretada em conjunto com o contrato comercial aplicavel, com as garantias expressamente assumidas e com a participacao do cliente em suas proprias rotinas de governanca, revisao e seguranca.",
    ],
  },
  {
    id: "alteracoes",
    title: "13. Mudancas no produto e nos termos",
    paragraphs: [
      "A ClinicFlux AI pode evoluir, substituir, descontinuar ou reorganizar funcionalidades, fluxos, interfaces, integracoes, nomenclaturas e componentes de seguranca para manter qualidade, conformidade e sustentabilidade da plataforma.",
      "Sempre que estes termos forem alterados de forma relevante, a nova versao passara a valer a partir da publicacao nesta pagina ou da comunicacao feita por canais contratuais e operacionais apropriados.",
    ],
  },
  {
    id: "lei-foro",
    title: "14. Legislacao aplicavel e foro",
    paragraphs: [
      "Estes termos sao regidos pela legislacao brasileira. Eventuais controversias deverao observar, em primeiro lugar, o mecanismo de solucao previsto no contrato ou instrumento comercial aplicavel.",
      "Na ausencia de disposicao contratual especifica, as partes elegem o foro competente no Brasil admitido pela legislacao para discutir questoes decorrentes destes termos, sem prejuizo de medidas urgentes cabiveis.",
    ],
  },
  {
    id: "contato",
    title: "15. Contato",
    paragraphs: [
      `Duvidas sobre estes Termos de Uso, notificacoes contratuais e solicitacoes operacionais podem ser enviadas para ${BRAND_SUPPORT_EMAIL} ou pelos canais oficiais de atendimento divulgados pela ClinicFlux AI.`,
    ],
  },
] as const;

export const metadata: Metadata = {
  title: `Termos de Uso | ${BRAND_NAME}`,
  description: `${BRAND_DESCRIPTION} Consulte as regras de acesso, uso da plataforma, integracoes, IA, seguranca e responsabilidades contratuais.`,
};

export default function TermsOfUsePage() {
  return (
    <LegalPageShell
      eyebrow="Contrato de uso da plataforma"
      title={`Termos de Uso da ${BRAND_NAME}`}
      summary="Este documento organiza as regras de acesso, responsabilidades, limites de uso, integracoes, recursos de IA, suporte e relacao contratual esperada para operar a plataforma com seguranca e previsibilidade."
      updatedAt={UPDATED_AT}
      version={VERSION}
      facts={facts}
      sections={[...sections]}
      relatedLinks={[
        { href: "/politica-de-privacidade", label: "Ver Politica de Privacidade" },
        { href: "/apresentacao", label: "Ver demonstracao" },
      ]}
    />
  );
}
