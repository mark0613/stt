from pathlib import Path

from dotenv import load_dotenv

load_dotenv('.env', override=True)

BASE_DIR = Path(__file__).parent.parent
