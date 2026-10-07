import requests
import pandas as pd
from config import API_BASE_URL
from diff_engine import compute_diff


VERBOSE = True   # Cambiá a False si no querés logs


def log(msg):
    if VERBOSE:
        print(msg)


def load_excel(path):
    with open(path, "rb") as f:
        return pd.read_excel(f)


def load_backend(endpoint):
    url = f"{API_BASE_URL}{endpoint}"
    resp = requests.get(url)
    resp.raise_for_status()
    return pd.DataFrame(resp.json())


def post_row(endpoint, row_dict):
    url = f"{API_BASE_URL}{endpoint}"
    log(f"  → POST {url}")
    log(f"    Payload: {row_dict}")
    resp = requests.post(url, json=row_dict)
    resp.raise_for_status()
    return resp.json()


def put_row(endpoint, row_id, row_dict):
    url = f"{API_BASE_URL}{endpoint}/{row_id}"
    log(f"  → PUT {url}")
    log(f"    Payload: {row_dict}")
    resp = requests.put(url, json=row_dict)
    resp.raise_for_status()
    return resp.json()


def delete_row(endpoint, row_id):
    url = f"{API_BASE_URL}{endpoint}/{row_id}"
    log(f"  → DELETE {url}")
    resp = requests.delete(url)
    resp.raise_for_status()
    return resp.json() if resp.text else None


def diff_details(before, after):
    """Devuelve un dict con los campos que cambiaron."""
    cambios = {}
    for col in before.index:
        if before[col] != after[col]:
            cambios[col] = (before[col], after[col])
    return cambios


def sync_table(config):
    endpoint = config["endpoint"]
    id_field = config["id_field"]
    excel_file = config["excel_file"]

    print(f"\n=== Sincronizando {endpoint} ===")

    import os
    print("Excel file path:", os.path.abspath(excel_file))


    # 1) Cargar datos
    df_excel = pd.read_excel(excel_file, sheet_name="sectores")
    df_backend = load_backend(endpoint)

    print("Excel IDs:", df_excel[id_field].tolist())
    print("Backend IDs:", df_backend[id_field].tolist())

    # Asegurar que la columna PK exista
    if id_field not in df_excel.columns:
        df_excel[id_field] = None

    if df_backend.empty:
        df_backend = pd.DataFrame(columns=df_excel.columns)
        if id_field not in df_backend.columns:
            df_backend[id_field] = None

    # 2) Calcular diferencias
    nuevos, modificados, eliminados = compute_diff(df_excel, df_backend, id_field)

    resumen = {"insertados": 0, "modificados": 0, "eliminados": 0}

    # 3) INSERT
    if not nuevos.empty:
        print("\n→ INSERTANDO registros nuevos:")

    for idx, row in nuevos.iterrows():
        payload = row.to_dict()

        # Eliminar PK del POST
        payload.pop(id_field, None)

        # Filtrar solo columnas válidas
        allowed_fields = ["nombre_sector", "centro_costo", "estado_sector"]
        payload = {k: v for k, v in payload.items() if k in allowed_fields}

        # Limpiar valores inválidos
        payload = {
            k: v for k, v in payload.items()
            if v not in [None, "None", "nan", ""]
        }

        resp = post_row(endpoint, payload)

        nuevo_id = resp.get(id_field)
        if nuevo_id is None:
            raise ValueError(f"El backend no devolvió {id_field} en el POST")

        log(f"    ✔ INSERT OK — Nuevo ID asignado: {nuevo_id}")

        df_excel.loc[idx, id_field] = nuevo_id
        resumen["insertados"] += 1

    # 4) UPDATE
    if not modificados.empty:
        print("\n→ ACTUALIZANDO registros existentes:")

    # Normalizar backend para diff_details
    df_backend_norm = df_backend.copy()
    df_backend_norm[id_field] = df_backend_norm[id_field].astype(str)

    for pk, row in modificados.iterrows():
        payload = row.to_dict()

        # Eliminar PK del PUT
        payload.pop(id_field, None)

        # Filtrar solo columnas válidas
        allowed_fields = ["nombre_sector", "centro_costo", "estado_sector"]
        payload = {k: v for k, v in payload.items() if k in allowed_fields}

        # Obtener valores anteriores para mostrar diferencias
        before = df_backend_norm.set_index(id_field).loc[pk]
        after = row

        cambios = diff_details(before, after)
        log(f"    ID {pk} — Cambios detectados:")
        for campo, (antes, despues) in cambios.items():
            log(f"      • {campo}: '{antes}' → '{despues}'")

        put_row(endpoint, pk, payload)
        log(f"    ✔ UPDATE OK — ID {pk}")
        resumen["modificados"] += 1

    # 5) DELETE
    if not eliminados.empty:
        print("\n→ ELIMINANDO registros:")

    for pk, row in eliminados.iterrows():
        log(f"    Eliminando ID {pk} ({row.to_dict()})")
        delete_row(endpoint, pk)
        log(f"    ✔ DELETE OK — ID {pk}")
        resumen["eliminados"] += 1

    print("\n=== RESUMEN ===")
    print(resumen)

    return resumen
