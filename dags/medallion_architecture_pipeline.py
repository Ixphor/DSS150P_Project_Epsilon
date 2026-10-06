"""
CFPB complaint pipeline: Raw -> Staging -> Curated (medallion architecture).

Sources
  * CFPB bulk CSV   : one-time bootstrap (skipped automatically once the table has data)
  * CFPB API        : incremental, paginated, UPSERTed on complaint_id
  * FDIC API (JSON -> Parquet) and Census ACS API (JSON)

Flow
  CFPB   : extract_cfpb_bulk >> load_cfpb_bulk >> extract_cfpb_api >> load_cfpb_api >> validate_cfpb >> stage_cfpb
  FDIC   : extract_fdic >> load_fdic >> validate_fdic >> stage_fdic
  Census : extract_census >> load_census >> validate_census >> stage_census
  all three stage_* >> build_curated >> validate_curated

Quality gates: every validate_* task RAISES on a failed check, which fails the task and
blocks everything downstream. Reruns are safe: raw uses upserts (or skip-if-loaded), and
staging / curated are rebuilt atomically in a single transaction.

Trigger parameters (Trigger DAG w/ config):
  lookback_days      days before the latest loaded complaint that the API pull restarts from
  force_bulk_reload  true = truncate and reload raw CFPB from the bulk CSV
"""
import logging
import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

logger = logging.getLogger(__name__)

PROJECT_HOME = os.getenv("PIPELINE_HOME", "/opt/airflow")


def notify_failure(context):
    """Failure hook: one clear log line pointing at the failed task and its log file."""
    ti = context["task_instance"]
    logger.error(
        "TASK FAILED: dag=%s task=%s run=%s try=%s/%s log=%s",
        ti.dag_id, ti.task_id, context.get("run_id"), ti.try_number, ti.max_tries + 1, ti.log_url,
    )


def py_task(task_id: str, module: str, args: str = "", **kwargs) -> BashOperator:
    """Runs `python -m <module>` from the project root so imports and relative paths resolve."""
    return BashOperator(
        task_id=task_id,
        bash_command=f"cd {PROJECT_HOME} && python -m {module} {args}".strip(),
        **kwargs,
    )


default_args = {
    "owner": "epsilon",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=15),
    "execution_timeout": timedelta(hours=1),
    "on_failure_callback": notify_failure,
}

with DAG(
    dag_id="medallion_architecture_pipeline",
    description="CFPB complaints enriched with FDIC institutions and Census demographics",
    default_args=default_args,
    start_date=datetime(2026, 10, 5),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    params={"lookback_days": 14, "force_bulk_reload": False},
    tags=["medallion", "cfpb", "fdic", "census"],
    doc_md=__doc__,
) as dag:

    # ------------------------------------------------------------ CFPB
    extract_cfpb_bulk = py_task("extract_cfpb_bulk", "src.extract.extract_cfpb_bulk", execution_timeout=timedelta(hours=2))
    load_cfpb_bulk = py_task(
        "load_cfpb_bulk", "src.load.load_cfpb",
        "{{ '--force' if params.force_bulk_reload else '' }}",
        execution_timeout=timedelta(hours=3),
    )
    extract_cfpb_api = py_task("extract_cfpb_api", "src.extract.extract_cfpb_api", "--lookback-days {{ params.lookback_days }}")
    load_cfpb_api = py_task("load_cfpb_api", "src.load.load_cfpb_api")
    validate_cfpb = py_task("validate_cfpb", "src.validation.validate_cfpb", retries=0)
    stage_cfpb = py_task("stage_cfpb", "src.transform.stage", "cfpb", execution_timeout=timedelta(hours=2))

    extract_cfpb_bulk >> load_cfpb_bulk >> extract_cfpb_api >> load_cfpb_api >> validate_cfpb >> stage_cfpb

    # ------------------------------------------------------------ FDIC
    extract_fdic = py_task("extract_fdic", "src.extract.extract_fdic")
    load_fdic = py_task("load_fdic", "src.load.load_fdic")
    validate_fdic = py_task("validate_fdic", "src.validation.validate_fdic", retries=0)
    stage_fdic = py_task("stage_fdic", "src.transform.stage", "fdic")

    extract_fdic >> load_fdic >> validate_fdic >> stage_fdic

    # ------------------------------------------------------------ Census
    extract_census = py_task("extract_census", "src.extract.extract_census")
    load_census = py_task("load_census", "src.load.load_census")
    validate_census = py_task("validate_census", "src.validation.validate_census", retries=0)
    stage_census = py_task("stage_census", "src.transform.stage", "census")

    extract_census >> load_census >> validate_census >> stage_census

    # ------------------------------------------------------------ Curated (needs all three sources)
    build_curated = py_task("build_curated", "src.transform.build_curated", execution_timeout=timedelta(hours=2))
    validate_curated = py_task("validate_curated", "src.validation.validate_curated", retries=0)

    [stage_cfpb, stage_fdic, stage_census] >> build_curated >> validate_curated
