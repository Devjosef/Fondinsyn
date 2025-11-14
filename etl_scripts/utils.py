import logging
import requests
import time
import pandas as pd
from sqlalchemy import create_engine


# Configure logger
logger = logging.getLogger(__name__)

def extract_data_from_api(api_url):
    """Extract data from a REST API."""
    logger.info(f"Starting data extraction from API: {api_url}")
    for attempt in range (3): # Retry incase of failure
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()  # Raise an error for bad status codes
            data = response.json()
            logger.info("Data extraction successful.")
            return data
        except requests.exceptions.RequestException as e:
            logger.warning(f"API call failed (attempt {attempt+1}/3). Retrying...")
            time.sleep(2 ** attempt)
    # Should run after the for all retries fail. 
    logger.error("All api retries failed")
    raise RuntimeError("Failed to fetch data from API")
    
def transform_data(df):
    """Clean and Transform the data."""
    logger.info("Starting data transformation")
    try:
        # Validation step to check if required columns exist
        required_columns = {'date', 'category', 'value'}
        if not required_columns.issubset(df.columns):
            missing = required_columns - set(df.columns)
            raise ValueError(f"Missing required columns: {missing}")
        
        # Remove rows with missing values
        original_row_count = len(df)
        df_clean = df.dropna()
        logger.info(f"Dropped missing values: rows={original_row_count - len(df_clean)}")
        
        # Data transformation example: Converting a date column.
        df_clean['date'] = pd.to_datetime(df_clean['date'], errors='coerce')
        logger.info("Data column converted to datetime.")
        
        # Aggregation example
        df_agg = df_clean.groupby('category').agg({'value': 'sum'}).reset_index()
        logger.info("Aggregated data by category.")
        
        logger.info("Data transformation completed: %d rows", len(df_agg))
        return df_agg
    except Exception as e:
        logger.error("Error during data transformation", exc_info=True)
        raise


def load_data(df, db_engine):
    """Load data into the database."""
    logger.info("Starting data loading")
    try:
        # Log target connection or table info
        df.to_sql('transformed_data', con=db_engine, if_exists='replace', index=False)
        logger.info("Data Loaded successfully into database: rows=%d", len(df))
    except Exception as e:
        logger.error("Error during data loading", exc_info=True)
        raise

if __name__ == "__main__":
    # Wrap ETL steps into main() function for reusability and testing
 # Start the ETL process 
    start_time = time.time()
    api_url="https://api.example.com/marketdata"
    db_connection_string = "sqlite:///etl_database.db"  # Example using SQLite

    logger.info("ETL Process Started")

    try:
        # Step 1: Extract
        data = extract_data_from_api(api_url)
        df = pd.DataFrame(data)
        
        # Json to Dataframe
        # Refering to (df = pd.DataFrame(data) should work if the api returns a list of dictionaries
        # If the case is that it is nested json i should use the code below
        # Add pd.json_normalize ["results"]

        # Step 2: Transform
        transformed_data = transform_data(df)

        # Step 3: Load
        engine = create_engine(db_connection_string)
        load_data(transformed_data, engine)

        logger.info("ETL pipeline completed successfully")
    except Exception as e:
        logger.error("ETL pipeline failed", exc_info=True)

    finally:
        end_time = time.time()
        logger.info(f"ETL pipeline finished in {end_time - start_time:.2f} seconds")
        # Add resource usage (CPU, memory) logger for monitoring.
 