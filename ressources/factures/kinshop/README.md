# Modèles Word originaux KINSHOP

- `facture.docx` : copie intégrale du fichier fourni `ORD0000013709+-1 (1).docx`.
- `packing.docx` : copie intégrale du fichier fourni `LCL (1).docx`.
- `sceau.png` : image du sceau extraite de la référence ; les deux Word contiennent
  déjà leurs images et sont remplis sans ajout de sceau.

Le générateur remplace les textes variables dans `word/document.xml`.
La taille et l’ajustement horizontal des nombres trop longs sont adaptés à la
largeur disponible, sans modifier les cadres ni arrondir les valeurs.
Les autres parties du fichier restent identiques octet pour octet : médias,
styles, relations, en-têtes, pieds de page et paramètres d'impression.
Aucune reconstruction de tableau, aucune suppression de ligne et aucun ajout de dessin.

Les modèles comportent trois lignes d'articles. Les lignes non utilisées sont vidées
sans suppression. Au-delà de trois articles, la génération demande un modèle plus grand.
Les dates, commandes et références de l'ancienne opération sont remplacées ; les
mentions commerciales fixes, le sceau et la signature du modèle fourni sont conservés.
