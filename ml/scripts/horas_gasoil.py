# Imports
import pandas as pd
import os

# Carga de datos
df_horas = pd.read_excel(os.path.join("..", "data", "preprocessed", "HorasGasoil.xlsx"), sheet_name="horas")
df_gasoil = pd.read_excel(os.path.join("..", "data", "preprocessed", "HorasGasoil.xlsx"), sheet_name="gasoil")

# Procesamiento

## Reordenar los DataFrames por patente y fecha
df_horas = df_horas.sort_values(["Patente", "Fecha"]).reset_index(drop=True)
df_gasoil = df_gasoil.sort_values(["PATENTE", "FECHA"]).reset_index(drop=True)

## Calcular las diferencias entre horas acumuladas y días para cada patente
df_horas["delta_horas"] = df_horas.groupby("Patente")["Acumulada"].diff()
df_horas["delta_dias"] = df_horas.groupby("Patente")["Fecha"].diff().dt.days

## Calcular las diferencias entre litros acumulados y días para cada patente entre fechas consecutivas
df_gasoil["delta_dias"] = df_gasoil.groupby("PATENTE")["FECHA"].diff().dt.days

## Eliminar filas con valores nulos en las columnas de diferencias de horas y días para horas acumuladas
df_horas.dropna(subset=["delta_horas", "delta_dias"], inplace=True)

## Eliminar filas con valores nulos en la columna de diferencias de días para gasoil
df_gasoil.dropna(subset=["delta_dias"], inplace=True)

## Calcular la tasa de uso diario y consumo diario para cada patente entre fechas consecutivas
df_horas["tasa_uso_diario"] = df_horas["delta_horas"] / df_horas["delta_dias"]
df_gasoil["tasa_consumo_diario"] = df_gasoil["LITROS"] / df_gasoil["delta_dias"]

## Agregar columnas de tasa de uso diario global, mediana y promedio para cada patente
df_horas_patente = df_horas.groupby("Patente").agg({"delta_horas": "sum", "delta_dias": "sum"}).reset_index()
df_horas_patente["tasa_uso_diario_global"] = df_horas_patente["delta_horas"] / df_horas_patente["delta_dias"]
df_horas_patente["tasa_uso_mediana"] = df_horas.groupby("Patente")["tasa_uso_diario"].median().values

## Agregar columnas de tasa de consumo diario global, mediana y promedio para cada patente
df_gasoil_patente = df_gasoil.groupby("PATENTE").agg({"LITROS": "sum", "delta_dias": "sum"}).reset_index()
df_gasoil_patente["tasa_consumo_diario_global"] = df_gasoil_patente["LITROS"] / df_gasoil_patente["delta_dias"]
df_gasoil_patente["tasa_consumo_diario_mediana"] = df_gasoil.groupby("PATENTE")["tasa_consumo_diario"].median().values

## Combinar los DataFrames de horas y gasoil por patente y calcular el consumo por hora global, mediana y promedio
df_horas_gasoil = pd.merge(df_horas_patente, df_gasoil_patente, left_on="Patente", right_on="PATENTE", how="inner")
df_horas_gasoil.drop(columns=["delta_horas", "delta_dias_x", "PATENTE", "LITROS", "delta_dias_y"], inplace=True)
df_horas_gasoil["consumo_por_hora_global"] = df_horas_gasoil["tasa_consumo_diario_global"] / df_horas_gasoil["tasa_uso_diario_global"]
df_horas_gasoil["consumo_por_hora_mediana"] = df_horas_gasoil["tasa_consumo_diario_mediana"] / df_horas_gasoil["tasa_uso_mediana"]