import pandas as pd

def load_excel(path):
    return pd.read_excel(path).fillna(value=None)
