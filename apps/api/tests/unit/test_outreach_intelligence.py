from __future__ import annotations

import importlib.util
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INTELLIGENCE_DIR = REPO_ROOT / "outreach-intelligence"
SCHEMA_DIR = INTELLIGENCE_DIR / "schemas"
EXAMPLES_DIR = INTELLIGENCE_DIR / "examples"


def _load_module():
    module_path = INTELLIGENCE_DIR / "scripts" / "outreach_intelligence.py"
    spec = importlib.util.spec_from_file_location("outreach_intelligence", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_ref(schema: dict[str, Any], ref: str) -> dict[str, Any]:
    assert ref.startswith("#/")
    node: Any = schema
    for part in ref[2:].split("/"):
      node = node[part]
    assert isinstance(node, dict)
    return node


def _validate_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int | float) and not isinstance(value, bool))
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise AssertionError(f"Unsupported schema type {expected}")


def _validate_instance(instance: Any, subschema: dict[str, Any], *, root_schema: dict[str, Any], path: str = "$") -> None:
    if "$ref" in subschema:
        subschema = _resolve_ref(root_schema, subschema["$ref"])

    expected_type = subschema.get("type")
    if isinstance(expected_type, list):
        assert any(_validate_type(instance, option) for option in expected_type), f"{path} has invalid type"
    elif isinstance(expected_type, str):
        assert _validate_type(instance, expected_type), f"{path} has invalid type"

    if "enum" in subschema:
        assert instance in subschema["enum"], f"{path} has invalid enum value {instance!r}"

    if isinstance(instance, str) and "minLength" in subschema:
        assert len(instance) >= subschema["minLength"], f"{path} is shorter than minLength"

    if isinstance(instance, int | float) and not isinstance(instance, bool):
        if "minimum" in subschema:
            assert instance >= subschema["minimum"], f"{path} below minimum"
        if "maximum" in subschema:
            assert instance <= subschema["maximum"], f"{path} above maximum"

    if isinstance(instance, dict):
        required = subschema.get("required", [])
        for key in required:
            assert key in instance, f"{path}.{key} is required"
        properties = subschema.get("properties", {})
        if subschema.get("additionalProperties") is False:
            extra = set(instance) - set(properties)
            assert not extra, f"{path} has unexpected keys {sorted(extra)}"
        for key, value in instance.items():
            if key in properties:
                _validate_instance(value, properties[key], root_schema=root_schema, path=f"{path}.{key}")

    if isinstance(instance, list) and "items" in subschema:
        for index, item in enumerate(instance):
            _validate_instance(item, subschema["items"], root_schema=root_schema, path=f"{path}[{index}]")


def test_jsonl_files_have_valid_json_objects():
    jsonl_files = [
        REPO_ROOT / "outreach-reviews" / "conversation-reviews.jsonl",
        INTELLIGENCE_DIR / "objection-library.jsonl",
        INTELLIGENCE_DIR / "skill-update-suggestions.jsonl",
    ]
    for path in jsonl_files:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert lines, f"{path} should contain at least one safe fictional example"
        for index, line in enumerate(lines, start=1):
            parsed = json.loads(line)
            assert isinstance(parsed, dict), f"{path}:{index} must be a JSON object"


def test_schemas_are_valid_json_schema_documents():
    schema_files = sorted(SCHEMA_DIR.glob("*.schema.json"))
    assert {path.name for path in schema_files} == {
        "campaign-summary.schema.json",
        "conversation-review.schema.json",
        "lead-profile.schema.json",
        "message-evaluation.schema.json",
        "objection.schema.json",
        "skill-update-suggestion.schema.json",
    }
    for path in schema_files:
        schema = _load_json(path)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"
        assert schema["title"]
        assert isinstance(schema.get("properties"), dict)


def test_examples_validate_against_schemas():
    pairs = [
        ("sample-conversation-review.json", "conversation-review.schema.json"),
        ("sample-lead-profile.json", "lead-profile.schema.json"),
        ("sample-message-evaluation.json", "message-evaluation.schema.json"),
        ("sample-objection.json", "objection.schema.json"),
        ("sample-campaign-summary.json", "campaign-summary.schema.json"),
        ("sample-skill-update-suggestion.json", "skill-update-suggestion.schema.json"),
    ]
    for example_name, schema_name in pairs:
        example = _load_json(EXAMPLES_DIR / example_name)
        schema = _load_json(SCHEMA_DIR / schema_name)
        _validate_instance(example, schema, root_schema=schema)


