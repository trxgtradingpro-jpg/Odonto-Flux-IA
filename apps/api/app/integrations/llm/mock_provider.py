import json
import re
import unicodedata

from app.integrations.llm.base import LLMProvider


def _contract(reply_text: str, next_action: str = "none", context: str = "mock", confidence: float = 0.84) -> str:
    return json.dumps(
        {
            "reply_text": reply_text,
            "next_action": next_action,
            "action_payload": {"context": context},
            "confidence": confidence,
        },
        ensure_ascii=False,
    )


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize(value: str) -> str:
    return _strip_accents(value or "").lower()


def _extract_patient_message(prompt: str) -> str:
    match = re.search(r"mensagem do paciente:\s*(.+)", prompt, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return match.group(1).split("\n\n", 1)[0].strip()


def _extract_structured_current_message(prompt: str) -> str:
    match = re.search(r"MENSAGEM_ATUAL:\s*(.+?)(?:\n\n|$)", prompt, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _structured_decision_contract(prompt: str) -> str:
    message = _extract_structured_current_message(prompt)
    normalized = _normalize(message)
    intent = "outro"
    action = "none"
    action_required = False
    should_reply_now = True
    missing_fields: list[str] = []
    suggested_question = None
    handoff_required = False
    handoff_reason = None
    if any(word in normalized for word in ["humano", "atendente", "pessoa"]):
        intent = "falar_com_humano"
        action = "handoff_to_human"
        action_required = True
        should_reply_now = False
        handoff_required = True
        handoff_reason = "patient_requested_human"
    elif any(word in normalized for word in ["urgente", "dor forte", "febre", "inchaco", "inchaço"]):
        intent = "urgencia"
        action = "handoff_to_human"
        action_required = True
        should_reply_now = False
        handoff_required = True
        handoff_reason = "urgency_detected"
    elif any(word in normalized for word in ["horario", "horarios", "agenda", "agendar", "marcar"]):
        intent = "consultar_horarios"
        action = "query_availability"
        action_required = True
        should_reply_now = False
        missing_fields = ["periodo"] if not any(word in normalized for word in ["manha", "tarde", "noite"]) else []
    elif any(word in normalized for word in ["valor", "preco", "preço", "orcamento", "orçamento"]):
        intent = "consultar_preco"
        action = "query_service"
        action_required = True
        should_reply_now = False
    elif any(word in normalized for word in ["convenio", "convênio", "plano"]):
        intent = "consultar_convenio"
        action = "query_insurance"
        action_required = True
        should_reply_now = False
    elif any(word in normalized for word in ["unidade", "endereco", "endereço", "onde fica"]):
        intent = "consultar_unidade"
        action = "query_units"
        action_required = True
        should_reply_now = False
    elif any(word in normalized for word in ["oi", "ola", "olá", "bom dia", "boa tarde", "boa noite"]):
        intent = "saudacao"
        suggested_question = "Olá! Posso te ajudar com informações, serviços ou horários. O que você precisa?"

    name_match = re.search(r"\b(?:sou|me chamo|meu nome e|meu nome é)\s+([A-Za-zÀ-ÿ ]{2,80})", message, flags=re.IGNORECASE)
    patient_name = name_match.group(1).strip(" .,!?:;") if name_match else None
    field_updates = []
    if patient_name:
        field_updates.append(
            {
                "target": "patients",
                "field": "full_name",
                "value": patient_name,
                "confidence": 0.84,
                "source_text": message,
                "should_apply": True,
                "reason": "Nome informado pelo paciente.",
            }
        )
        field_updates.append(
            {
                "target": "leads",
                "field": "name",
                "value": patient_name,
                "confidence": 0.84,
                "source_text": message,
                "should_apply": True,
                "reason": "Nome informado pelo paciente.",
            }
        )

    payload = {
        "schema_version": "1.0",
        "intent": intent,
        "confidence": 0.82,
        "detected_language": "pt-BR",
        "message_summary": message[:180],
        "extracted_data": {
            "patient_name": patient_name,
            "responsible_name": None,
            "preferred_name": None,
            "phone": None,
            "email": None,
            "cpf": None,
            "birth_date": None,
            "unit_requested_text": "Centro" if "centro" in normalized else None,
            "unit_id": None,
            "service_requested_text": None,
            "service_id": None,
            "procedure_type": None,
            "professional_requested_text": None,
            "professional_id": None,
            "preferred_date": None,
            "preferred_period": "tarde" if "tarde" in normalized else ("manha" if "manha" in normalized else ("noite" if "noite" in normalized else None)),
            "preferred_time_text": None,
            "selected_slot_id": None,
            "selected_datetime": None,
            "appointment_id": None,
            "pain": {
                "has_pain": "dor" in normalized,
                "duration_text": None,
                "has_swelling": "inchaco" in normalized or "inchaço" in normalized,
                "has_fever": "febre" in normalized,
                "urgency_level": "alta" if handoff_required else "desconhecida",
            },
        },
        "field_updates": field_updates,
        "appointment_intent": {
            "wants_booking": action == "query_availability",
            "wants_reschedule": False,
            "wants_cancel": False,
            "procedure_type": None,
            "unit_id": None,
            "professional_id": None,
            "starts_at": None,
            "ends_at": None,
            "canceled_reason": None,
        },
        "system_action": {
            "required": action_required,
            "action": action,
            "params": {
                "unit_id": None,
                "unit_name": "Centro" if "centro" in normalized else None,
                "service_id": None,
                "procedure_type": None,
                "professional_id": None,
                "date": None,
                "time_after": None,
                "time_before": None,
                "period": None,
                "slot_id": None,
                "appointment_id": None,
                "hold_minutes": 10,
                "limit": 3,
            },
        },
        "reply_control": {
            "should_reply_now": should_reply_now,
            "reply_after_system_action": action_required,
            "next_expected_field": missing_fields[0] if missing_fields else None,
            "missing_fields": missing_fields,
            "suggested_next_question": suggested_question,
        },
        "handoff": {"required": handoff_required, "reason": handoff_reason, "tag": "fila_humana_ia" if handoff_required else None},
        "guardrails": {"triggered": handoff_required and intent == "urgencia", "reason": handoff_reason, "forbidden_topics_detected": []},
    }
    return json.dumps(payload, ensure_ascii=False)


def _structured_reply_contract(prompt: str) -> str:
    action_result = {}
    match = re.search(r"SYSTEM_ACTION_RESULT_JSON:\s*(\{.*?\})\s*Retorne somente", prompt, flags=re.IGNORECASE | re.DOTALL)
    if match:
        try:
            action_result = json.loads(match.group(1))
        except Exception:
            action_result = {}
    message = "Entendi. Para eu te ajudar certinho, você prefere atendimento em qual unidade e período?"
    reason = "mock_structured_reply"
    final_decision = "ask_clarification"
    if action_result.get("action") == "query_availability":
        slots = action_result.get("slots") if isinstance(action_result.get("slots"), list) else []
        if slots:
            options = "\n".join(f"{index}. {slot.get('label') or slot.get('starts_at')}" for index, slot in enumerate(slots[:3], start=1))
            message = f"Perfeito 😊 Encontrei estes horários:\n{options}\nQual deles fica melhor para você?"
            final_decision = "reply"
            reason = "availability_options_returned"
        else:
            message = "Não encontrei horários nesse período. Posso verificar outro dia ou outro período para você?"
            reason = "availability_empty"
    elif action_result.get("action") == "query_units":
        units = action_result.get("units") if isinstance(action_result.get("units"), list) else []
        names = ", ".join(str(unit.get("name")) for unit in units[:5] if unit.get("name"))
        if names:
            message = f"Temos estas unidades disponíveis: {names}. Qual delas fica melhor para você?"
            final_decision = "reply"
            reason = "units_returned"
    elif action_result.get("action") == "query_insurance":
        plans = action_result.get("accepted_insurance") if isinstance(action_result.get("accepted_insurance"), list) else []
        if plans:
            message = "Atendemos estes convênios cadastrados: " + ", ".join(plans[:8]) + ". Qual é o seu plano?"
            final_decision = "reply"
            reason = "insurance_returned"
    payload = {
        "schema_version": "1.0",
        "message": message,
        "message_type": "text",
        "interactive_payload": None,
        "confidence": 0.82,
        "final_decision": final_decision,
        "decision_reason": reason,
    }
    return json.dumps(payload, ensure_ascii=False)


def _extract_catalog_rows(prompt: str, *, header: str, limit: int = 5) -> list[str]:
    rows: list[str] = []
    collecting = False
    for raw_line in prompt.splitlines():
        line = raw_line.strip()
        if not line:
            if collecting and rows:
                break
            continue
        if _normalize(header) in _normalize(line):
            collecting = True
            continue
        if not collecting:
            continue
        if not line.startswith("- "):
            if rows:
                break
            continue
        rows.append(line[2:].strip())
        if len(rows) >= limit:
            break
    return rows


def _format_catalog_row(row: str) -> str:
    parts: dict[str, str] = {}
    for chunk in row.split("|"):
        if ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        parts[_normalize(key).strip()] = value.strip()
    name = parts.get("nome") or row.split("|", 1)[0].strip() or row
    address = parts.get("endereco")
    phone = parts.get("telefone")
    suffix = ""
    if address:
        suffix = f" ({address})"
    elif phone:
        suffix = f" (telefone: {phone})"
    return f"{name}{suffix}"


class MockLLMProvider(LLMProvider):
    def complete(self, *, task: str, prompt: str, model: str | None = None) -> dict:
        lower_prompt = _normalize(prompt)
        if task == "classify_intent":
            intent = "agendamento"
            if "cancel" in lower_prompt:
                intent = "cancelamento"
            elif "reagend" in lower_prompt or "remarc" in lower_prompt:
                intent = "reagendamento"
            elif "orcamento" in lower_prompt or "valor" in lower_prompt:
                intent = "orcamento"
            elif "humano" in lower_prompt or "atendente" in lower_prompt:
                intent = "handoff"
            elif any(word in lower_prompt for word in ["clinica", "unidade", "endereco", "onde fica"]):
                intent = "informacoes_clinica"
            elif any(word in lower_prompt for word in ["procedimento", "servico", "tratamento"]):
                intent = "servicos"
            return {
                "output": json.dumps({"intent": intent, "confidence": 0.81}, ensure_ascii=False),
                "metadata": {"provider": "mock", "task": task},
            }

        if task == "lead_temperature":
            temperature = "morno"
            if "urgente" in lower_prompt or "fechar hoje" in lower_prompt:
                temperature = "quente"
            elif "depois vejo" in lower_prompt:
                temperature = "frio"
            return {
                "output": json.dumps({"temperature": temperature, "confidence": 0.76}, ensure_ascii=False),
                "metadata": {"provider": "mock", "task": task},
            }

        if task == "auto_responder_structured_extract":
            return {
                "output": _structured_decision_contract(prompt),
                "metadata": {"provider": "mock", "task": task, "contract": "ai_structured_flow.v1"},
            }

        if task == "auto_responder_structured_reply":
            return {
                "output": _structured_reply_contract(prompt),
                "metadata": {"provider": "mock", "task": task, "contract": "patient_reply.v1"},
            }

        if task == "auto_responder":
            patient_message = _extract_patient_message(prompt)
            normalized = _normalize(patient_message)
            clinic_rows = _extract_catalog_rows(prompt, header="Clinicas/unidades cadastradas no sistema")
            clinic_summary = "; ".join(_format_catalog_row(row) for row in clinic_rows)
            service_rows = _extract_catalog_rows(prompt, header="Servicos disponiveis")
            service_names = []
            for row in service_rows:
                formatted = _format_catalog_row(row)
                service_names.append(formatted.split(" (", 1)[0])
            service_summary = ", ".join(service_names[:5])

            asks_clinic = any(
                word in normalized
                for word in [
                    "clinica",
                    "clinicas",
                    "unidade",
                    "unidades",
                    "endereco",
                    "enderecos",
                    "localizacao",
                    "onde voces tem",
                    "onde vcs tem",
                    "onde fica",
                ]
            )
            asks_services = any(
                word in normalized
                for word in [
                    "procedimento",
                    "procedimentos",
                    "servico",
                    "servicos",
                    "tratamento",
                    "tratamentos",
                    "como e feito",
                    "como funciona",
                ]
            )

            if any(word in normalized for word in ["humano", "atendente", "pessoa"]):
                output = _contract(
                    "Claro. Vou encaminhar você para nossa equipe continuar o atendimento com segurança.",
                    next_action="handoff_human",
                    context="patient_requested_human",
                    confidence=0.9,
                )
            elif any(word in normalized for word in ["dor forte", "sangramento", "urgente"]):
                output = _contract(
                    "Sinto muito que você esteja passando por isso. Vou acionar nossa equipe para te orientar pelo atendimento correto.",
                    next_action="handoff_human",
                    context="urgency_detected",
                    confidence=0.88,
                )
            elif asks_clinic and asks_services:
                clinic_phrase = (
                    f"Hoje tenho estas unidades cadastradas: {clinic_summary}."
                    if clinic_summary
                    else "Posso te mostrar as unidades cadastradas antes de avançarmos."
                )
                service_phrase = (
                    f"Sobre procedimentos, aparecem para atendimento: {service_summary}."
                    if service_summary
                    else "Sobre procedimentos, cada caso começa por uma avaliação para entender a melhor indicação com segurança."
                )
                output = _contract(
                    (
                        "Claro! Posso te explicar sobre a clínica, as unidades e os procedimentos. "
                        f"{clinic_phrase} {service_phrase} "
                        "Você prefere começar escolhendo a unidade ou vendo os serviços disponíveis?"
                    ),
                    next_action="show_clinics",
                    context="clinic_and_services_question",
                    confidence=0.87,
                )
            elif asks_clinic:
                clinic_phrase = (
                    f" Hoje tenho estas unidades cadastradas: {clinic_summary}."
                    if clinic_summary
                    else " Vou te mostrar as clínicas disponíveis para você escolher a mais próxima."
                )
                output = _contract(
                    (
                        "Claro! Posso te ajudar com as informações da clínica e localização das unidades. "
                        f"{clinic_phrase}"
                    ),
                    next_action="show_clinics",
                    context="clinic_location_question",
                    confidence=0.86,
                )
            elif asks_services:
                service_phrase = (
                    f" Os serviços cadastrados são: {service_summary}."
                    if service_summary
                    else " Cada tratamento começa com uma avaliação para entender seu caso e indicar o melhor caminho."
                )
                output = _contract(
                    (
                        "Claro! Posso te explicar os procedimentos de forma simples e segura. "
                        f"{service_phrase} "
                        "Qual procedimento você quer conhecer primeiro?"
                    ),
                    next_action="show_services",
                    context="services_question",
                    confidence=0.85,
                )
            elif any(word in normalized for word in ["agendar", "agenda", "marcar", "consulta", "horario"]):
                output = _contract(
                    "Perfeito, posso te ajudar com o agendamento. Me diga qual procedimento você procura e o melhor período para atendimento.",
                    next_action="open_booking",
                    context="booking_request",
                    confidence=0.86,
                )
            elif any(word in normalized for word in ["cancel", "desmarcar"]):
                output = _contract(
                    "Sem problema, eu te ajudo com o cancelamento. Me confirme seu nome completo e a data da consulta.",
                    context="cancellation_request",
                    confidence=0.83,
                )
            elif any(word in normalized for word in ["reagendar", "remarcar"]):
                output = _contract(
                    "Claro, vamos reorganizar seu horário. Me informe seu nome completo e quais períodos funcionam melhor para você.",
                    context="reschedule_request",
                    confidence=0.84,
                )
            elif any(word in normalized for word in ["valor", "preco", "orcamento"]):
                output = _contract(
                    "Consigo te ajudar com informações de valores e próximos passos. Para te orientar melhor, qual procedimento você tem interesse?",
                    next_action="show_services",
                    context="price_question",
                    confidence=0.8,
                )
            elif any(word in normalized for word in ["oi", "ola", "bom dia", "boa tarde", "boa noite"]):
                output = _contract(
                    "Olá! Tudo bem? Sou o assistente da clínica e posso te ajudar com informações, horários e agendamentos. Como posso te ajudar hoje?",
                    context="greeting",
                    confidence=0.82,
                )
            else:
                output = _contract(
                    (
                        "Entendi. Posso te ajudar com informações da clínica, procedimentos, unidades, horários e agendamentos. "
                        "Se quiser, me diga se você quer ver serviços, clínicas ou horários disponíveis."
                    ),
                    context="general_question",
                    confidence=0.78,
                )

            return {
                "output": output,
                "metadata": {"provider": "mock", "task": task, "contract": "ai_autoresponder.v1"},
            }

        summary = prompt[:300]
        return {
            "output": f"Resumo operacional: {summary}",
            "metadata": {"provider": "mock", "task": task},
        }
