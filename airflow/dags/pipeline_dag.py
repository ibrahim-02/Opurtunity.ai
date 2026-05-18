"""
Job pipeline DAG: enrich_jobs → embed_jobs
Runs every 30 minutes. Each task only runs after the previous succeeds.
"""
import sys, os
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "airflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=3),
    "execution_timeout": timedelta(hours=2),
}


def run_enrich():
    from pipeline.enrich_jobs import run
    run(batch=200, source=None, delay=0.3)


def run_embed():
    from pipeline.embed_jobs import run
    run(batch=500, source=None, delay=0.05)


with DAG(
    dag_id="job_pipeline",
    default_args=default_args,
    schedule_interval="*/30 * * * *",
    start_date=datetime(2026, 5, 1),
    catchup=False,
    max_active_runs=1,
    tags=["pipeline"],
) as dag:

    enrich_task = PythonOperator(
        task_id="enrich_jobs",
        python_callable=run_enrich,
    )

    embed_task = PythonOperator(
        task_id="embed_jobs",
        python_callable=run_embed,
    )

    enrich_task >> embed_task
