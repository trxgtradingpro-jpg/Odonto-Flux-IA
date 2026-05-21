from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class AdminLoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class AdminLoginOutput(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    force_password_change: bool = False
    roles: list[str] = []


class AdminChangeInitialPasswordInput(BaseModel):
    current_password: str = Field(min_length=8)
    new_password: str = Field(min_length=10)


class ProspectUnitInput(BaseModel):
    unit_name: str = Field(min_length=2, max_length=180)
    address: str = ""
    phone: str | None = None
    email: EmailStr | None = None
    is_primary: bool = False


class ProspectServiceInput(BaseModel):
    service_name: str = Field(min_length=2, max_length=180)
    category: str | None = None
    duration_minutes: int = Field(default=60, ge=15, le=480)
    price_range: str | None = None
    description: str = ""


class ProspectCreate(BaseModel):
    clinic_name: str = Field(min_length=2, max_length=255)
    owner_name: str | None = None
    manager_name: str | None = None
    phone: str | None = None
    whatsapp_phone: str | None = None
    email: EmailStr | None = None
    website: str | None = None
    city: str | None = None
    state: str | None = None
    main_address: str | None = None
    notes: str = ""
    lead_source: str | None = "manual"
    first_contact_channel: str | None = None
    first_contact_at: datetime | None = None
    uses_whatsapp_heavily: bool = False
    estimated_volume: int | None = Field(default=None, ge=0)
    main_pain: str | None = None
    tags: list[str] = []
    test_phone_number: str | None = None
    proposal_snapshot: dict | None = None
    units: list[ProspectUnitInput] = []
    services: list[ProspectServiceInput] = []


class ProspectUpdate(BaseModel):
    clinic_name: str | None = None
    owner_name: str | None = None
    manager_name: str | None = None
    phone: str | None = None
    whatsapp_phone: str | None = None
    email: EmailStr | None = None
    website: str | None = None
    city: str | None = None
    state: str | None = None
    main_address: str | None = None
    notes: str | None = None
    lead_source: str | None = None
    first_contact_channel: str | None = None
    first_contact_at: datetime | None = None
    uses_whatsapp_heavily: bool | None = None
    estimated_volume: int | None = Field(default=None, ge=0)
    main_pain: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    test_phone_number: str | None = None
    do_not_contact: bool | None = None
    legal_basis: str | None = None
    roi_inputs: dict | None = None
    proposal_snapshot: dict | None = None


class ProspectNoteInput(BaseModel):
    body: str = Field(min_length=2)
    note_type: str = "nota"


class ProspectStatusInput(BaseModel):
    status: str
    note: str | None = None


class ProspectContactInput(BaseModel):
    channel: str = Field(default="ligacao")
    summary: str = Field(min_length=2)
    next_step: str | None = None


class ProspectOutreachInput(BaseModel):
    step: Literal["reception_intro", "decision_maker_pitch", "video_followup"] = "reception_intro"
    recipient_name: str | None = None
    video_url: str | None = None


class ProspectOutreachOutput(BaseModel):
    prospect: "ProspectOutput"
    step: str
    destination: str
    message_text: str
    demo_login_url: str | None = None
    video_url: str | None = None
    sender_tenant_id: UUID
    conversation_id: UUID
    outbound_message_id: UUID


class ProspectOutreachLabInput(BaseModel):
    scenario: Literal["manager_interested", "asks_price", "already_has_system", "reception_blocks"] = "manager_interested"


class ProspectOutreachLabTurnOutput(BaseModel):
    id: str
    role: str
    label: str
    text: str
    step: str | None = None
    meta: dict = {}


class ProspectOutreachLabOutput(BaseModel):
    prospect: "ProspectOutput"
    scenario: str
    scenario_label: str
    status: str
    outcome: str
    converted: bool
    recommendation: str | None = None
    demo_login_url: str | None = None
    video_url: str | None = None
    transcript: list[ProspectOutreachLabTurnOutput]
    metrics: dict


class DemoEventInput(BaseModel):
    prospect_account_id: UUID | None = None
    event_name: str
    page_path: str | None = None
    session_id: str | None = None
    payload: dict = {}


class DemoGuideResumeInput(BaseModel):
    source: str | None = "resume"
    page_path: str | None = None
    session_id: str | None = None


class DemoGuideCompleteStepInput(BaseModel):
    step_id: str
    source: str | None = "cta"
    page_path: str | None = None
    session_id: str | None = None


class DemoGuideDismissInput(BaseModel):
    source: str | None = "dismiss"
    page_path: str | None = None
    session_id: str | None = None


class DemoGuideBackStepInput(BaseModel):
    source: str | None = "back"
    page_path: str | None = None
    session_id: str | None = None


class DemoRedeemTokenInput(BaseModel):
    token: str = Field(min_length=3, max_length=120)


class MagicLinkInput(BaseModel):
    prospect_account_id: UUID


class ProspectUnitOutput(BaseModel):
    id: UUID
    unit_name: str
    address: str
    phone: str | None
    email: str | None
    is_primary: bool
    created_at: datetime


class ProspectServiceOutput(BaseModel):
    id: UUID
    service_name: str
    category: str | None
    duration_minutes: int
    price_range: str | None
    description: str
    created_at: datetime


class ProspectNoteOutput(BaseModel):
    id: UUID
    body: str
    note_type: str
    author_user_id: UUID | None
    created_at: datetime


class ProspectTimelineEventOutput(BaseModel):
    id: UUID
    event_type: str
    event_label: str
    actor_type: str
    actor_id: UUID | None
    payload: dict
    created_at: datetime


class DemoActivityOutput(BaseModel):
    id: UUID
    event_name: str
    page_path: str | None
    session_id: str | None
    payload: dict
    occurred_at: datetime


class ProspectOutput(BaseModel):
    id: UUID
    clinic_name: str
    owner_name: str | None
    manager_name: str | None
    phone: str | None
    whatsapp_phone: str | None
    email: str | None
    website: str | None
    city: str | None
    state: str | None
    main_address: str | None
    notes: str
    lead_source: str | None
    first_contact_channel: str | None
    first_contact_at: datetime | None
    uses_whatsapp_heavily: bool
    estimated_volume: int | None
    main_pain: str | None
    score: int
    temperature: str
    status: str
    tags: list[str]
    test_phone_number: str | None
    do_not_contact: bool
    legal_basis: str
    demo_tenant_id: UUID | None
    demo_user_id: UUID | None
    demo_login_email: str | None
    demo_sent_at: datetime | None
    demo_first_login_at: datetime | None
    demo_last_login_at: datetime | None
    demo_status: str
    demo_expires_at: datetime | None
    demo_checklist: dict
    last_activity_at: datetime | None
    score_explanation: dict
    proposal_snapshot: dict
    roi_inputs: dict
    created_at: datetime
    updated_at: datetime
    units: list[ProspectUnitOutput] = []
    services: list[ProspectServiceOutput] = []


class ProspectListOutput(BaseModel):
    data: list[ProspectOutput]
    total: int
    limit: int
    offset: int


class ProspectOverviewOutput(BaseModel):
    total_prospects: int
    demos_created: int
    demos_accessed: int
    hot_leads: int
    meetings_scheduled: int
    won: int
    recent_activity: list[ProspectTimelineEventOutput]


class SalesMessageTemplateOutput(BaseModel):
    key: str
    label: str
    description: str
    recommended_for: list[str]
    body: str
    messages: list["SalesMessageTemplateMessageOutput"]


class SalesMessageTemplateMessageOutput(BaseModel):
    key: str
    label: str
    body: str
    is_default: bool = False


class SalesMessageTemplateMessageInput(BaseModel):
    key: str | None = Field(default=None, max_length=80)
    label: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=2, max_length=5000)
    is_default: bool = False


