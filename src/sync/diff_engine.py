import pandas as pd

def normalize_df(df):
    df = df.copy()
    df.columns = df.columns.str.strip()

    for col in df.columns:
        df[col] = (
            df[col]
            .astype(str)
            .str.strip()
            .replace({
                "nan": None,
                "NaN": None,
                "None": None,
                "": None,
                " ": None
            })
        )
    return df


def normalize_pk(df, id_field):
    """
    Normaliza la PK:
    - Convierte a string
    - Reemplaza valores inválidos por None
    """
    df[id_field] = (
        df[id_field]
        .astype(str)
        .str.strip()
        .replace({
            "nan": None,
            "NaN": None,
            "None": None,
            "": None,
            " ": None,
            "0": None
        })
    )
    return df


def compute_diff(df_excel, df_backend, id_field):

    df_excel = normalize_df(df_excel)
    df_backend = normalize_df(df_backend)

    df_excel = normalize_pk(df_excel, id_field)
    df_backend = normalize_pk(df_backend, id_field)

    # Nuevos = PK vacía
    nuevos = df_excel[df_excel[id_field].isna()]

    existentes_excel = df_excel[df_excel[id_field].notna()]
    existentes_backend = df_backend[df_backend[id_field].notna()]

    if not existentes_excel.empty:
        existentes_excel = existentes_excel.set_index(id_field)

    if not existentes_backend.empty:
        existentes_backend = existentes_backend.set_index(id_field)

    eliminados = existentes_backend.loc[
        ~existentes_backend.index.isin(existentes_excel.index)
    ]

    comunes_excel = existentes_excel.loc[
        existentes_excel.index.isin(existentes_backend.index)
    ]

    comunes_backend = existentes_backend.loc[
        existentes_backend.index.isin(existentes_excel.index)
    ]

    comunes_backend = comunes_backend.reindex(columns=comunes_excel.columns)

    modificados = comunes_excel[
        (comunes_excel != comunes_backend).any(axis=1)
    ]

    return nuevos, modificados, eliminados
