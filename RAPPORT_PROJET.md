# Rapport du chef de projet — AsyDec

Date : 27 octobre 2026.

## Organisation

- Chef de projet : agent Configuration, responsable de la revue et de tous les commits.
- Agent Références : une seule tâche active, REF-101 (bibliothèque SQLite en consultation).
- Canal partagé : `COORDINATION_AGENTS.md` et un rapport distinct par agent.
- L'agent Références a confirmé avoir lu le protocole. Les nouveaux ordres sont lus à sa prochaine intervention ; ce canal ne le réveille pas automatiquement.

## État vérifié

| Lot | État |
|---|---|
| Simulation contrôlée, poids entiers, ratios variables ajustables | Tests automatisés réussis. |
| Extraction XML, SQLite, statuts et preuves | Livrés par l'agent Références ; tests inclus dans la suite commune. |
| Connexion locale, paramètres, verrouillage, reset avec archivage | Implémentés ; 16 tests dédiés réussis sur données temporaires. |
| Interface persistante de la bibliothèque | REF-101 assigné, livraison/revue attendues. |
| Références SQLite utilisées par le générateur | Étape ultérieure, non annoncée comme livrée. |
| Historique des modèles utilisés et réutilisation | Étape ultérieure, non annoncée comme livrée. |
| Import de fond et recette gros volumes | Étape ultérieure. |

## Résultats et limites

- Dernière suite commune complète reçue : **63 tests réussis**.
- Aucun reset des données réelles, aucun compte administrateur réel créé par les tests.
- Les essais graphiques Configuration ont été interrompus avant réception de leur résultat : recette visuelle non validée.
- Le reset possède un point de préparation ; REF-101 doit y fermer sa connexion et refuser une opération active.
- Les XML originaux externes, exports, sauvegardes et compte sont conservés par le reset. Les fichiers de travail connus sont archivés dans `SAUVEGARDES`.
- La connexion locale ne chiffre pas les XML ni la base de données.

## Ordre de travail

1. CFG-101 : vérification et commits du lot stable par le chef de projet.
2. REF-101 : rapport de livraison de l'interface de consultation, puis revue.
3. Attribuer une seule nouvelle tâche après validation du lot précédent.

Aucune publication GitHub ni aucun déploiement n'est prévu dans cette étape.

## Livraison CFG-101

Le chef a créé les commits :

- `7bd62b3` : règles communes, poids entiers et ratios ajustables.
- `ad30a93` : stockage et extraction des références, taxes et statuts.
- `43932b9` : interface avec connexion, paramètres et reset récupérable.
- Un commit de documentation regroupe le canevas, la coordination et les rapports.

Suite complète : **63 tests réussis**. Rien n'a été publié. Le dépôt est prêt pour la tâche unique REF-101 ; son résultat et sa revue restent attendus. La recette visuelle Configuration reste à confirmer.

## État actualisé — revue du travail REF-101 en cours

- Le socle validé reste dans Git jusqu'au commit `966c753` (protocole d'accord préalable).
- En cours, non validé : `ui/references.py` et raccordements dans `ui/app.py`.
- Test relancé sur cet état de travail : **63 tests, 62 réussis, 1 erreur** dans le test de fermeture de session. Le double de test n'intègre pas encore la nouvelle fermeture SQLite ; correction du test et vérification du contrat attendues.
- Aucun rapport de livraison REF-101 reçu à cette vérification. Le code de bibliothèque n'est pas encore accepté ni commité.
- Autres réserves : périmètre de la page plus large que la consultation assignée, fuseau d'affichage à fixer explicitement, recette visuelle à confirmer.
- Priorité unique : rapport et correction de REF-101 avant tout nouveau lot. Les références SQLite du générateur, l'historique de réutilisation et l'import de fond restent ultérieurs.

## Bilan CAP AsyDec

L'équipe dispose maintenant de noms et d'un registre dans `EQUIPE.md` : Atlas (chef) et Quartz (Références). Tout nouvel agent doit se présenter et attendre son périmètre autorisé.

Nouvelle suite complète exécutée par Atlas : **66 tests réussis**. L'erreur de fermeture de la revue précédente ne se reproduit plus. REF-101 demeure non validé jusqu'au contrôle du périmètre, des tests spécifiques et du fuseau. Bilan de productivité : `RAPPORT_PRODUCTIVITE.md`.

## Reprise active

Euclide (AGT-003), agent d'appui mathématique, s'est présenté conformément au protocole. Atlas lui a autorisé MAT-101 : lecture, tests existants ciblés et trois cas limites au maximum, sans changement de code.

Quartz conserve l'unique tâche de code REF-101. Son autorisation de finitions est reconfirmée et répond explicitement à sa demande encore affichée dans son rapport. Atlas attend le bilan avant revue et commit ; aucun changement de périmètre n'est autorisé.

## Livraisons validées — REF-101 et MAT-101

- **Quartz / REF-101** : bibliothèque SQLite en consultation intégrée après revue. Filtres, détail des articles/taxes, provenance et historique consultables ; opérations d'import, modification de statut et export hors périmètre désactivées.
- **Vérification Atlas** : 74 tests réussis, comprenant les tests graphiques temporaires de consultation seule. Cette vérification ne constitue pas une certification du rendu visuel complet.
- **Euclide / MAT-101** : revue mathématique reçue et deux cas reproduits par le chef. À corriger dans une future tâche : répartiteur de colis au minimum en cas d'égalité ; branche de génération stricte lorsque tous les ratios sont identiques.
- Pas de nouveau lot lancé. Le raccordement du générateur à SQLite, l'historique de réutilisation et l'import de fond restent à développer.
