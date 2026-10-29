"""Impression PDF des modèles validés et des comparaisons, sans dépendance externe.

Le PDF est un document de travail : il ne modifie ni la base, ni les XML, et ne vaut
pas acceptation douanière. Polices standard Helvetica, encodage WinAnsi (accents français).
"""
from datetime import datetime
from pathlib import Path
import unicodedata

from asydec.formats import date_locale, nombre

LARGEUR, HAUTEUR = 842, 595          # A4 paysage, en points
MARGE = 36
BAS = MARGE + 18                      # réserve pour le pied de page
MENTION_MODELE = 'Validation locale : ne vaut pas acceptation douanière.'
MENTION_COMPARAISON = 'Écart = fichier fourni - XML généré. Un écart ne prouve ni erreur ni acceptation douanière.'

# Largeurs Helvetica (AFM, millièmes de taille) pour les caractères 32 à 126.
_LARGEURS = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
             556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
             1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
             667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
             333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
             556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_REMPLACEMENTS = {'−': '-', ' ': ' ', ' ': ' ', ' ': ' ', '≤': '<=',
                  '≥': '>=', '≠': '!=', '✓': 'OK', '⚠': '!', '→': '->'}


def _texte(valeur):
    texte = str(valeur)
    for avant, apres in _REMPLACEMENTS.items():
        texte = texte.replace(avant, apres)
    return texte


def largeur(texte, taille, gras=False):
    total = 0
    for c in _texte(texte):
        # Lettres accentuées : largeur de la lettre de base, approximation suffisante.
        o = ord(unicodedata.normalize('NFKD', c)[0])
        total += _LARGEURS[o - 32] if 32 <= o <= 126 else 556
    return total * taille / 1000 * (1.06 if gras else 1)


def _couper(texte, taille, maximum, gras=False):
    texte = _texte(texte)
    if largeur(texte, taille, gras) <= maximum:
        return texte
    while texte and largeur(texte + '…', taille, gras) > maximum:
        texte = texte[:-1]
    return texte + '…'


def _lignes(texte, taille, maximum, gras=False):
    sortie = []
    for paragraphe in _texte(texte).split('\n'):
        ligne = ''
        for mot in paragraphe.split(' '):
            essai = f'{ligne} {mot}' if ligne else mot
            if ligne and largeur(essai, taille, gras) > maximum:
                sortie.append(ligne)
                ligne = mot
            else:
                ligne = essai
        sortie.append(ligne)
    return sortie


def _chaine(texte):
    octets = _texte(texte).encode('cp1252', errors='replace')
    return '(' + octets.decode('latin-1').replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') + ')'


