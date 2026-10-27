# Rapport MAT-101 — revue mathématique ciblée

Date : 27 octobre 2026.
Statut : tâche exécutée sur feu vert d'Atlas ; en attente de revue.

## Présentation

- Session : assistant Copilot SDK dans VS Code, conversation actuelle.
- Identifiant et nom d'équipe : Euclide, AGT-003 (attribué par Atlas).
- Rôle proposé : appui en analyse mathématique et validation des calculs.

## Périmètre et vérification

Mandat MAT-101 : lecture de `moteur.py` et `variantes.py`, tests ciblés existants,
puis jusqu'à trois cas limites reproductibles. Aucun code ni test n'a été modifié.
Aucun XML réel ni donnée persistante n'a été utilisé.

Commande exécutée :

```text
.venv/bin/python -B -m unittest test_generer test_variantes
Ran 15 tests — OK
```

## Constats — deux cas reproductibles

1. **Moyen — colis gradués, cas d'égalité et total minimal.**  
   `moteur.colis_gradues([1]*8, [1]*8, 108)` lève `ValueError`, alors que
   `[10,11,12,13,14,15,16,17]` est une répartition valide, distincte, d'au moins
   10 colis par article et de somme 108. Le cas expose une limite de l'algorithme
   de départage lorsque les parts sont égales.

2. **Moyen — ratios identiques au ratio global.**  
   `variantes.generer(800, 800, 108, [1.0]*8, nombre=1)` lève `ValueError` :
   la garde exige strictement `min(limites) < FOB/poids < max(limites)`. Ici,
   les huit articles peuvent avoir chacun 100 kg et 100 USD ; la moyenne cible
   égale exactement les ratios et les totaux sont cohérents. Le cas n'est pas
   couvert par les 15 tests ciblés.

Les deux constats sont reproductibles en mémoire. Le premier provient d'un appel
direct au répartiteur de colis ; le second de l'API de génération. Aucune correction
ni proposition de modification du code n'est incluse dans ce mandat.

## Suite attendue

Atlas peut décider si ces cas doivent être transformés en tests et autoriser une
tâche de correction distincte. Je n'engage pas d'autre modification ni test sans
nouvelle consigne.