class SalesMessageTemplateInput(BaseModel):
    key: str | None = Field(default=None, max_length=80)
    label: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    recommended_for: list[str] = []
    messages: list[SalesMessageTemplateMessageInput] = Field(min_length=1)


class SalesClinicMessageItemOutput(BaseModel):
    prospect: ProspectOutput
    suggested_template_key: str
    contact_name: str
    whatsapp_destination: str | None
    demo_ready: bool
    copy_blocked_reason: str | None
    last_event_name: str | None
    last_event_at: datetime | None
    last_template_key: str | None


class SalesClinicMessageListOutput(BaseModel):
    data: list[SalesClinicMessageItemOutput]
    total: int
    limit: int
    offset: int
    templates: list[SalesMessageTemplateOutput]


class SalesClinicMessagePreviewInput(BaseModel):
    prospect_id: UUID
    template_key: str | None = None
    message_key: str | None = None
    issue_demo_access: bool = True


class SalesClinicMessagePreviewOutput(BaseModel):
    prospect: ProspectOutput
    template_key: str
    template_label: str
    message_key: str
    message_label: str
    message_text: str
    demo_login_url: str | None
    can_copy: bool
    warnings: list[str]
    missing_variables: list[str]
    resolved_variables: dict
    suggested_template_key: str


class SalesClinicMessageEventInput(BaseModel):
    event_name: Literal["message_previewed", "message_copied", "demo_link_copied", "contact_registered"]
    template_key: str | None = None
    message_key: str | None = None
    message_snapshot: str | None = Field(default=None, max_length=5000)
    demo_login_url: str | None = Field(default=None, max_length=1200)
    channel: str = Field(default="whatsapp_manual", max_length=80)
    note: str | None = Field(default=None, max_length=1000)


class SalesClinicMessageEventOutput(BaseModel):
    prospect: ProspectOutput
    event: ProspectTimelineEventOutput


class DemoProvisionOutput(BaseModel):
    prospect: ProspectOutput
    access_token: str
    demo_login_url: str
    checklist: dict
    ai_draft: dict


class DemoAccessOutput(BaseModel):
    access_token: str
    demo_login_url: str
    expires_at: datetime | None


class ProspectInsightsOutput(BaseModel):
    score: int
    temperature: str
    explanation: dict
    sessions: int
    modules: dict
    last_activity_at: datetime | None


class DemoGuideStepOutput(BaseModel):
    id: str
    order: int
    title: str
    description: str
    observe: list[str]
    cta_label: str
    page_path: str
    page_label: str


class DemoGuideStateOutput(BaseModel):
    version: int
    enabled: bool
    status: str
    current_step_id: str
    current_step_order: int
    completed_step_ids: list[str]
    completed_count: int
    total_steps: int
    started_at: datetime | None
    completed_at: datetime | None
    dismissed_at: datetime | None
    steps: list[DemoGuideStepOutput]


ProspectOutreachOutput.model_rebuild()
SalesMessageTemplateOutput.model_rebuild()