def test_conversation_review_scenario_examples_validate_against_schema():
    schema = _load_json(SCHEMA_DIR / "conversation-review.schema.json")
    scenario_files = sorted(EXAMPLES_DIR.glob("conversation-review-*.json"))
    assert scenario_files
    for path in scenario_files:
        example = _load_json(path)
        _validate_instance(example, schema, root_schema=schema)
        assert "Ficticia" in example["clinic_name"]
        assert example["analysis_mode"] in {"economico", "profissional", "elite_300"}


def test_conversation_review_jsonl_matches_schema():
    schema = _load_json(SCHEMA_DIR / "conversation-review.schema.json")
    for row in _load_module().load_jsonl(REPO_ROOT / "outreach-reviews" / "conversation-reviews.jsonl"):
        _validate_instance(row, schema, root_schema=schema)


def test_conversation_review_schema_supports_safety_and_token_fields():
    schema = _load_json(SCHEMA_DIR / "conversation-review.schema.json")
    required = set(schema["required"])
    for field in [
        "cold_outreach_message_count",
        "auto_reply_received",
        "human_reply_received",
        "first_human_message_received",
        "first_human_message_at",
        "last_human_reply_at",
        "outside_24h_window",
        "template_required",
        "template_used",
        "stop_contact_required",
        "do_not_follow_up",
        "opt_in_status",
        "do_not_contact",
        "commercial_risk_score",
        "burn_risk",
        "next_best_action",
        "reply_type",
        "detected_persona",
        "detected_intent",
        "lead_temperature",
        "max_remaining_cold_messages",
        "analysis_mode",
        "token_efficiency_mode",
        "token_budget_level",
        "should_use_elite_mode",
        "elite_mode_reason",
        "estimated_token_cost_level",
        "data_loading_strategy",
        "large_context_allowed",
    ]:
        assert field in required

    assert set(schema["properties"]["opt_in_status"]["enum"]) == {
        "unknown",
        "public_business_contact",
        "explicit_opt_in",
        "human_replied",
        "requested_information",
        "do_not_contact",
    }
    assert set(schema["properties"]["analysis_mode"]["enum"]) == {"economico", "profissional", "elite_300"}
    assert set(schema["properties"]["data_loading_strategy"]["enum"]) == {
        "minimal",
        "lead_profile_only",
        "recent_events_only",
        "aggregated_summary",
        "full_campaign_analysis",
    }


def test_message_evaluation_rewrites_low_score_message():
    module = _load_module()
    result = module.evaluate_message(
        "Vamos lotar sua agenda com pacientes garantidos!!!",
        {
            "clinic_name": "Clinica Aurora Ficticia",
            "source": "google_places",
            "has_website": False,
            "website_quality": "none",
            "latest_reply": "Como voces nos encontraram?",
            "previous_messages": ["Oi, tudo bem? Encontrei a clinica no Google."],
        },
    )
    assert result["message_quality_score"] < 85
    assert result["approved_to_send"] is False
    assert result["burn_risk"] in {"medium", "high", "critical"}
    assert "garantidos" not in result["corrected_message"].lower()
    assert result["analysis_mode"] == "profissional"
    assert result["should_use_elite_mode"] is False
    assert result["judges"] == {}
    assert result["digital_twin"] == {}


def test_message_evaluation_approves_clear_contextual_message():
    module = _load_module()
    result = module.evaluate_message(
        "Encontrei voces no Google pesquisando por clinica odontologica na regiao. Aqui e o time comercial da ClinicFlux AI. Posso falar com quem cuida do WhatsApp e dos agendamentos?",
        {
            "clinic_name": "Clinica Aurora Ficticia",
            "source": "google_places",
            "has_website": False,
            "website_quality": "none",
            "latest_reply": "",
            "previous_messages": [],
        },
    )
    assert result["message_quality_score"] >= 85
    assert 40 <= result["risk_score"] <= 50
    assert result["approved_to_send"] is True
    assert result["burn_risk"] == "medium"
    assert result["analysis_mode"] == "economico"
    assert result["should_use_elite_mode"] is False
    assert result["judges"] == {}
    assert result["digital_twin"] == {}


