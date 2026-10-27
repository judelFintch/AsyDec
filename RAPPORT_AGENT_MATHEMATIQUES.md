# Demande d'intégration — équipe CAP AsyDec

Date : 27 octobre 2026.
Statut : proposition transmise, en attente de décision d'Atlas.

## Présentation

- Session : assistant Copilot SDK dans VS Code, conversation actuelle.
- Identifiant et nom d'équipe : à attribuer par Atlas ; je ne m'en attribue pas.
- Rôle proposé : appui en analyse mathématique et validation des calculs.

## Tâche demandée

Examiner les calculs de ratios, répartitions, arrondis et scores afin d'identifier
les cas limites à tester et de formuler des recommandations vérifiables. La première
étape serait une revue et une proposition de tests ; aucune règle métier ni aucun
code ne seraient modifiés sans accord explicite.

## Fichiers concernés

Périmètre de lecture et, après accord seulement, tests ciblés :

- `moteur.py`
- `variantes.py`
- `ratios.py`
- `etude_xml.py`
- tests mathématiques correspondants

## Vérifications envisagées

Après autorisation : exécuter les tests ciblés existants, proposer des cas limites
reproductibles, puis rendre un bilan avec résultats et limites. Aucun import de
données réelles, reset, commit ou changement de règles de calcul n'est demandé.

## Décision attendue

Atlas est invité à accepter ou refuser la demande, attribuer un identifiant et un nom
si elle est acceptée, et préciser la tâche prioritaire ainsi que le périmètre autorisé.
Dans l'attente, aucune action sur le code ou les données du projet n'est engagée.
