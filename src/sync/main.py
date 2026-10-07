from sync_engine import sync_table
from config import SYNC_CONFIG

def main():
    for table_name, config in SYNC_CONFIG.items():
        print(f"Sincronizando {table_name}...")
        result = sync_table(config)
        print(result)

if __name__ == "__main__":
    main()
