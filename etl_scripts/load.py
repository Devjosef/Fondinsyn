import yaml
from datetime import datetime
import logging
import pandas as pd
from sqlalchemy import create_engine
from etl_scripts.utils import extract_data_from_api, transform_data, load_data


# Configure logger
logger = logging.getLogger(__name__)


def load_config(config_path):
    """Load YAML config file."""
    with open(config_path, 'r') as file:
        try:
            config = yaml.safe_load(file)
            logger.info("Configuration loaded successfully.")
            return config
        except yaml.YAMLError as e:
            logger.error("Error loading configuration", exc_info=True)
            raise


def main():
    # Load config
    config = load_config('config.yaml')

    # Extract parameters from config
    api_url = config['api']['base_url']  # Fixed key name from 'url' to 'base_url'

    db_conn_str = f"postgresql://CREDENTIAL_REMOVED_9bcf166e240683cd1b72a7f9d05b8274@" \
                  f"{config['database']['host']}:{config['database']['port']}/{config['database']['db_name']}"

    # Extract
    raw_data = extract_data_from_api(api_url)

    # Transform
    df = transform_data(raw_data)

    # Load
    engine = create_engine(db_conn_str)
    load_conf = config['etl']['load']  # Fixed variable name typo from load_data to load_conf

    table_name = load_conf.get('table_name', 'transformed_data')
    if_exists = load_conf.get('if_exists', 'replace')
    index = load_conf.get('index', False)
    chunksize = load_conf.get('chunksize', None)

    # Load data to DB
    try:
        df.to_sql(name=table_name, con=engine, if_exists=if_exists, index=index, chunksize=chunksize)
        logger.info(f"Data loaded successfully into table '{table_name}'.")
    except Exception as e:
        logger.error("Error loading data into database", exc_info=True)
        raise  


if __name__ == "__main__":
    main()
