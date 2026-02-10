import logging.config
import yaml
import sys

logger = logging.getLogger(__name__)

def setup_logging(default_path='config/config.yaml', default_level=logging.INFO):
    """Load logging configuration from YAML."""
    try:
        with open(default_path, 'r') as f:
            config = yaml.safe_load(f.read())
            logging_config = {
                'version': 1,
                'formatters': {
                    'default': {
                        'format': '%(asctime)s [%(levelname)s] %(message)s',
                    },
                },
                'handlers': {
                    'file': {
                        'class': 'logging.FileHandler',
                        'formatter': 'default',
                        'filename': config['logging']['log_file'],
                        'level': config['logging']['log_level'],
                        'encoding': 'utf8'
                    },
                    'console': {
                        'class': 'logging.StreamHandler',
                        'formatter': 'default',
                        'level': config['logging']['log_level'],
                        'stream': sys.stdout,
                    },
                },
                'root': {
                    'handlers': ['file', 'console'],
                    'level': config['logging']['log_level'],
                },
            }
            logging.config.dictConfig(logging_config)
    except Exception as e:
        print(f"Error loading logging configuration: {e}")
        logging.basicConfig(level=default_level)

def main():
    print("=== ETL START ===")
    sys.stdout.flush()

    setup_logging()
    config = yaml.safe_load(open('config/config.yaml'))

    logger.info("Importing ETL modules...")
    from etl_scripts.extract import extract_data
    from etl_scripts.transform import transform_data
    from etl_scripts.load import load_data
    from etl_scripts.load_assets import load_assets_from_csv
    from etl_scripts.load_holdings import load_holdings_from_csv

    try:
        logger.info("Extracting data...")
        total_extracted = 0
        transformed_chunks = []

        for i, chunk in enumerate(extract_data(), start=1):
            total_extracted += len(chunk)
            logger.info(f"Chunk {i}: {len(chunk)} rows extracted.")
            for transformed in transform_data(chunk):
                transformed_chunks.append(transformed)

        logger.info(f"Extracted {total_extracted} rows total.")

        logger.info("Loading sector allocations...")
        load_data(transformed_chunks)

        assets_loaded = load_assets_from_csv('swedish_funds_complete.csv', config)
        logger.info(f"{assets_loaded} assets loaded.")

        holdings_loaded = load_holdings_from_csv('swedish_funds_complete.csv', config)
        logger.info(f"{holdings_loaded} holdings loaded.")

        logger.info("Exporting CSVs from database...")

        logger.info("ETL completed successfully.")
    except Exception:
        logger.exception("ETL failed.")

    print("=== ETL END ===")

if __name__ == "__main__":
    main()
