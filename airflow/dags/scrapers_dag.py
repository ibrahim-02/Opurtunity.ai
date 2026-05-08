"""
Scrapers DAG: greenhouse + lever + workday.

- greenhouse_scrape, lever_scrape, workday_scrape run in parallel every 12 hours.
- workday_discover runs once a day (02:00 UTC) to find new Workday boards from
  the SEC companies list. Discovery is slow (~1-2h for full list) so it runs
  separately and less frequently than the scrape pass.
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
    "execution_timeout": timedelta(hours=3),
}


def run_greenhouse():
    from scrapers.greenhouse.main import run_scrape
    run_scrape(limit=None)


def run_lever():
    from scrapers.lever.main import run
    run(limit=None)


def run_workday_discover():
    from scrapers.workday.main import run_discover
    run_discover(limit=None)


def run_workday_scrape():
    from scrapers.workday.main import run_scrape
    run_scrape(limit=None)


# ── Scrape DAG (every 12 hours) ───────────────────────────────────────────────
with DAG(
    dag_id="scrapers_pipeline",
    default_args=default_args,
    schedule_interval="0 */12 * * *",
    start_date=datetime(2026, 5, 1),
    catchup=False,
    max_active_runs=1,
    tags=["scrapers"],
) as scrape_dag:

    greenhouse_task = PythonOperator(
        task_id="greenhouse_scrape",
        python_callable=run_greenhouse,
    )

    lever_task = PythonOperator(
        task_id="lever_scrape",
        python_callable=run_lever,
    )

    workday_scrape_task = PythonOperator(
        task_id="workday_scrape",
        python_callable=run_workday_scrape,
    )

    # All three run in parallel
    [greenhouse_task, lever_task, workday_scrape_task]


# ── Discovery DAG (once a day) ────────────────────────────────────────────────
with DAG(
    dag_id="workday_discover",
    default_args={**default_args, "execution_timeout": timedelta(hours=4)},
    schedule_interval="0 2 * * *",
    start_date=datetime(2026, 5, 1),
    catchup=False,
    max_active_runs=1,
    tags=["scrapers", "discovery"],
) as discover_dag:

    PythonOperator(
        task_id="workday_discover",
        python_callable=run_workday_discover,
    )
