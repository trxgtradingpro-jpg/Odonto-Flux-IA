from pydantic import BaseModel


class DashboardKPIOutput(BaseModel):
    avg_first_response_minutes: float
    avg_resolution_minutes: float
    confirmation_rate: float
    cancellation_rate: float
    no_show_rate: float
    no_show_recovery_rate: float
    budget_conversion_rate: float
    reactivated_patients: int
    messages_count: int
    leads_by_origin: list[dict]
    performance_by_unit: list[dict]
    performance_by_attendant: list[dict]
    ai_automation_rate: float = 0.0
    ai_handoff_rate: float = 0.0
    avg_first_response_ai_minutes: float = 0.0
    ai_send_failure_rate: float = 0.0
