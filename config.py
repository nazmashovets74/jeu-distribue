BROKER_HOST = "rpi-a.local"
BROKER_PORT = 1883
NB_TOURS = 5
INTERVALLE = 5  # secondes

CAPTEURS = {
    "1": {"ville": "Annecy",        "lat": 45.899, "lon": 6.129},
    "2": {"ville": "Chambery",      "lat": 45.564, "lon": 5.917},
    "3": {"ville": "Aix-les-Bains", "lat": 45.688, "lon": 5.915},
    # Capteur virtuel : la consigne demande 4 RPi, nous n'en avons que 3.
    # Même programme que les autres, lancé en plus sur RPi A (./jeu.sh capteur 4).
    "4": {"ville": "Rumilly",       "lat": 45.866, "lon": 5.944},
}
