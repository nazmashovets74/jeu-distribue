"""Simule N parties avec les VRAIES temperatures de 3 villes voisines."""
import random

from strategies.mediane import choisir_suspect

IDS = ["1", "2", "3"]

# ВПИШИ СВОИ 3 ЧИСЛА из шага 1 (id датчика -> температура его города)
VRAIES = {"1": 11.8, "2": 12.3, "3": 11.5}


def partie(mode):
    espion = random.choice(IDS)
    # шпион копирует среднее честных, +/-10 %
    ref = sum(v for i, v in VRAIES.items() if i != espion) / 2
    sign = random.choice([-1, 1])
    h = {i: [] for i in IDS}
    for _ in range(5):
        for i in IDS:
            if i == espion:
                k = random.uniform(-0.10, 0.10) if mode == "alea" else sign * 0.10
                h[i].append(ref * (1 + k))
            else:
                h[i].append(VRAIES[i])
    honnetes = [i for i in IDS if i != espion]
    return all(choisir_suspect(i, h) == espion for i in honnetes)


if __name__ == "__main__":
    N = 5000
    print("Temperatures reelles :", VRAIES)
    for mode in ("alea", "fixe"):
        ok = sum(partie(mode) for _ in range(N))
        print(f"espion {mode:<4}  capteurs gagnent {100*ok/N:5.1f} %")