def test_first_cold_message_is_allowed_and_uses_economico_mode():
    module = _load_module()
    context = {
        "source": "google_places",
        "lead_temperature": "cold",
        "cold_outreach_message_count": 0,
        "human_reply_received": False,
        "opt_in_status": "public_business_contact",
    }
    state = module.classify_cold_outreach_state(context)
    result = module.evaluate_message(
        "Oi, tudo bem? Encontrei a clinica no Google. Aqui e o time comercial da ClinicFlux AI. Posso falar com quem cuida do WhatsApp e dos agendamentos?",
        context,
    )

    assert state["recommended_action"] == "send_first_cold_message"
    assert state["analysis_mode"] == "economico"
    assert result["approved_to_send"] is True
    assert result["analysis_mode"] == "economico"
    assert result["data_loading_strategy"] == "minimal"


def test_auto_reply_does_not_count_as_human_and_allows_one_clarification():
    module = _load_module()
    context = {
        "source": "google_places",
        "lead_temperature": "cold",
        "cold_outreach_message_count": 1,
        "auto_reply_received": True,
        "human_reply_received": False,
        "reply_type": "auto_reply",
        "detected_persona": "automation",
        "opt_in_status": "public_business_contact",
    }
    state = module.classify_cold_outreach_state(context)

    assert state["auto_reply_received"] is True
    assert state["human_reply_received"] is False
    assert state["reply_type"] == "auto_reply"
    assert state["detected_persona"] == "automation"
    assert state["interest_level"] == "unknown"
    assert state["recommended_action"] == "send_second_commercial_clarification"
    assert state["max_remaining_cold_messages"] == 1
    assert state["analysis_mode"] == "economico"
    assert state["should_use_elite_mode"] is False

    action = module.decide_next_best_action(context)
    assert action["action"] == "send_second_commercial_clarification"
    assert action["analysis_mode"] == "economico"

    result = module.evaluate_message(
        "Obrigado. Meu contato e comercial, nao e para agendamento de paciente. Aqui e o time da ClinicFlux AI. Queria falar com quem cuida do WhatsApp e dos agendamentos da clinica. Se nao fizer sentido, sem problema.",
        context,
    )
    assert 35 <= result["risk_score"] <= 50
    assert result["approved_to_send"] is True
    assert result["should_use_elite_mode"] is False


def test_cold_lead_without_human_reply_stops_after_second_message():
    module = _load_module()
    context = {
        "source": "google_maps",
        "lead_temperature": "cold",
        "cold_outreach_message_count": 2,
        "auto_reply_received": True,
        "human_reply_received": False,
        "opt_in_status": "public_business_contact",
    }
    state = module.classify_cold_outreach_state(context)
    action = module.decide_next_best_action(context)

    assert state["reply_type"] == "no_human_reply_after_second_message"
    assert state["recommended_action"] == "stop_contact"
    assert state["max_remaining_cold_messages"] == 0
    assert state["do_not_follow_up"] is True
    assert action["action"] == "stop_contact"
    assert action["do_not_follow_up"] is True
    assert action["analysis_mode"] == "economico"
    assert action["should_use_elite_mode"] is False


def test_third_and_fourth_cold_messages_without_human_reply_are_blocked():
    module = _load_module()
    third = module.evaluate_message(
        "Passando de novo para ver quem cuida dos agendamentos.",
        {
            "source": "google_places",
            "lead_temperature": "cold",
            "cold_outreach_message_count": 2,
            "human_reply_received": False,
            "auto_reply_received": True,
            "opt_in_status": "public_business_contact",
        },
    )
    fourth = module.evaluate_message(
        "Ultima tentativa para falar com alguem da clinica.",
        {
            "source": "google_places",
            "lead_temperature": "cold",
            "cold_outreach_message_count": 3,
            "human_reply_received": False,
            "auto_reply_received": True,
            "opt_in_status": "public_business_contact",
        },
    )

    assert 75 <= third["risk_score"] <= 90
    assert third["approved_to_send"] is False
    assert third["should_use_elite_mode"] is False
    assert "Terceira mensagem fria sem resposta humana deve ser bloqueada." in third["blocked_reasons"]
    assert 90 <= fourth["risk_score"] <= 100
    assert fourth["approved_to_send"] is False
    assert fourth["analysis_mode"] == "economico"


