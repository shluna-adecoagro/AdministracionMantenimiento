# 1. Imports

import numpy as np
import pandas as pd
import os

# 2. Carga de datos

PATH = r"C:\Users\shluna\Proyectos\AdministracionMantenimiento\data\preprocessed"

df_OT = pd.read_excel(os.path.join(PATH, "OTs.xlsx"), sheet_name="OTs")
df_horas = pd.read_excel(os.path.join(PATH, "HorasGasoil.xlsx"), sheet_name="horas")# 

# 3. Procesamiento

def clean_data(df_OT):
    # Filtrar filas en función de las columnas: 'Estado', 'Fecha Inicio Programada'
    df_OT = df_OT[(df_OT['Estado'].str.contains("fin", regex=False, na=False, case=False)) & (df_OT['Fecha Inicio Programada'].apply(str).str.contains("2026", regex=False, na=False, case=False))]
    return df_OT

df_OT_clean = clean_data(df_OT.copy())
df_OT_clean.head(25)


def clean_data(df_horas):
    # Ordenar por columna: 'Fecha' (ascendente)
    df_horas = df_horas.sort_values(['Fecha'])
    # Filtrar filas según la columna: 'Fecha'
    df_horas = df_horas[df_horas['Fecha'].apply(str).str.contains("2026", regex=False, na=False, case=False)]

    return df_horas

df_horas_clean = clean_data(df_horas.copy())
df_horas_clean.head()

df_horas_patente = df_horas_clean.groupby("Patente").agg({"Acumulada": "max"}).reset_index()
df_horas_patente_min = df_horas_clean.groupby("Patente").agg({"Acumulada": "min"}).reset_index()
df_horas_patente["Acumulada"] = df_horas_patente["Acumulada"] - df_horas_patente_min["Acumulada"]

df_OT_patente = df_OT_clean.groupby("Activo").agg({"Tipo de Pedido de Trabajo": "count"}).reset_index()

df_patentes = pd.merge(df_horas_patente, df_OT_patente, left_on="Patente", right_on="Activo", how="inner")

df_patentes["MTBF"] = df_patentes["Acumulada"] / df_patentes["Tipo de Pedido de Trabajo"]

df_patentes = df_patentes.drop(columns=["Activo"])