class Document:
    """Pages de texte et de tableaux, paginées automatiquement."""

    def __init__(self):
        self.pages = []
        self._nouvelle_page()

    def _nouvelle_page(self):
        self.page = []
        self.pages.append(self.page)
        self.y = HAUTEUR - MARGE

    def _place(self, hauteur):
        if self.y - hauteur < BAS:
            self._nouvelle_page()

    def _ecrire(self, x, y, texte, taille, gras=False):
        self.page.append(f'BT /{"F2" if gras else "F1"} {taille} Tf {x:.2f} {y:.2f} Td {_chaine(texte)} Tj ET')

    def titre(self, texte):
        self._place(24)
        self.y -= 18
        self._ecrire(MARGE, self.y, texte, 16, True)
        self.y -= 8

    def paragraphe(self, texte, taille=9, gras=False):
        for ligne in _lignes(texte, taille, LARGEUR - 2 * MARGE, gras):
            self._place(taille + 3)
            self.y -= taille + 3
            self._ecrire(MARGE, self.y, ligne, taille, gras)

    def espace(self, hauteur=6):
        self.y -= hauteur

    def tableau(self, colonnes, lignes, taille=8):
        """colonnes : [(titre, largeur relative, 'w' ou 'e')] ; lignes : (valeurs, gras)."""
        total = sum(c[1] for c in colonnes)
        largeurs = [c[1] * (LARGEUR - 2 * MARGE) / total for c in colonnes]
        pas = taille + 6

        def entete():
            self._place(2 * pas)
            self.page.append(f'0.9 g {MARGE} {self.y - pas:.2f} {LARGEUR - 2 * MARGE} {pas} re f 0 g')
            self._rangee([c[0] for c in colonnes], colonnes, largeurs, taille, True)

        entete()
        for valeurs, gras in lignes:
            if self.y - pas < BAS:
                self._nouvelle_page()
                entete()
            self._rangee(valeurs, colonnes, largeurs, taille, gras)
            self.page.append(f'0.8 G 0.4 w {MARGE} {self.y:.2f} m {LARGEUR - MARGE} {self.y:.2f} l S 0 G')
        self.espace()

    def _rangee(self, valeurs, colonnes, largeurs, taille, gras):
        self.y -= taille + 6
        x = MARGE
        for valeur, (_, _, alignement), l in zip(valeurs, colonnes, largeurs):
            texte = _couper(valeur, taille, l - 6, gras)
            dx = l - 3 - largeur(texte, taille, gras) if alignement == 'e' else 3
            self._ecrire(x + dx, self.y + 4, texte, taille, gras)
            x += l

    def octets(self, pied=''):
        objets = ['<< /Type /Catalog /Pages 2 0 R >>', None,
                  '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
                  '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>']
        pages = []
        for numero, contenu in enumerate(self.pages, 1):
            bas = f'{pied} · page {numero}/{len(self.pages)}' if pied else f'page {numero}/{len(self.pages)}'
            flux = '\n'.join(contenu + [f'BT /F1 7 Tf {MARGE} {MARGE - 6} Td {_chaine(bas)} Tj ET'])
            flux = flux.encode('latin-1')
            objets.append(b'<< /Length %d >>\nstream\n' % len(flux) + flux + b'\nendstream')
            objets.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {LARGEUR} {HAUTEUR}] '
                          f'/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {len(objets)} 0 R >>')
            pages.append(f'{len(objets)} 0 R')
        objets[1] = f'<< /Type /Pages /Kids [{" ".join(pages)}] /Count {len(pages)} >>'
        sortie = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
        positions = []
        for numero, objet in enumerate(objets, 1):
            positions.append(len(sortie))
            corps = objet if isinstance(objet, bytes) else objet.encode('latin-1')
            sortie += b'%d 0 obj\n' % numero + corps + b'\nendobj\n'
        debut = len(sortie)
        sortie += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objets) + 1)
        sortie += b''.join(b'%010d 00000 n \n' % p for p in positions)
        sortie += b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objets) + 1, debut)
        return bytes(sortie)

    def enregistrer(self, chemin, pied=''):
        chemin = Path(chemin)
        temporaire = chemin.with_name(chemin.name + '.tmp')
        temporaire.write_bytes(self.octets(pied))
        temporaire.replace(chemin)
        return chemin


def _pied(utilisateur, mention, maintenant):
    quand = (maintenant or datetime.now()).strftime('%d/%m/%Y %H:%M')
    return f'AsyDec · imprimé le {quand} par {utilisateur or "?"} · {mention}'


