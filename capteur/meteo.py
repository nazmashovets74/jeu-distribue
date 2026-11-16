import requests

URL = "https://api.open-meteo.com/v1/forecast"


def get_temperature(lat: float, lon: float) -> float:
    """Température actuelle (°C) aux coordonnées données."""
    r = requests.get(URL, params={
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m",  # seulement la température actuelle
    }, timeout=10)
    r.raise_for_status()  # erreur si l'API ne répond pas 200
    return float(r.json()["current"]["temperature_2m"])


if __name__ == "__main__":  # test rapide
    print(get_temperature(45.90, 6.13))  # Annecy
