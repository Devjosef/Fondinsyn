import logging.config
import yaml
import sys

# Config logging even for main.py
logger = logging.getLogger(__name__)

def setup_logging(default_path='config.yaml', default_level=logging.INFO):
    """ Load logging config from YAML and apply """
    try:
        with open(default_path, 'r') as f:
            config = yaml.safe_load(f.read())
            logging_config = {
                'version': 1,
                'formatters': {
                    'default':{
                        'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
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
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("ETL pipeline starting")

    # Imports for ETL modules.
    from etl_scripts.extract import extract_data
    from etl_scripts.transform import transform_data
    from etl_scripts.load import load_data

    # Expected / Example of run flow:
    try:
        data = extract_data()
        transformed = transform_data(data)
        load_data(transformed)
        logger.info("ETL pipeline completed successfully")
    except Exception as e:
        logger.error("ETL pipeline failed", exc_info=True)

if __name__ == "__main__":
    main()