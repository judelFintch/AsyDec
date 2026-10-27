# Équipe CAP AsyDec

CAP : Contrôle, Analyse, Production.

| Identifiant | Nom de projet | Session connue | Rôle |
|---|---|---|---|
| AGT-001 | Atlas | Codex, conversation principale | Chef de projet : arbitrage, configuration, revue, intégration et commits. |
| AGT-002 | Quartz | Claude Code `outils-65` / `19dadd` (identité déclarée dans son rapport) | Références XML, données SQLite, consultation et analyse. |
| AGT-003 | Euclide | Copilot SDK dans VS Code (session déclarée dans son rapport) | Revue mathématique et cas limites, sans modification des règles. |
| AGT-004 | Relais | Sous-agent Codex `/root/simplifier_totaux` | Lots ciblés attribués par Atlas, rapport préalable, tests et livraison sans commit. |

Ces noms sont des identifiants de travail pour les agents existants, pas des agents supplémentaires.

## Accueil d'un nouvel agent

Avant toute action, un nouvel agent déclare dans son rapport : session, rôle proposé, tâche demandée et fichiers concernés. Atlas lui attribue un identifiant `AGT-003`, etc., et un nom unique dans ce registre, puis autorise ou refuse la tâche. Aucun agent non présenté ne commence des modifications.

## Fonctionnement

- Une tâche autorisée à la fois par agent.
- Proposition → accord d'Atlas → travail ciblé → rapport → revue → commit par Atlas.
- Rapports courts : résultat, fichiers, tests, blocages, action attendue.
- Ne pas confondre quantité de code et fonctionnalité livrée.
- Pas d'engagement implicite d'un nouveau lot après une livraison.
- Communication par fichiers : pas de réveil automatique des autres sessions.

Rapports : `RAPPORT_AGENT_CONFIGURATION.md` (Atlas), `RAPPORT_AGENT_REFERENCES.md` (Quartz), `RAPPORT_AGENT_MATHEMATIQUES.md` (Euclide), `RAPPORT_PRODUCTIVITE.md` (bilan).
