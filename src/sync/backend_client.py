import requests

def get_all(url):
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def create(url, data):
    r = requests.post(url, json=data)
    r.raise_for_status()
    return r.json()

def update(url, record_id, data):
    r = requests.put(f"{url}/{record_id}", json=data)
    r.raise_for_status()
    return r.json()

def delete(url, record_id):
    r = requests.delete(f"{url}/{record_id}")
    r.raise_for_status()
    return True