def test_outside_24h_api_freeform_message_without_human_reply_is_blocked():
    module = _load_module()
    context = {
        "source": "google_places",
        "lead_temperature": "cold",
        "cold_outreach_message_count": 1,
        "human_reply_received": False,
        "outside_24h_window": True,
        "template_required": True,
        "template_used": False,
        "opt_in_status": "public_business_contact",
    }

    action = module.decide_next_best_action(context)
    result = module.evaluate_message(
        "Oi, tudo bem? Queria falar com quem cuida do WhatsApp da clinica.",
        context,
    )

    assert action["action"] == "stop_contact_or_use_approved_template_only"
    assert action["do_not_follow_up"] is True
    assert action["analysis_mode"] == "economico"
    assert action["should_use_elite_mode"] is False
    assert result["approved_to_send"] is False
    assert result["risk_score"] >= 88
    assert result["analysis_mode"] == "economico"


def test_do_not_contact_blocks_any_new_message():
    module = _load_module()
    action = module.decide_next_best_action(
        {
            "source": "google_places",
            "opt_in_status": "do_not_contact",
            "latest_reply": "Nao quero receber contato.",
        }
    )
    state = module.classify_cold_outreach_state({"opt_in_status": "do_not_contact"})

    assert action["action"] == "stop_contact"
    assert action["do_not_contact"] is True
    assert action["stop_contact_required"] is True
    assert state["do_not_contact"] is True
    assert state["do_not_follow_up"] is True


def test_first_human_message_from_clinic_switches_to_profissional_contextual_flow():
    module = _load_module()
    context = {
        "source": "google_places",
        "lead_temperature": "cold",
        "cold_outreach_message_count": 0,
        "clinic_sent_first_today": True,
        "latest_reply": "Bom dia, sobre o que seria?",
        "clinic_replied": True,
    }
    state = module.classify_cold_outreach_state(context)
    action = module.decide_next_best_action(context)
    result = module.evaluate_message(
        "Bom dia! Aqui e o time comercial da ClinicFlux AI. Meu contato e sobre atendimento e agendamentos no WhatsApp, nao e para consulta. Voces tem alguem responsavel por essa parte?",
        context,
    )

    assert state["human_reply_received"] is True
    assert state["auto_reply_received"] is False
    assert state["opt_in_status"] == "human_replied"
    assert state["recommended_action"] == "reply_contextually"
    assert state["analysis_mode"] == "profissional"
    assert state["token_budget_level"] == "medium"
    assert state["data_loading_strategy"] == "lead_profile_only"
    assert state["risk_score"] == 15
    assert action["action"] == "reply_contextually"
    assert result["analysis_mode"] == "profissional"
    assert 10 <= result["risk_score"] <= 25


def test_permission_to_send_stays_profissional_and_allows_demo_summary():
    module = _load_module()
    context = {
        "latest_reply": "Pode mandar.",
        "clinic_replied": True,
        "reply_type": "permission_to_send",
        "human_reply_received": True,
    }
    action = module.decide_next_best_action(context)
    result = module.evaluate_message(
        "Perfeito. Vou te mandar uma demo rapida para voce testar como se fosse um paciente falando com a clinica pelo WhatsApp.",
        context,
    )

    assert action["action"] == "send_demo"
    assert action["analysis_mode"] == "profissional"
    assert result["approved_to_send"] is True
    assert result["analysis_mode"] == "profissional"
    assert result["should_use_elite_mode"] is False


def test_price_and_demo_requests_use_elite_with_reason():
    module = _load_module()
    price = module.decide_next_best_action({"latest_reply": "Qual o valor?", "clinic_replied": True})
    demo = module.decide_next_best_action({"latest_reply": "Pode mandar uma demo?", "clinic_replied": True})

    assert price["analysis_mode"] == "elite_300"
    assert price["should_use_elite_mode"] is True
    assert price["elite_mode_reason"] == "asked_price"
    assert demo["analysis_mode"] == "elite_300"
    assert demo["should_use_elite_mode"] is True
    assert demo["elite_mode_reason"] == "requested_demo"


def test_auto_reply_text_only_is_not_human_reply():
    module = _load_module()
    state = module.classify_cold_outreach_state(
        {
            "source": "google_places",
            "lead_temperature": "cold",
            "cold_outreach_message_count": 1,
            "latest_reply": "Bem-vindo ao atendimento automatico. Digite 1 para agendar.",
            "clinic_replied": True,
        }
    )

    assert state["auto_reply_received"] is True
    assert state["human_reply_received"] is False
    assert state["analysis_mode"] == "economico"