def pdf_modele(d, chemin, utilisateur, maintenant=None):
    """PDF d'un modèle (résultat de modeles_generes.detail) ; refusé s'il n'est pas validé."""
    if d.get('statut') != 'valide':
        raise ValueError('Seul un modèle « Validé localement » peut être imprimé en PDF.')
    from asydec.references.import_references import extraire
    r = d['resultat']
    resume = r['resume']
    sources = [a for a in extraire(d['base_xml'])['articles'] if a['fob'] is not None and float(a['fob']) != 0]
    doc = Document()
    doc.titre(f"Modèle validé n° {d['id']} · {d['importateur']}")
    doc.paragraphe(f"Proposition : {d['nom']} · créée le {date_locale(d['cree_utc'])} par {d['auteur']}")
    doc.paragraphe(f"Plaque : {d.get('plaque') or '—'}", gras=True)
    comparaisons = [date_locale(e['date_utc']) for e in d['evenements'] if e['action'] == 'comparaison']
    doc.paragraphe(f"Comparé avec un XML : {len(comparaisons)} fois, dernière le {comparaisons[-1]}"
                   if comparaisons else 'Comparé avec un XML : jamais')
    doc.paragraphe('Statut : Validé localement. ' + MENTION_MODELE, gras=True)
    if resume.get('taux') is not None:
        doc.paragraphe(f"Taux de change du XML de base : {nombre(resume['taux'], 4)} CDF")
    doc.espace()
    lignes = []
    for source, a, colis in zip(sources, resume['articles'], r['colis']):
        lignes.append(((source['position'], source.get('code') or '', source.get('designation') or '',
                        nombre(a['poids']), nombre(a['fob'], 2), colis,
                        nombre(a['fob'] / a['poids'], 4) if a['poids'] > 0 else '—',
                        nombre(a['cif']), nombre(a['taxes'])), False))
    poids, fob = resume['poids'], resume['fob']
    lignes.append((('Total', '', '', nombre(poids), nombre(fob, 2), sum(r['colis']),
                    nombre(fob / poids, 4) if poids else '—', nombre(resume['cif']),
                    nombre(resume.get('taxes_articles'))), True))
    doc.tableau([('Art.', 5, 'e'), ('Code', 9, 'w'), ('Désignation', 26, 'w'), ('Poids kg', 9, 'e'),
                 ('FOB USD', 11, 'e'), ('Colis', 6, 'e'), ('Ratio FOB/kg', 10, 'e'),
                 ('CIF CDF', 12, 'e'), ('Taxes CDF', 12, 'e')], lignes)
    doc.paragraphe(f"Taxes des articles : {nombre(resume.get('taxes_articles'))} CDF · "
                   f"taxes globales (reprises du XML de base) : {nombre(resume.get('taxes_globales'))} CDF · "
                   f"taxes totales : {nombre(resume.get('taxes_totales'))} CDF", gras=True)
    doc.espace(10)
    doc.paragraphe('Historique', 11, True)
    doc.espace(2)
    from asydec.declarations.modeles_generes import resume_evenement
    doc.tableau([('Date', 15, 'w'), ('Auteur', 12, 'w'), ('Événement', 73, 'w')],
                [((date_locale(e['date_utc']), e['auteur'], resume_evenement(e)), False) for e in d['evenements']])
    return doc.enregistrer(chemin, _pied(utilisateur, MENTION_MODELE, maintenant))


