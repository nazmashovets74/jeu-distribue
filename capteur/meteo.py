import requests  # HTTP-запити

URL = "https://api.open-meteo.com/v1/forecast"  # API Open-Meteo


def get_temperature(lat: float, lon: float) -> float:
    """Поточна температура (°C) для координат."""
    r = requests.get(URL, params={
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m",  # лише поточна температура
    }, timeout=10)
    r.raise_for_status()  # помилка, якщо API не відповів 200
    return float(r.json()["current"]["temperature_2m"])


if __name__ == "__main__":  # швидкий тест
    print(get_temperature(45.90, 6.13))  # Annecy