def test_patient_like_message_long_pitch_and_early_demo_link_are_high_risk():
    module = _load_module()
    patient_like = module.evaluate_message(
        "Oi, quero agendar uma consulta para passar pela recepcao.",
        {"source": "google_places", "lead_temperature": "cold", "cold_outreach_message_count": 0},
    )
    long_pitch = module.evaluate_message(
        "Obrigado pelo retorno automatico. Aqui e o time comercial da ClinicFlux AI. Nossa plataforma ajuda com WhatsApp, agenda, automacao, organizacao, relatorios, controle, atendimento, retorno, funil, gestao e varias melhorias para a clinica crescer com mais previsibilidade e menos perda de oportunidades.",
        {
            "source": "google_places",
            "lead_temperature": "cold",
            "cold_outreach_message_count": 1,
            "auto_reply_received": True,
            "human_reply_received": False,
        },
    )
    early_link = module.evaluate_message(
        "Veja a demo aqui: https://demo.example.test/clinicflux",
        {"source": "google_places", "lead_temperature": "cold", "cold_outreach_message_count": 0},
    )

    assert patient_like["risk_score"] >= 50
    assert patient_like["approved_to_send"] is False
    assert long_pitch["risk_score"] >= 70
    assert long_pitch["approved_to_send"] is False
    assert early_link["risk_score"] >= 75
    assert early_link["approved_to_send"] is False


def test_demo_link_after_human_permission_is_allowed_with_recalculated_risk():
    module = _load_module()
    result = module.evaluate_message(
        "Perfeito, segue uma demo rapida: https://demo.example.test/clinicflux",
        {
            "latest_reply": "Pode mandar.",
            "clinic_replied": True,
            "human_reply_received": True,
            "reply_type": "permission_to_send",
            "opt_in_status": "requested_information",
        },
    )

    assert result["approved_to_send"] is True
    assert result["risk_score"] <= 25
    assert result["analysis_mode"] == "profissional"


def test_simple_decisions_do_not_load_full_jsonl(monkeypatch):
    module = _load_module()

    def _blocked_load_jsonl(*_args, **_kwargs):
        raise AssertionError("simple decision should not load JSONL")

    monkeypatch.setattr(module, "load_jsonl", _blocked_load_jsonl)
    context = {
        "source": "google_places",
        "lead_temperature": "cold",
        "cold_outreach_message_count": 1,
        "auto_reply_received": True,
        "human_reply_received": False,
    }

    assert module.classify_cold_outreach_state(context)["analysis_mode"] == "economico"
    assert module.decide_next_best_action(context)["action"] == "send_second_commercial_clarification"
    assert module.evaluate_message(
        "Obrigado. Meu contato e comercial. Aqui e o time da ClinicFlux AI.",
        context,
    )["analysis_mode"] == "economico"


def test_lead_scoring_routes_no_site_and_strong_site():
    module = _load_module()
    no_site = module.calculate_lead_score(
        {
            "has_website": False,
            "website_quality": "none",
            "google_rating": 4.8,
            "review_count": 120,
            "category": "clinica odontologica",
            "has_whatsapp": True,
            "volume_signals": 3,
        }
    )
    assert no_site["recommended_offer"] == "website_seo"
    assert no_site["lead_score"] >= 75
    assert no_site["whatsapp_dependency"] >= 70

    strong_site = module.calculate_lead_score(
        {
            "has_website": True,
            "website_quality": "strong",
            "google_rating": 4.6,
            "review_count": 80,
            "category": "dentista",
            "has_whatsapp": True,
            "volume_signals": 2,
        }
    )
    assert strong_site["recommended_offer"] == "clinicflux_ai"
    assert strong_site["digital_maturity_score"] >= 80


def test_next_best_action_handles_refusal_source_price_and_demo():
    module = _load_module()
    assert module.decide_next_best_action({"latest_reply": "Nao tenho interesse"})["action"] == "stop_contact"
    assert module.decide_next_best_action({"latest_reply": "Como voces nos encontraram?"})["action"] == "reply_contextually"
    assert module.decide_next_best_action({"latest_reply": "Qual o valor?", "stage_reached": "replied"})["action"] == "send_summary"
    assert module.decide_next_best_action({"stage_reached": "demo_clicked", "whatsapp_tested": False})["action"] == "send_video"
    assert module.decide_next_best_action({"stage_reached": "whatsapp_tested", "whatsapp_tested": True})["action"] == "book_meeting"


