from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class LeakFinding(BaseModel):
	id: str
	title: str
	severity: str
	what_changed: str
	likely_why: str
	what_to_do: str
	evidence: List[str] = Field(default_factory=list)


class CohortRetentionPoint(BaseModel):
	cohort: str
	customer_count: int
	retained_30d: int
	retention_rate_30d: float


class FeatureSnapshot(BaseModel):
	total_revenue: float
	order_count: int
	customer_count: int
	revenue_per_user: float
	purchase_frequency: float
	repeat_rate: float
	refund_rate: float
	avg_time_to_second_purchase_days: Optional[float] = None
	avg_purchase_interval_days: Optional[float] = None
	week_over_week_revenue_change_pct: Optional[float] = None
	cohort_retention_30d: List[CohortRetentionPoint] = Field(default_factory=list)


class DiagnosisBlock(BaseModel):
	what_changed: str
	likely_why: str
	what_to_do: str


class AnalysisResponse(BaseModel):
	run_id: Optional[int] = None
	created_at: Optional[str] = None
	source_file: Optional[str] = None
	from_cache: bool = False
	segment: str
	summary: str
	features: FeatureSnapshot
	findings: List[LeakFinding] = Field(default_factory=list)
	diagnosis: DiagnosisBlock


class AnalysisHistoryItem(BaseModel):
	run_id: int
	created_at: str
	source_file: str
	segment: str
	summary: str


class SignupRequest(BaseModel):
	full_name: str = Field(min_length=2, max_length=120)
	email: EmailStr
	password: str = Field(min_length=8, max_length=256)
	company: Optional[str] = Field(default=None, max_length=120)


class SignupResponse(BaseModel):
	user_id: int
	created_at: str
	full_name: str
	email: EmailStr
	company: Optional[str] = None


class AuthUser(BaseModel):
	user_id: int
	full_name: str
	email: EmailStr
	company: Optional[str] = None


class LoginRequest(BaseModel):
	email: EmailStr
	password: str = Field(min_length=8, max_length=256)


class LoginResponse(BaseModel):
	access_token: str
	token_type: str = "bearer"
	user: AuthUser


class ShopifyConnectStartRequest(BaseModel):
	shop_domain: str = Field(min_length=5, max_length=255)


class ShopifyConnectStartResponse(BaseModel):
	auth_url: str
	shop_domain: str


class ShopifyConnectionStatusResponse(BaseModel):
	connected: bool
	shop_domain: Optional[str] = None
	scope: Optional[str] = None
	last_synced_at: Optional[str] = None


class MonitorRunResponse(BaseModel):
	processed_stores: int
	triggered_analyses: int


class DataRetentionRunResponse(BaseModel):
	total_deleted: int
	analysis_runs_deleted: int
	monitor_runs_deleted: int
	revoked_sessions_deleted: int
	inactive_connections_deleted: int


class PlanCount(BaseModel):
	plan_code: str
	total: int


class TurnaroundTrendPoint(BaseModel):
	day: str
	avg_duration_ms: float


class ProductImpactMetrics(BaseModel):
	total_revenue_analyzed: float = 0.0
	repeat_rate: float = 0.0
	refund_rate: float = 0.0
	week_over_week_revenue_change_pct: Optional[float] = None
	based_on_run_id: Optional[int] = None
	based_on_created_at: Optional[str] = None


class UsageVelocityMetrics(BaseModel):
	analyses_run_7d: int = 0
	active_users_7d: int = 0
	csv_to_insight_turnaround_trend: List[TurnaroundTrendPoint] = Field(default_factory=list)


class MonitoringReliabilityMetrics(BaseModel):
	monitor_runs_7d: int = 0
	success_rate_pct: float = 0.0
	error_count_7d: int = 0
	top_error_category: Optional[str] = None


class CommercialTractionMetrics(BaseModel):
	new_signups_7d: int = 0
	active_subscriptions_by_plan: List[PlanCount] = Field(default_factory=list)
	payment_success_events_7d: int = 0


class FounderPostPackMetricsResponse(BaseModel):
	generated_at: str
	window_days: int = 7
	product_impact: ProductImpactMetrics
	usage_velocity: UsageVelocityMetrics
	monitoring_reliability: MonitoringReliabilityMetrics
	commercial_traction: CommercialTractionMetrics


class AccountPlanResponse(BaseModel):
	plan_code: str
	is_admin: bool = False


class FeatureTimeSeriesPoint(BaseModel):
	timestamp: str
	total_revenue: float = 0.0
	order_count: int = 0
	customer_count: int = 0
	revenue_per_user: float = 0.0
	purchase_frequency: float = 0.0
	repeat_rate: float = 0.0
	refund_rate: float = 0.0
	week_over_week_revenue_change_pct: Optional[float] = None


class AdminFeatureTimeSeriesResponse(BaseModel):
	generated_at: str
	window_days: int = 30
	points: List[FeatureTimeSeriesPoint] = Field(default_factory=list)


class UserPerformanceSummary(BaseModel):
	total_revenue: float = 0.0
	order_count: int = 0
	customer_count: int = 0
	revenue_per_user: float = 0.0
	purchase_frequency: float = 0.0
	repeat_rate: float = 0.0
	refund_rate: float = 0.0
	week_over_week_revenue_change_pct: Optional[float] = None


class UserPerformanceResponse(BaseModel):
	generated_at: str
	window_days: int = 7
	points: List[FeatureTimeSeriesPoint] = Field(default_factory=list)
	summary: UserPerformanceSummary


class FlutterwaveInitializeRequest(BaseModel):
	plan: str = Field(min_length=3, max_length=20)


class FlutterwaveInitializeResponse(BaseModel):
	public_key: str
	tx_ref: str
	amount: float
	currency: str
	payment_plan: str
	customer_email: EmailStr
	customer_name: str
	customization_title: str = "SignalOps Subscription"
	customization_description: str = "SignalOps plan checkout"
	status: str = "ready"

