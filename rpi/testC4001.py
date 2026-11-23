import time

from rpi.models.c4001_presence import presence, fermer

try:
    while True:
        etat = presence()
        if etat is None:
            print("capteur muet / pas de donnees")
        elif etat:
            print("il y a quelqu'un")
        else:
            print("personne")
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    fermer()