def test_objection_library_matches_schema():
    schema = _load_json(SCHEMA_DIR / "objection.schema.json")
    for row in _load_module().load_jsonl(INTELLIGENCE_DIR / "objection-library.jsonl"):
        _validate_instance(row, schema, root_schema=schema)
        assert 0 <= row["reply_rate"] <= 1


def test_commercial_brain_has_required_sections():
    brain = _load_json(INTELLIGENCE_DIR / "commercial-brain.json")
    for key in [
        "best_opening_by_lead_type",
        "best_offer_by_website_status",
        "best_followup_by_objection",
        "winning_patterns",
        "losing_patterns",
        "worst_messages",
        "pricing_resistance_patterns",
        "best_campaigns",
        "recommended_strategy_next_week",
        "last_updated_at",
    ]:
        assert key in brain
    assert brain["best_offer_by_website_status"]["none"] == "website_seo"


def test_skill_update_suggestions_require_human_approval():
    schema = _load_json(SCHEMA_DIR / "skill-update-suggestion.schema.json")
    for row in _load_module().load_jsonl(INTELLIGENCE_DIR / "skill-update-suggestions.jsonl"):
        _validate_instance(row, schema, root_schema=schema)
        assert row["skill"] == "local-seo-outreach-playbook"
        assert row["requires_human_approval"] is True
        assert row["analysis_mode"] == "elite_300"
        assert row["should_use_elite_mode"] is True
        assert row["data_loading_strategy"] == "full_campaign_analysis"


def test_weekly_summary_generation_uses_reviews():
    module = _load_module()
    reviews = module.load_jsonl(REPO_ROOT / "outreach-reviews" / "conversation-reviews.jsonl")
    summary = module.generate_weekly_summary(reviews, week_end=date(2026, 5, 29))
    schema = _load_json(SCHEMA_DIR / "campaign-summary.schema.json")
    _validate_instance(summary, schema, root_schema=schema)
    assert summary["total_leads_contacted"] >= 1
    assert 0 <= summary["reply_rate"] <= 1
    assert summary["analysis_mode"] == "elite_300"
    assert summary["data_loading_strategy"] == "aggregated_summary"
    assert summary["should_use_elite_mode"] is True


def test_no_new_outreach_files_contain_obvious_secrets():
    paths = [
        *INTELLIGENCE_DIR.rglob("*"),
        *(REPO_ROOT / "outreach-reviews").rglob("*"),
        *(REPO_ROOT / "outreach-reports").rglob("*"),
        REPO_ROOT / "skills" / "seo" / "SKILL.md",
        REPO_ROOT / "OUTREACH_INTELLIGENCE_README.md",
        REPO_ROOT / "OUTREACH_TESTING_GUIDE.md",
        REPO_ROOT / "OUTREACH_DATA_DICTIONARY.md",
        REPO_ROOT / "OUTREACH_DASHBOARD_SPEC.md",
        REPO_ROOT / "OUTREACH_INTELLIGENCE_IMPLEMENTATION_PLAN.md",
        REPO_ROOT / "OUTREACH_INTELLIGENCE_HARDENING_REPORT.md",
    ]
    secret_patterns = [
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|secret)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
        re.compile(r"(?i)password\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
        re.compile(r"(?i)[a-z0-9._%+-]+@(gmail|hotmail|outlook|icloud|yahoo)\\.com"),
        re.compile(r"\+?55\s?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}"),
    ]
    text_suffixes = {".json", ".jsonl", ".md", ".py", ".tsx"}
    for path in paths:
        if not path.is_file() or path.suffix not in text_suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in secret_patterns:
            assert not pattern.search(text), f"Potential secret in {path}"


def test_skill_frontmatter_keeps_name_and_description():
    skill_path = REPO_ROOT / "skills" / "seo" / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    frontmatter = text.split("---", 2)[1]
    assert "name: local-seo-outreach-playbook" in frontmatter
    assert "description:" in frontmatter
    assert "Cold WhatsApp Outreach Safety Policy" in text
    assert "Pre-send Message Sense Check" in text
    assert "Post-conversation Review" in text
