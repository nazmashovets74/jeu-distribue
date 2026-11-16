import random
import statistics


def fausse_temperature(valeurs_autres: list[float]) -> float:
    """Valeur écartée de 5 à 10 % de la moyenne des autres capteurs."""
    base = statistics.mean(valeurs_autres)                     # moyenne des valeurs honnêtes
    ecart = max(abs(base) * random.uniform(0.05, 0.10), 0.5)   # 5-10 %, au moins 0,5 °C
    signe = random.choice([-1, 1])                             # au-dessus ou en dessous
    return round(base + signe * ecart, 1)


if __name__ == "__main__":  # test rapide
    print(fausse_temperature([12.0, 12.4, 11.8]))