def pdf_comparaison(rapport, chemin, utilisateur, maintenant=None):
    """PDF du rapport de comparaison_prediction, tel qu'affiché dans la fenêtre."""
    doc = Document()
    doc.titre('Comparaison : XML généré / fichier fourni')
    doc.paragraphe(MENTION_COMPARAISON, gras=True)
    doc.paragraphe(f"XML généré : {rapport.get('source', '—')}\nFichier fourni : {rapport['fichier']}\n"
                   f"Devise du XML généré : {rapport['devise_prevue'] or 'absente'} · devise fournie : {rapport['devise_fournie'] or 'absente'}\n"
                   f"Taux XML généré : 1 {rapport['devise_prevue'] or '?'} = {nombre(rapport.get('taux_genere'), 4)} CDF · "
                   f"taux fichier fourni : 1 {rapport['devise_fournie'] or '?'} = {nombre(rapport.get('taux_fourni'), 4)} CDF")
    if rapport.get('plaque') or rapport.get('plaque_fournie'):
        doc.paragraphe(f"Plaque : {rapport.get('plaque') or '—'} · plaque du fichier fourni : {rapport.get('plaque_fournie') or '—'}", gras=True)
    total = next((l for l in rapport['lignes'] if l['position'] == 'Total global' and l['metrique'] == 'taxes'), None)
    if total:
        doc.espace(4)
        doc.paragraphe(f"Total déclaration estimé (XML généré) : {nombre(total['prevu'], 2)} CDF\n"
                       f"Total déclaration comparée : {nombre(total['fourni'], 2)} CDF\n"
                       f"Différence : {nombre(total['ecart'], 2)} CDF ({nombre(total['pourcentage'], 2)} %)", 11, True)
        doc.paragraphe('Taxes totales déclarées dans les deux XML.')
        from asydec.declarations.comparaison_prediction import synthese_taxes
        doc.espace(4)
        doc.paragraphe('Ce qu’il faut retenir', 11, True)
        for phrase in synthese_taxes(rapport)['phrases']:
            doc.paragraphe(f'- {phrase}')
    globales = next((l for l in rapport['lignes'] if l['metrique'] == 'taxes_globales'), None)
    if globales:
        doc.espace(4)
        doc.paragraphe(f"Taxes globales : XML généré {nombre(globales['prevu'], 2)} CDF · "
                       f"fichier fourni {nombre(globales['fourni'], 2)} CDF · "
                       f"écart {nombre(globales['ecart'], 2)} CDF ({nombre(globales['pourcentage'], 2)} %)", 11, True)
    doc.espace(4)
    doc.paragraphe('Contexte différent ou incomplet : interprétez les écarts fiscaux avec prudence.'
                   if rapport['contexte'] else 'Aucune différence détectée dans les champs de contexte comparés.')
    doc.espace()
    lignes = []
    for l in rapport['lignes']:
        decimales = {'ratio': 4, 'poids': 3, 'colis': 0}.get(l['metrique'], 2)
        lignes.append((((f"{l['position']} · {l['code']}" if l['code'] else str(l['position'])), l['libelle'], nombre(l['prevu'], decimales),
                        nombre(l['fourni'], decimales), nombre(l['ecart'], decimales),
                        nombre(l['pourcentage'], 2), l['etat']), l['position'] == 'Total global'))
    doc.tableau([('Position · Code', 13, 'w'), ('Mesure', 14, 'w'), ('XML généré', 13, 'e'),
                 ('Fichier fourni', 13, 'e'), ('Écart', 12, 'e'), ('Écart %', 8, 'e'),
                 ('Observation', 27, 'w')], lignes)
    if rapport.get('taxes_detail'):
        doc.paragraphe('Détails des taxes : estimé (XML généré) / comparé (fichier fourni)', 11, True)
        doc.espace(2)
        doc.tableau([('Art. · Code', 10, 'w'), ('Taxe', 6, 'w'), ('Base estimée', 11, 'e'), ('Base comparée', 11, 'e'),
                     ('Taux est.', 7, 'e'), ('Taux comp.', 7, 'e'), ('Estimé', 11, 'e'), ('Comparé', 11, 'e'),
                     ('Écart', 10, 'e'), ('Écart %', 6, 'e'), ('Observation', 14, 'w')],
                    [(((f"{l['position']} · {l['article']}" if l['article'] else str(l['position'])), l['taxe'],
                       nombre(l['base_estimee'], 2), nombre(l['base_comparee'], 2),
                       nombre(l['taux_estime'], 3), nombre(l['taux_compare'], 3),
                       nombre(l['estime'], 2), nombre(l['compare'], 2), nombre(l['ecart'], 2),
                       nombre(l['pourcentage'], 2), l['etat']), l['position'] in ('Total', 'Globale'))
                     for l in rapport['taxes_detail']])
    details = rapport['contexte'] + rapport['avertissements']
    if details:
        doc.paragraphe('Détails du contexte et des données', 11, True)
        for detail in details:
            doc.paragraphe(f'- {detail}')
    return doc.enregistrer(chemin, _pied(utilisateur, 'document de travail', maintenant))
