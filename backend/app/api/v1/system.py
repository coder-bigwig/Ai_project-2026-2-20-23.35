from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db, is_postgres_ready, storage_backend_name
from ...repositories import (
    AttachmentRepository,
    AuthUserRepository,
    CourseRepository,
    ExperimentRepository,
    KVStoreRepository,
    OperationLogRepository,
    ResourceRepository,
    UserRepository,
)
from ...services.kv_policy_service import default_resource_policy_payload
from ...services.usage_monitor_service import build_cached_jupyter_usage_report, load_usage_monitor_state

router = APIRouter()
METRICS_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _prom_escape_label_value(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _prom_metric_line(name: str, value, labels: dict[str, str] | None = None) -> str:
    if not labels:
        return f"{name} {value}"
    serialized = ",".join(
        f'{key}="{_prom_escape_label_value(labels[key])}"'
        for key in sorted(labels)
    )
    return f"{name}{{{serialized}}} {value}"


def _metric_period_ranges(now_utc: datetime) -> dict[str, tuple[datetime | None, datetime | None]]:
    now_local = now_utc.astimezone(METRICS_TIMEZONE)
    day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())
    month_start = day_start.replace(day=1)
    if month_start.month == 12:
        next_month_start = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)
    return {
        "day": (day_start.astimezone(timezone.utc), (day_start + timedelta(days=1)).astimezone(timezone.utc)),
        "week": (week_start.astimezone(timezone.utc), (week_start + timedelta(days=7)).astimezone(timezone.utc)),
        "month": (month_start.astimezone(timezone.utc), next_month_start.astimezone(timezone.utc)),
        "all": (None, None),
    }


@router.get("/")
def root():
    return {"message": "Training Platform API", "version": "1.0.0"}


