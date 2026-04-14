import json

from app.integrations.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    def complete(self, *, task: str, prompt: str) -> dict:
        lower_prompt = prompt.lower()
        if task == 'classify_intent':
            intent = 'agendamento'
            if 'cancel' in lower_prompt:
                intent = 'cancelamento'
            elif 'reagend' in lower_prompt:
                intent = 'reagendamento'
            elif 'orcamento' in lower_prompt:
                intent = 'orcamento'
            return {
                'output': json.dumps({'intent': intent, 'confidence': 0.81}),
                'metadata': {'provider': 'mock', 'task': task},
            }

        if task == 'lead_temperature':
            temperature = 'morno'
            if 'urgente' in lower_prompt or 'fechar hoje' in lower_prompt:
                temperature = 'quente'
            elif 'depois vejo' in lower_prompt:
                temperature = 'frio'
            return {
                'output': json.dumps({'temperature': temperature, 'confidence': 0.76}),
                'metadata': {'provider': 'mock', 'task': task},
            }

        if task == 'auto_responder':
            patient_message = ''
            marker = 'mensagem do paciente:'
            if marker in lower_prompt:
                patient_message = lower_prompt.split(marker, 1)[1].strip()
                patient_message = patient_message.split('\n\n', 1)[0].strip()

            if any(word in patient_message for word in ['oi', 'ola', 'olá', 'bom dia', 'boa tarde', 'boa noite']):
                output = (
                    'Oi! Tudo bem? Sou o assistente da clínica e posso te ajudar com '
                    'agendamento, confirmação e reagendamento. Qual melhor horário para você?'
                )
            elif any(word in patient_message for word in ['agendar', 'agenda', 'marcar', 'consulta']):
                output = (
                    'Perfeito, posso te ajudar com o agendamento. '
                    'Me diga seu nome completo e o melhor período (manhã, tarde ou noite).'
                )
            elif any(word in patient_message for word in ['cancel', 'desmarcar']):
                output = (
                    'Sem problema, posso te ajudar com o cancelamento. '
                    'Me confirme seu nome completo e a data da consulta.'
                )
            elif any(word in patient_message for word in ['reagendar', 'remarcar']):
                output = (
                    'Claro, vamos reagendar. '
                    'Me informe seu nome completo e os períodos que funcionam melhor para você.'
                )
            else:
                output = (
                    'Entendi. Posso te ajudar com informações operacionais, horários e agendamentos. '
                    'Como posso te ajudar agora?'
                )

            return {
                'output': output,
                'metadata': {'provider': 'mock', 'task': task},
            }

        summary = prompt[:300]
        return {
            'output': f'Resumo operacional: {summary}',
            'metadata': {'provider': 'mock', 'task': task},
        }
