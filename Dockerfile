FROM apache/airflow:2.7.1-python3.10

ENV PYTHONPATH=/opt/airflow \
    PIPELINE_HOME=/opt/airflow

USER airflow
COPY --chown=airflow:root requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt