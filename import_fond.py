"""Import de références en tâche de fond (REF-102).

Le fil d'import possède sa propre connexion SQLite, ouverte et fermée dans ce fil.
Il ne touche jamais à Tkinter : il dépose des événements dans une file que le fil de
l'interface lit périodiquement. L'annulation intervient entre deux documents ; les
documents déjà importés restent dans la base.
"""
import dataclasses
import queue
import threading

import base_references
import import_references

NOM_DU_FIL = "import-references"


class TacheImport:
    def __init__(self, chemins, chemin_base=None, nom_lot=None):
        self.chemins = [str(c) for c in chemins]
        self.chemin_base = chemin_base
        self.nom_lot = nom_lot
        self.evenements = queue.Queue()   # ("progression", bilan, chemin) | ("fin", bilan) | ("erreur", message)
        self._annulation = threading.Event()
        self._fil = None

    def demarrer(self):
        if self._fil is not None:
            raise RuntimeError("Cette tâche d'import a déjà été démarrée.")
        self._fil = threading.Thread(target=self._executer, name=NOM_DU_FIL)
        self._fil.start()

    def _executer(self):
        # L'événement terminal n'est publié qu'après la fermeture de la connexion : quand
        # l'interface le reçoit, il ne reste plus rien d'ouvert dans ce fil.
        conn, terminal = None, ("erreur", "Import interrompu avant son terme.")
        try:
            conn = base_references.ouvrir(self.chemin_base)
            bilan = import_references.importer_lot(
                self.chemins, conn, nom_lot=self.nom_lot, annulation=self._annulation.is_set,
                progression=lambda b, chemin: self.evenements.put(
                    ("progression", dataclasses.replace(b, refus=list(b.refus), documents=list(b.documents)),
                     str(chemin))))
            terminal = ("fin", bilan)
        except Exception as exc:  # noqa: BLE001 - l'erreur est rapportée à l'interface, jamais perdue
            terminal = ("erreur", str(exc))
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception as exc:  # noqa: BLE001 - fermeture impossible : erreur terminale
                    terminal = ("erreur", f"Fermeture de la base impossible : {exc}")
            self.evenements.put(terminal)

    def annuler(self):
        self._annulation.set()

    def en_cours(self):
        return self._fil is not None and self._fil.is_alive()

    def arreter(self, delai=5.0):
        """Demande l'arrêt et attend au plus `delai` secondes. Renvoie True si le fil est terminé."""
        self.annuler()
        if self._fil is not None:
            self._fil.join(timeout=delai)
        return not self.en_cours()
