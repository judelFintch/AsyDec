# Coordination des agents — AsyDec

Date : 27 octobre 2026.

## État de la communication

L'agent « Configuration et connexion » peut consulter le répertoire partagé, mais l'autre agent n'est pas joignable via les outils de communication de cette conversation.

Ce document est un point de coordination proposé. Il ne constitue pas un accord reçu de l'autre agent. Celui-ci doit le lire et écrire son accusé de réception dans son propre rapport pour confirmer la répartition.

## Répartition proposée

| Chantier | Agent responsable | Fichiers réservés |
|---|---|---|
| Connexion, compte administrateur, paramètres, verrouillage, reset | Configuration et connexion | `gestion_locale.py`, `ui/connexion.py`, `ui/parametres.py`, `test_gestion_locale.py` et `test_session_locale.py` |
| Références, import XML, persistance, analyse et historique | Références | `base_references.py`, `import_references.py`, `service_references.py`, `ratios.py`, `test_references.py`, `test_ratios.py`, `SUITE_MODULE_REFERENCES.md` |
| Navigation et démarrage | Intégration partagée, modifications minimales | `ui/app.py`, `asydec.py`, lanceurs `.command`, garde de lancement d'`interface.py` |
| Écrans de références et génération | Agent Références ; raccordements à annoncer | `ui/outils.py`, `ui/etapes.py`, `generer.py`, `variantes.py` |
| Exclusions locales | Intégration partagée, ajouts ciblés | `.gitignore` |
| Documentation générale | Prévenir avant de modifier | `README.md` |

## Procédure de communication

1. Lire ce fichier et le rapport de l'autre agent avant toute modification d'un fichier partagé.
2. Chaque agent met à jour uniquement son propre rapport : état, fichiers touchés, tests, questions et problèmes.
3. Annoncer les changements de contrat et demandes d'intégration avec un identifiant, par exemple `CFG-001`.
4. Avant d'éditer un fichier partagé, relire sa version sur disque ; ne pas remplacer le travail récent de l'autre agent par une ancienne copie.
5. Réserver une zone ou une fonction précise avant une modification simultanée. En l'absence d'accord, privilégier un nouveau module et documenter le raccordement.
6. Ne pas nettoyer les fichiers non suivis, supprimer une base, lancer un reset ou faire un commit global du travail de l'autre agent.
7. Exécuter les tests du chantier puis les tests communs avant d'annoncer une livraison intégrée.
8. Distinguer « proposé », « reçu », « intégré » et « vérifié » dans les rapports. Ne pas annoncer un rapport commun validé sans lecture des deux contributions.

Rapport Configuration : `RAPPORT_AGENT_CONFIGURATION.md`.
Rapport Références attendu : `RAPPORT_AGENT_REFERENCES.md` (à créer par cet agent).

## Contrat CFG-001 — Réinitialisation et SQLite

- Le reset conserve les XML originaux externes, les déclarations exportées, les exports Excel et le compte administrateur.
- Les données de travail sont archivées dans `SAUVEGARDES/reset-*` avant redémarrage : `DONNEES/asydec.db` et ses fichiers WAL/SHM, `DONNEES/sources`, `MODELES_XML`, `ETUDES_XML`, `registre.json`, `SAISIE.xlsx`, paramètres et préférences locales.
- Aucun reset n'est exécuté par les agents sur les données réelles pendant le développement.
- Le schéma SQLite reste la responsabilité de l'agent Références.
- Avant le reset, tout import actif doit être arrêté et toute connexion SQLite persistante doit être fermée.
- Point de raccordement prévu : `app.enregistrer_preparation_reset(callback)`. Le callback doit terminer rapidement, lever `ValueError` si le reset est impossible et ne pas supprimer de données.
- Aucun callback déclaré ne signifie pas que tous les services de références ont confirmé leur fermeture. Ce point reste à vérifier avec l'autre agent.

## Contrat CFG-002 — Compte et réglages

- `CONFIG_LOCAL/compte.json` appartient au module de connexion ; ne pas le déplacer dans la base des références.
- Le compte survit au reset. Les mots de passe sont salés et dérivés, jamais stockés en clair.
- Les préférences de l'interface passent dans `CONFIG_LOCAL/preferences.json`.
- Les réglages d'application passent dans `CONFIG_LOCAL/reglages.json`.
- Le module Configuration ne change pas les ratios, les règles fiscales ou le schéma des références.

## Contrat CFG-003 — Démarrage et session

- `ui.app.main()` demande la connexion avant de créer l'interface métier.
- La connexion locale ne chiffre pas les XML ni la base et ne remplace pas les permissions du système.
- Les lanceurs graphiques doivent converger vers ce démarrage pour présenter un parcours cohérent.
- Les accès programmatiques aux modules de calcul restent des API locales : aucune sécurité distante n'est annoncée.

## Questions en attente de l'autre agent

- [ ] Lecture du présent document confirmée dans son rapport.
- [ ] Des connexions SQLite restent-elles ouvertes pendant la session ?
- [ ] Quels imports/tâches de fond faut-il arrêter avant reset ?
- [ ] Le module écrit-il d’autres fichiers de travail que `DONNEES/asydec.db` et `DONNEES/sources` ? Les autres fichiers de `DONNEES`, notamment exports et sauvegardes, sont conservés par défaut.
- [ ] Quels raccordements prévoit-il dans `ui/app.py` ?

## Rapport commun

Le rapport commun doit distinguer les résultats des tests, les limites connues et les accords en attente. Pour l'instant, seul le chantier Configuration dispose d'un rapport de contribution ; aucun accord de l'autre agent n'a encore été reçu.

## Décision de direction — reprise du 27 octobre 2026

L'agent Références a accusé réception dans `RAPPORT_AGENT_REFERENCES.md`. Le chef de projet a répondu aux contrats REF-001/002/003 et fixé les priorités REF-P1 à REF-P4 dans `RAPPORT_AGENT_CONFIGURATION.md`.

Le canal par fichiers fonctionne avec lecture à chaque intervention, mais **ne déclenche pas automatiquement un autre agent**. Le relais utilisateur reste nécessaire pour lui demander de lire les nouvelles directives.

Les tests communs observés à cette étape : 63 tests réussis. La validation graphique Configuration reste en cours ; aucun résultat de capture visuelle n'est annoncé.

## Organisation active — tâche par tâche

- **Tous les agents rendent rapport** dans leur fichier, de manière concise.
- **Seul le chef de projet committe** ; aucun commit ni publication par l'agent Références.
- L'unique tâche active de l'agent Références est **REF-101**, définie à la fin de `RAPPORT_AGENT_CONFIGURATION.md`. Ne pas démarrer les autres lots.
- L'unique tâche active du chef de projet est **CFG-101** : vérifier et commiter le lot stable.
- Après livraison et revue d'une tâche, le chef attribue la suivante.
