import requests
import logging
from airflow.decorators import dag, task
from datetime import datetime

# Config logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dag(schedule="@daily", start_date=datetime(2025, 11, 5), catchup=False, max_active_runs=1)
def nav_etl():

    @task()
    def extract():
        url="https://api.example.com/data"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            logger.info("Data extracted successfully")
            return data
        except requests.exceptions.RequestException as e:
            raise

    @task()
    def transform(raw_data):
        try:
            transformed_data = raw_data
            logger.info("Data transformed successfully")
            return transformed_data
        except Exception as e:
            raise

    @task()
    def load(processed_data):
        try:
            logger.info(f"Loading Data with {len(processed_data)} records")
            print(processed_data)
            logger.info("Data loading successful")
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            raise

    raw = extract()
    processed = transform(raw)
    load(processed)

etl_dag = nav_etl()

