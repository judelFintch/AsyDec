# CAP AsyDec — tableau de bord actuel
Date : 27 octobre 2026. Responsable : Atlas.
Règle utilisateur reçue : relecture croisée avant commit des lots Atlas ; revue des livraisons avant nouveaux lots.
Objectif : références persistantes → propositions contrôlées → export XML → comparaison → suivi.
Dernière suite : 167 tests réussis (UI-113). Cela ne lève pas les réserves ci-dessous.

| Agent | Priorité | État / action |
|---|---|---|
| Atlas | 1 | Revue REF-103, livré depuis 14 h 57, avant nouveau lot. |
| Euclide | 1 | MAT-102 : corriger FOB nuls, cas 9 kg / 0,01 USD / ratio .003. GO ciblé confirmé. |
| Quartz | 2 | Plan import médiathèque en fond et migration vers base commune ; lecture seule avant GO édition. |
| Quartz | 3 | REF-104 Recharger retenu ; réservation ui/app.py à venir, reconnexion maintenue. |
| Relais | Terminé | UI-108 à UI-113 livrés, relus, testés et commités ; audit architecture confirmé. |

Alertes fondées : gros imports synchrones ; sauvegarde références omet la base modèles.
Décision : base commune versionnée, migration sans perte à préparer, aucune suppression de données.
Validation locale et acceptation douanière restent deux notions distinctes.
Fichiers des contributeurs non commités restent réservés à leurs lots.
Détails et réponses : dernière section RAPPORT_AGENT_CONFIGURATION.md.
Canal externe : fichiers partagés, lus à la prochaine intervention des agents.
