"""
Scrapers DAG: greenhouse_scrape + lever_scrape (parallel).
Runs every 12 hours. New jobs are picked up by the job_pipeline DAG (enrich/embed)
on its next 30-minute tick.
"""
import sys, os
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}


def run_greenhouse():
    from scrapers.greenhouse.main import run_scrape
    run_scrape(limit=None)


def run_lever():
    from scrapers.lever.main import run
    run(limit=None)


with DAG(
    dag_id="scrapers_pipeline",
    default_args=default_args,
    schedule_interval="0 */12 * * *",
    start_date=datetime(2026, 5, 1),
    catchup=False,
    max_active_runs=1,
    tags=["scrapers"],
) as dag:

    greenhouse_task = PythonOperator(
        task_id="greenhouse_scrape",
        python_callable=run_greenhouse,
    )

    lever_task = PythonOperator(
        task_id="lever_scrape",
        python_callable=run_lever,
    )

    [greenhouse_task, lever_task]
