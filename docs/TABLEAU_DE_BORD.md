# CAP AsyDec — tableau de bord actuel
Date : 27 octobre 2026. Responsable : Atlas.
Règle : plan → GO → livraison → revue croisée → commit Atlas ; lots séquentiels pour économiser les tokens.
Objectif : références persistantes → propositions contrôlées → export XML → comparaison → suivi.
Dernière suite : 226 tests réussis (27/10, UI-116, UI-117 et REF-104 non commités).

| Agent | Lot | État |
|---|---|---|
| Quartz | REF-103 | Revu et intégré : 93a4a11 ; agent laissé au repos. |
| Euclide / Relais | MAT-102 | Intégré : 801b8e5, FOB nuls refusés, minimum colis corrigé. |
| Relais | ALERTE005 | Import médiathèque délégué au worker existant, 43 tests ciblés et suite complète OK. |
| Atlas | Revue/intégration | Rapports et code relus, commits séparés. |
| Plume (Claude Code) | UI-116 / UI-117 | PDF intégré 67c1dd8. UI-116 reprise (lot Codex) vérifiée ; UI-117 plaque, trace des comparaisons, détail des taxes. 213 tests OK, revue Atlas attendue, non commité : RAPPORT_AGENT_PDF.md. |

Limite import : repérage/tri des fichiers encore synchrones, traitement XML en fond.
À traiter : migration versionnée des modèles vers base commune, sauvegarde cohérente et liens de provenance.
La sauvegarde des références n'est pas une sauvegarde complète des modèles générés.
REF-104 Recharger implémenté par Plume sur ordre utilisateur (revue Atlas attendue) ; reconnexion conservée.
Aucun XML réel modifié. Aucun lot supplémentaire lancé automatiquement.
Détails : dernières sections RAPPORT_AGENT_CONFIGURATION.md.
Canal Quartz/Euclide : rapports partagés à leur prochaine intervention ; Relais joignable par sous-agent.
