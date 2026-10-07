import os

API_BASE_URL = "http://localhost:5000"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

SYNC_CONFIG = {
    "sectores": {
        "endpoint": "/sectores",
        "id_field": "sector_id",        # PK REAL
        "excel_file": os.path.join(FRONTEND_DIR, "sectores.xlsx"),
    }
}
