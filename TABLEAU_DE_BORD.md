# CAP AsyDec — tableau de bord actuel
Date : 27 octobre 2026. Responsable : Atlas. Les anciens rapports servent d'historique.
Objectif : données XML persistantes → références contrôlées → propositions → choix → export et suivi.
Dernière suite sur état de travail : 91 tests réussis ; REF-102 et mot de passe 8 validés, MAT-102 en revue.

| Agent | Tâche autorisée | Livrable attendu |
|---|---|---|
| Quartz (AGT-002) | REF-103 autorisé après REF-102 validé | Activer les statuts avec preuve/motif/auteur, sans activer les exports. |
| Euclide (AGT-003) | MAT-102 : dernière retouche autorisée | Interdire tout FOB nul dans la nouvelle branche homogène ; régression 9 kg / 0,01 USD. |
| Atlas (AGT-001) | Revue, arbitrage et intégration | Vérifier les rapports et tests, puis commiter chaque lot séparément. |

Autorisation détaillée : dernières sections de `RAPPORT_AGENT_CONFIGURATION.md`.
Attendu de chaque contributeur : réception → travail dans son périmètre → rapport → attente de revue.
Fichiers partagés : `ui/app.py` réservé aux raccordements autorisés de Quartz ; moteurs réservés à MAT-102.
Commits : Atlas uniquement. Aucune publication ni import de données réelles par les agents.

À suivre ensuite, pas encore autorisé : références SQLite du générateur,
contrôle contextualisé des ratios variables, historique des utilisations/réutilisations et reprise des études.
Ratios variables : restent ajustables ; aucun plafond arbitraire ajouté par ce mandat.
Réserves : recette visuelle complète et acceptation effective SYDONIA non garanties par les tests.
