import os
from dotenv import find_dotenv, load_dotenv

dotenv_path = find_dotenv()

load_dotenv(dotenv_path)

API_KEY = os.getenv("API_KEY")

print(f"Loaded API_KEY: {API_KEY}")