@router.get("/api/health")
def api_health():
    return {
        "status": "ok",
        "service": "experiment-manager",
        "storage_backend": storage_backend_name(),
        "postgres_ready": is_postgres_ready(),
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(db: AsyncSession = Depends(get_db)):
    user_repo = UserRepository(db)
    auth_user_repo = AuthUserRepository(db)
    course_repo = CourseRepository(db)
    experiment_repo = ExperimentRepository(db)
    attachment_repo = AttachmentRepository(db)
    resource_repo = ResourceRepository(db)
    operation_log_repo = OperationLogRepository(db)
    kv_repo = KVStoreRepository(db)
    policy_row = await kv_repo.get("resource_policy")
    policy = policy_row.value_json if policy_row and isinstance(policy_row.value_json, dict) else default_resource_policy_payload()
    overrides = policy.get("overrides", {}) if isinstance(policy, dict) else {}
    override_count = len(overrides) if isinstance(overrides, dict) else 0

    students_total = await user_repo.count_by_role("student")
    teachers_total = await auth_user_repo.count_by_role("teacher")
    classes_total = await user_repo.count_classes()
    courses_total = await course_repo.count()
    experiments_total = await experiment_repo.count()
    attachments_total = await attachment_repo.count()
    resources_total = await resource_repo.count()
    operation_logs_total = await operation_log_repo.count()

    now_utc = datetime.now(timezone.utc)
    period_ranges = _metric_period_ranges(now_utc)
    total_by_action = await operation_log_repo.count_grouped_by_action()
    total_by_success = await operation_log_repo.count_grouped_by_success()
    latest_created_at = await operation_log_repo.latest_created_at()
    period_totals: dict[str, int] = {}
    period_by_action: dict[str, dict[str, int]] = {}
    period_by_success: dict[str, dict[str, int]] = {}
    active_operators_by_period: dict[str, int] = {}

    for period, (start_at, end_at) in period_ranges.items():
        period_totals[period] = await operation_log_repo.count_in_period(start_at=start_at, end_at=end_at)
        period_by_action[period] = await operation_log_repo.count_grouped_by_action(start_at=start_at, end_at=end_at)
        period_by_success[period] = await operation_log_repo.count_grouped_by_success(start_at=start_at, end_at=end_at)
        active_operators_by_period[period] = await operation_log_repo.count_distinct_operators(
            start_at=start_at,
            end_at=end_at,
        )

    online_learning_students = 0
    try:
        usage_state = await load_usage_monitor_state(db)
        usage_report = build_cached_jupyter_usage_report(usage_state)
        usage_summary = usage_report.get("summary", {}) if isinstance(usage_report, dict) else {}
        online_learning_students = int(usage_summary.get("active_students") or 0)
    except Exception:
        online_learning_students = 0

    lines = [
        "# HELP training_backend_up Backend process up status (1=up).",
        "# TYPE training_backend_up gauge",
        "training_backend_up 1",
        "# HELP training_backend_students_total Total students stored in PostgreSQL.",
        "# TYPE training_backend_students_total gauge",
        f"training_backend_students_total {students_total}",
        "# HELP training_backend_teachers_total Total teachers stored in PostgreSQL.",
        "# TYPE training_backend_teachers_total gauge",
        f"training_backend_teachers_total {teachers_total}",
        "# HELP training_backend_online_learning_students Current students online in the cached Jupyter usage snapshot.",
        "# TYPE training_backend_online_learning_students gauge",
        f"training_backend_online_learning_students {online_learning_students}",
        "# HELP training_backend_classes_total Total classes stored in PostgreSQL.",
        "# TYPE training_backend_classes_total gauge",
        f"training_backend_classes_total {classes_total}",
        "# HELP training_backend_courses_total Total courses stored in PostgreSQL.",
        "# TYPE training_backend_courses_total gauge",
        f"training_backend_courses_total {courses_total}",
        "# HELP training_backend_experiments_total Total experiments stored in PostgreSQL.",
        "# TYPE training_backend_experiments_total gauge",
        f"training_backend_experiments_total {experiments_total}",
        "# HELP training_backend_attachments_total Total attachments stored in PostgreSQL.",
        "# TYPE training_backend_attachments_total gauge",
        f"training_backend_attachments_total {attachments_total}",
        "# HELP training_backend_resources_total Total uploaded resources stored in PostgreSQL.",
        "# TYPE training_backend_resources_total gauge",
        f"training_backend_resources_total {resources_total}",
        "# HELP training_backend_resource_quota_overrides_total Total custom user resource overrides in PostgreSQL KV.",
        "# TYPE training_backend_resource_quota_overrides_total gauge",
        f"training_backend_resource_quota_overrides_total {override_count}",
        "# HELP training_backend_operation_logs_total Total operation logs stored in PostgreSQL.",
        "# TYPE training_backend_operation_logs_total gauge",
        f"training_backend_operation_logs_total {operation_logs_total}",
        "# HELP training_backend_operation_logs_by_action_total Total operation logs grouped by action.",
        "# TYPE training_backend_operation_logs_by_action_total gauge",
        "# HELP training_backend_operation_logs_by_success_total Total operation logs grouped by success flag.",
        "# TYPE training_backend_operation_logs_by_success_total gauge",
        "# HELP training_backend_operation_logs_period_total Total operation logs in the current natural day/week/month/all window.",
        "# TYPE training_backend_operation_logs_period_total gauge",
        "# HELP training_backend_operation_logs_period_by_action_total Total operation logs in the current natural period grouped by action.",
        "# TYPE training_backend_operation_logs_period_by_action_total gauge",
        "# HELP training_backend_operation_logs_period_by_success_total Total operation logs in the current natural period grouped by success flag.",
        "# TYPE training_backend_operation_logs_period_by_success_total gauge",
        "# HELP training_backend_operation_logs_active_operators Total distinct operators active in the current natural period.",
        "# TYPE training_backend_operation_logs_active_operators gauge",
        "# HELP training_backend_operation_logs_latest_timestamp_seconds Unix timestamp of the latest operation log.",
        "# TYPE training_backend_operation_logs_latest_timestamp_seconds gauge",
    ]

    for action, count in sorted(total_by_action.items()):
        lines.append(_prom_metric_line("training_backend_operation_logs_by_action_total", count, {"action": action}))
    for success, count in sorted(total_by_success.items()):
        lines.append(_prom_metric_line("training_backend_operation_logs_by_success_total", count, {"success": success}))
    for period in ("day", "week", "month", "all"):
        lines.append(_prom_metric_line("training_backend_operation_logs_period_total", period_totals.get(period, 0), {"period": period}))
        lines.append(
            _prom_metric_line(
                "training_backend_operation_logs_active_operators",
                active_operators_by_period.get(period, 0),
                {"period": period},
            )
        )
        for action, count in sorted(period_by_action.get(period, {}).items()):
            lines.append(
                _prom_metric_line(
                    "training_backend_operation_logs_period_by_action_total",
                    count,
                    {"period": period, "action": action},
                )
            )
        for success, count in sorted(period_by_success.get(period, {}).items()):
            lines.append(
                _prom_metric_line(
                    "training_backend_operation_logs_period_by_success_total",
                    count,
                    {"period": period, "success": success},
                )
            )
    lines.append(
        _prom_metric_line(
            "training_backend_operation_logs_latest_timestamp_seconds",
            int(latest_created_at.timestamp()) if latest_created_at else 0,
        )
    )
    return "\n".join(lines) + "\n"
