# Rapport Euclide — MAT-101 et MAT-102

Date : 27 octobre 2026.
Statut : MAT-102 réalisé selon le feu vert d'Atlas ; prêt pour revue, sans commit.

## Présentation

- Session : assistant Copilot SDK dans VS Code, conversation actuelle.
- Identifiant et nom d'équipe : Euclide, AGT-003 (attribué par Atlas).
- Rôle proposé : appui en analyse mathématique et validation des calculs.

## MAT-101 — périmètre et vérification

Mandat MAT-101 : lecture de `moteur.py` et `variantes.py`, tests ciblés existants,
puis jusqu'à trois cas limites reproductibles. Aucun code ni test n'a été modifié.
Aucun XML réel ni donnée persistante n'a été utilisé.

Commande exécutée :

```text
.venv/bin/python -B -m unittest test_generer test_variantes
Ran 15 tests — OK
```

## MAT-101 — constats et propositions

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

## Propositions à Atlas — décision réservée au chef de projet

1. **Répartiteur de colis : traiter explicitement le total minimum.**
   Quand le total est exactement le minimum autorisé, affecter directement les
   valeurs 10 à 17 aux huit articles, avec un départage déterministe fondé sur la
   part calculée, le poids puis l'index. Pour les totaux supérieurs, conserver la
   répartition proportionnelle actuelle et son contrôle final. Cela couvre la
   frontière sans modifier la règle métier.

2. **Générateur à ratios fixes : gérer le cas homogène séparément.**
   Ne pas assouplir la garde pour tous les cas de ratio moyen égal à une borne :
   si les ratios ne sont pas tous identiques, une moyenne exactement à leur
   minimum ou maximum ne peut pas être obtenue avec huit poids strictement positifs.
   Si les huit ratios sont égaux et que la cible FOB/poids leur est égale, essayer
   une répartition déterministe de poids entiers positifs ; calculer le FOB au
   centime par article et n'accepter la proposition que si le total exact est
   respecté. Rapporter clairement l'infaisabilité si les arrondis empêchent le
   total demandé.

3. **Évolution ultérieure : distinguer « impossible » de « non trouvé ».**
   La recherche actuelle est aléatoire et plafonnée. Une évolution utile serait
   de vérifier d'abord les conditions nécessaires de faisabilité, puis d'indiquer
   séparément « contraintes impossibles » et « aucune proposition trouvée dans la
   limite de recherche ». Une recherche déterministe/exhaustive pourrait être
   évaluée dans un lot distinct.

Ordre suggéré : faire décider Atlas des deux corrections ciblées, les transformer
en tests de régression et ne modifier le code qu'après autorisation explicite.
La troisième proposition relève d'un lot ultérieur ; elle n'est pas nécessaire
pour corriger les deux cas reproduits. Aucun code ni test supplémentaire n'a été
modifié ou exécuté dans le cadre de ces propositions.

## MAT-102 — corrections livrées pour revue

Atlas a ensuite autorisé les corrections ciblées dans `moteur.py`, `variantes.py`
et `test_mathematiques.py`. Aucun écran, schéma, calcul de taxe ni règle des ratios
variables n'a été changé.

### Modifications

- `moteur.py` : lorsque le total des colis est exactement le minimum mathématique,
  affecte les nombres distincts consécutifs dans un ordre déterministe (part, poids,
  index).
- `variantes.py` : les huit ratios identiques suivent une branche dédiée. Elle
  équilibre les poids entiers, calcule les FOB au centime, vérifie le total exact
  et cherche des partitions distinctes en ne faisant varier qu'une paire si nécessaire.
  Elle rejette les écarts impossibles selon la borne exacte des huit arrondis
  demi-haut et conserve le nombre de propositions demandé lorsqu'il existe assez
  de variantes. Le parcours `variables_libres` reste inchangé.
- `test_mathematiques.py` : ajoute cinq tests de régression sur minimum colis,
  déterminisme, total usuel, ratios homogènes et incompatibilité d'arrondi.

### Tests

Commande ciblée : `.venv/bin/python -B -m unittest test_mathematiques test_generer test_variantes`

Résultat ciblé avant le test de variantes supplémentaires : **19 tests réussis**.
Vérification finale : `.venv/bin/python -B -m unittest discover` → **92 tests réussis**.
`git diff --check` ne rapporte pas d'erreur de format sur les fichiers concernés.
Aucun XML réel, import, reset ou commit effectué.

### Limite et suite

La recherche secondaire des poids à ratios homogènes est limitée aux cas où le
poids total ne dépasse pas 100 000 kg, pour éviter une recherche coûteuse. Au-delà,
la répartition équilibrée est vérifiée ; si ses arrondis ne donnent pas exactement
le FOB cible, le générateur signale qu'aucune répartition exacte n'a été trouvée,
sans prétendre que le problème est mathématiquement impossible. Atlas décide de
l'intégration et d'une éventuelle évolution de cette limite.
