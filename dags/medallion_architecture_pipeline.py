from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

default_args = {
    'owner': 'epsilon',
    'depends_on_past': False,
    'start_date': datetime(2026, 10, 5),
    'retries': 1,
    'retry_delay': timedelta(minutes=5)
}

with DAG(
    'medallion_architecture_pipeline',
    default_args=default_args,
    schedule_interval='@daily',
    catchup=False,
    tags=['medallion', 'cfpb', 'census', 'fdic']
) as dag:

    # 1. Extraction of Raw Data 
    extract_census = BashOperator(
        task_id = 'extract_census',
        bash_command = 'python -m src.extract.extract_census'
    )

    extract_fdic = BashOperator(
        task_id = 'extract_fdic',
        bash_command = 'python -m src.extract.extract_fdic'
    )

    extract_cfpb = BashOperator(
        task_id = 'extract_cfpb',
        bash_command = 'echo "CFPB extraction (CSV file download)"'
    )

    # 2. Ingestion of Raw Data 

    load_census = BashOperator(
        task_id = 'load_census',
        bash_command = 'python -m src.load.load_census'
    )

    load_fdic = BashOperator(
        task_id = 'load_fdic',
        bash_command = 'python -m src.load.load_fdic'
    )

    load_cfpb = BashOperator(
        task_id = "load_cfpb",
        bash_command = 'python -m src.load.load_cfpb'
    )

    # 3. Validation of Ingested Data

    validate_census = BashOperator(
        task_id = 'validate_census',
        bash_command = 'python -m src.validation.validate_census'
    )

    validate_fdic = BashOperator(
        task_id = 'validate_fdic',
        bash_command = 'python -m src.validation.validate_fdic'
    )

    validate_cfpb = BashOperator(
        task_id = 'validate_cfpb',
        bash_command = 'python -m src.validation.validate_cfpb'
    )

    # Transformation of Data

    # Star Schema Transformation for the 3 file sources (Census, FDIC, CFPB)
    transform_enrichment_census = BashOperator(
        task_id = 'transform_enrichment_census',
        bash_command = 'python -m src.transform.transform_enrichment_census'
    )

    transform_enrichment_fdic = BashOperator(
        task_id = 'transform_enrichment_fdic',
        bash_command = 'python -m src.transform.transform_enrichment_fdic'
    )

    transform_enrichment_cfpb = BashOperator(
        task_id = 'transform_enrichment_cfpb',
        bash_command = 'python -m src.transform.transform_enrichment_cfpb'
    )

    # Task dependencies
    
    # Extract --> Ingest
    extract_census >> load_census
    extract_fdic >> load_fdic
    extract_cfpb >> load_cfpb

    # Ingest --> Validate
    load_census >> validate_census
    load_fdic >> validate_fdic
    load_cfpb >> validate_cfpb

    # Validate --> Transform
    validate_census >> transform_enrichment_census
    validate_fdic >> transform_enrichment_fdic
    validate_cfpb >> transform_enrichment_cfpb

    # All validations must pass before transformations begin
    validations = [validate_census, validate_fdic, validate_cfpb]
    
    validations >> transform_enrichment_census
    validations >> transform_enrichment_fdic
    validations >> transform_enrichment_cfpb