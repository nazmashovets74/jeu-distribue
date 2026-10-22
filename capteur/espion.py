import random, statistics  # випадковість і середнє


def fausse_temperature(valeurs_autres: list[float]) -> float:
    """Значення, відмінне на 5-10% від середнього інших датчиків."""
    base = statistics.mean(valeurs_autres)  # середнє чесних значень
    ecart = max(abs(base) * random.uniform(0.05, 0.10), 0.5)  # 5-10%, мінімум 0.5 °C
    signe = random.choice([-1, 1])  # вище чи нижче
    return round(base + signe * ecart, 1)


if __name__ == "__main__":  # швидкий тест
    print(fausse_temperature([12.0, 12.4, 11.8]))