# CAP AsyDec — tableau de bord actuel
Date : 27 octobre 2026. Responsable : Atlas. Les anciens rapports servent d'historique.
Objectif : données XML persistantes → références contrôlées → propositions → choix → export et suivi.
Dernière validation complète : 74 tests réussis ; REF-101 intégré (`97c2f9c`).

| Agent | Tâche autorisée | Livrable attendu |
|---|---|---|
| Quartz (AGT-002) | REF-102 livré, revue Atlas attendue | Import multiple/dossier ; 82 tests annoncés par Quartz, à vérifier indépendamment. |
| Euclide (AGT-003) | MAT-102 : corriger les deux cas limites confirmés | Correctifs minimaux colis/ratios homogènes et tests de régression. |
| Atlas (AGT-001) | Revue, arbitrage et intégration | Vérifier les rapports et tests, puis commiter chaque lot séparément. |

Autorisation détaillée : dernières sections de `RAPPORT_AGENT_CONFIGURATION.md`.
Attendu de chaque contributeur : réception → travail dans son périmètre → rapport → attente de revue.
Fichiers partagés : `ui/app.py` réservé aux raccordements REF-102 ; moteurs réservés à MAT-102.
Commits : Atlas uniquement. Aucune publication ni import de données réelles par les agents.

À suivre ensuite, pas encore autorisé : statuts dans l'interface, références SQLite du générateur,
contrôle contextualisé des ratios variables, historique des utilisations/réutilisations et reprise des études.
Ratios variables : restent ajustables ; aucun plafond arbitraire ajouté par ce mandat.
Réserves : recette visuelle complète et acceptation effective SYDONIA non garanties par les tests.
