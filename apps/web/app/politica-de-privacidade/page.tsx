import type { Metadata } from "next";

import { LegalPageShell } from "@/components/marketing/legal-page-shell";
import { BRAND_DESCRIPTION, BRAND_LEGAL_ENTITY, BRAND_NAME, BRAND_SUPPORT_EMAIL } from "@/lib/brand";

const UPDATED_AT = "16 de maio de 2026";
const VERSION = "v1.0";

const facts = [
  {
    label: "Responsavel pela plataforma",
    value: BRAND_LEGAL_ENTITY,
  },
  {
    label: "Canal principal",
    value: BRAND_SUPPORT_EMAIL,
  },
];

const sections = [
  {
    id: "escopo",
    title: "1. Escopo desta politica",
    paragraphs: [
      `Esta Politica de Privacidade descreve como a ${BRAND_NAME} coleta, utiliza, armazena, compartilha e protege dados pessoais tratados em seu site institucional, em suas demonstracoes, em seus canais comerciais e na plataforma SaaS oferecida a clinicas, consultorios, redes e equipes autorizadas.`,
      `O documento se aplica a visitantes do site, representantes de clientes, usuarios cadastrados, leads comerciais, parceiros e titulares cujos dados sejam tratados pela ${BRAND_NAME} em nome proprio ou por instrucao contratual de clientes.`,
    ],
  },
  {
    id: "papeis",
    title: "2. Papeis da ClinicFlux AI no tratamento de dados",
    paragraphs: [
      `Quando a ${BRAND_NAME} trata dados para administrar sua propria operacao comercial, financeira, contratual, antifraude, suporte, onboarding e marketing institucional, ela atua como controladora desses dados.`,
      `Quando uma clinica cliente utiliza a plataforma para operar atendimento, agenda, leads, pacientes, documentos, automacoes, historicos de conversa e fluxos internos, a clinica contratante atua como controladora e a ${BRAND_NAME} atua como operadora, seguindo o contrato, as configuracoes habilitadas e as instrucoes documentadas do cliente.`,
    ],
    bullets: [
      "Dados de visitantes, representantes comerciais, administradores de conta e faturamento podem ser tratados diretamente pela ClinicFlux AI.",
      "Dados de pacientes, leads e conversas recebidos pela clinica dentro da plataforma sao tratados em nome da clinica contratante, salvo quando a lei determinar de outro modo.",
    ],
  },
  {
    id: "dados-coletados",
    title: "3. Categorias de dados tratados",
    paragraphs: [
      "Podemos tratar diferentes categorias de dados conforme o canal utilizado, o modulo contratado e o perfil do usuario.",
    ],
    bullets: [
      "Dados cadastrais e de contato: nome, e-mail, telefone, cargo, empresa, unidade, perfil de acesso e preferencias de contato.",
      "Dados de autenticacao e seguranca: senha criptografada, tentativas de login, IP, data e hora de acesso, navegador, dispositivo e trilhas de auditoria.",
      "Dados operacionais de clinicas clientes: agendas, profissionais, servicos, leads, pacientes, mensagens de WhatsApp, documentos, consentimentos, observacoes e registros de atendimento.",
      "Dados de integracao: identificadores de contas de WhatsApp, tokens tecnicos, webhooks, chaves de servico e metadados necessarios para integracoes autorizadas.",
      "Dados comerciais e de suporte: historico de propostas, solicitacoes, tickets, demonstracoes, aceite de termos, faturamento e comprovacoes de atendimento.",
    ],
  },
  {
    id: "finalidades",
    title: "4. Finalidades e bases legais",
    paragraphs: [
      `A ${BRAND_NAME} trata dados para finalidades legitimas, especificas e compativeis com a operacao da plataforma, observando a Lei Geral de Protecao de Dados Pessoais (Lei no 13.709/2018) e demais normas aplicaveis.`,
    ],
    bullets: [
      "Executar contrato, proposta, pedido, onboarding, suporte e operacao da plataforma.",
      "Permitir autenticacao, gestao de permissao, auditoria, seguranca e prevencao a fraude.",
      "Viabilizar atendimento automatizado, qualificacao, agenda, recuperacao de oportunidades e fluxos operacionais autorizados pelos clientes.",
      "Cumprir obrigacoes legais, regulatorias, fiscais, contabeis e de guarda de evidencias.",
      "Exercer direitos em processos judiciais, administrativos ou arbitrais.",
      "Realizar comunicacoes institucionais, comerciais e educativas relacionadas ao produto, respeitando consentimento quando exigido e opt-out quando aplicavel.",
    ],
  },
  {
    id: "compartilhamento",
    title: "5. Compartilhamento de dados",
    paragraphs: [
      "Os dados podem ser compartilhados apenas na medida necessaria para entregar a plataforma, cumprir obrigacoes legais ou viabilizar servicos integrados autorizados.",
    ],
    bullets: [
      "Provedores de infraestrutura, hospedagem, monitoramento, backup, autenticacao e seguranca.",
      "Provedores de mensageria, WhatsApp, e-mail, notificacao, telefonia e comunicacao operacional.",
      "Provedores de inteligencia artificial, quando habilitados para apoiar fluxos do produto e sujeitos a controles contratuais e tecnicos.",
      "Processadores de pagamento, emissores fiscais, assessorias juridicas, auditorias e autoridades publicas quando necessario.",
      "Clientes controladores, quando a solicitacao partir da clinica contratante e envolver dados tratados em nome dela.",
    ],
  },
  {
    id: "transferencias",
    title: "6. Transferencias internacionais",
    paragraphs: [
      "Parte da infraestrutura e de alguns suboperadores pode estar localizada fora do Brasil. Nesses casos, a ClinicFlux AI adota medidas contratuais, organizacionais e tecnicas para assegurar nivel adequado de protecao e uso compativel com esta politica.",
      "Ao utilizar recursos de IA, mensageria e nuvem, o cliente reconhece que pode haver tratamento transfronteirico limitado ao estritamente necessario para a prestacao do servico contratado.",
    ],
  },
  {
    id: "retencao",
    title: "7. Retencao e descarte",
    paragraphs: [
      "Os dados sao mantidos apenas pelo tempo necessario para cumprir as finalidades informadas, atender obrigacoes legais, preservar trilhas de seguranca, executar contrato e resguardar exercicio regular de direitos.",
      "O tempo de retencao pode variar por modulo, evento de seguranca, configuracao da clinica cliente, rotina de backup e obrigacao fiscal ou regulatoria aplicavel.",
    ],
    bullets: [
      "Contas inativas, eventos de auditoria e logs tecnicos podem ser preservados por periodo adicional para seguranca e conformidade.",
      "Quando cabivel, os dados podem ser anonimizados, agregados, bloqueados ou eliminados de forma segura ao fim do ciclo de tratamento.",
    ],
  },
  {
    id: "seguranca",
    title: "8. Seguranca da informacao e governanca",
    paragraphs: [
      "A ClinicFlux AI emprega controles administrativos, tecnicos e organizacionais para reduzir riscos de acesso nao autorizado, vazamento, perda, uso indevido, alteracao ou destruicao indevida de dados.",
    ],
    bullets: [
      "Controle de acesso por usuario, papeis e contexto operacional.",
      "Protecao de credenciais, segregacao logica, trilhas de auditoria e revisao de atividades sensiveis.",
      "Backups, monitoramento, correcoes, revisoes internas e medidas de continuidade operacional proporcionais ao servico.",
      "Fluxos de suporte, investigacao de incidentes e resposta a eventos de seguranca conforme prioridade e impacto.",
    ],
  },
  {
    id: "direitos",
    title: "9. Direitos dos titulares",
    paragraphs: [
      "Nos termos da LGPD, o titular pode solicitar confirmacao de tratamento, acesso, correcao, anonimizacao, bloqueio, eliminacao, portabilidade, informacao sobre compartilhamentos, revisao de decisoes automatizadas quando cabivel e revogacao de consentimento quando essa base legal for utilizada.",
      `Quando os dados forem tratados pela ${BRAND_NAME} na condicao de operadora, a solicitacao sera encaminhada ou coordenada com a clinica controladora responsavel, respeitando o contrato e as instrucoes recebidas.`,
    ],
  },
  {
    id: "cookies",
    title: "10. Cookies e tecnologias semelhantes",
    paragraphs: [
      "O site e a plataforma podem utilizar cookies, armazenamento local, identificadores de sessao e tecnologias semelhantes para manter login, seguranca, preferencia de navegacao, desempenho, medicao de uso e continuidade da experiencia.",
      "Voce pode gerenciar parte dessas tecnologias pelo navegador. Certas funcionalidades essenciais podem deixar de operar corretamente se mecanismos tecnicos indispensaveis forem desativados.",
    ],
  },
  {
    id: "menores",
    title: "11. Dados de criancas e adolescentes",
    paragraphs: [
      "A plataforma e o site nao sao direcionados ao uso autonomo por criancas. Eventual tratamento de dados de menores dentro da operacao de clinicas clientes deve observar base legal adequada, autorizacoes cabiveis e responsabilidade direta da clinica controladora.",
      "Se houver indicio de uso indevido ou envio indevido de dados de menores fora do contexto assistencial legitimo, a ClinicFlux AI podera restringir o tratamento e solicitar regularizacao imediata.",
    ],
  },
  {
    id: "contato",
    title: "12. Atendimento de privacidade e exercicio de direitos",
    paragraphs: [
      `Solicitacoes relacionadas a esta politica podem ser encaminhadas para ${BRAND_SUPPORT_EMAIL} ou pelos canais oficiais informados no processo comercial, no contrato ou no ambiente do cliente.`,
      "Para pedidos ligados a dados operados em nome de uma clinica contratante, a resposta pode exigir validacao previa com o controlador responsavel, inclusive para preservar sigilo profissional, seguranca do paciente e integridade de prontuarios e registros operacionais.",
    ],
  },
  {
    id: "alteracoes",
    title: "13. Atualizacoes desta politica",
    paragraphs: [
      "Esta politica pode ser atualizada para refletir evolucoes do produto, requisitos legais, novos modulos, integracoes, mudancas de seguranca ou ajustes operacionais.",
      "A versao vigente sera sempre a publicada nesta pagina, acompanhada da data de atualizacao. Mudancas relevantes tambem poderao ser comunicadas por meios contratuais, operacionais ou diretamente na plataforma.",
    ],
  },
] as const;

export const metadata: Metadata = {
  title: `Politica de Privacidade | ${BRAND_NAME}`,
  description: `${BRAND_DESCRIPTION} Conheca como a plataforma trata dados pessoais, operacao de clinicas e direitos previstos na LGPD.`,
};

export default function PrivacyPolicyPage() {
  return (
    <LegalPageShell
      eyebrow="Privacidade e LGPD"
      title={`Politica de Privacidade da ${BRAND_NAME}`}
      summary="Aqui explicamos, de forma objetiva, quais dados podem ser tratados no site e na plataforma, em quais situacoes a ClinicFlux AI atua como controladora ou operadora e como protegemos operacao, seguranca e direitos dos titulares."
      updatedAt={UPDATED_AT}
      version={VERSION}
      facts={facts}
      sections={[...sections]}
      relatedLinks={[
        { href: "/termos-de-uso", label: "Ver Termos de Uso" },
        { href: "/login", label: "Entrar na plataforma" },
      ]}
    />
  );
}
