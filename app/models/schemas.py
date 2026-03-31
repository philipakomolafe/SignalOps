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

