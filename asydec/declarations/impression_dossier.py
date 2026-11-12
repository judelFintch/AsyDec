"""Choix et assemblage des documents d'un dossier à imprimer en une fois.

Factures, packing lists, CVI + BL et déclarations sont repris des fichiers Word déjà générés ;
chacun est converti en PDF par Word (réutilisé s'il est à jour), puis tout est réuni dans un seul PDF.
"""
from pathlib import Path

GROUPES = (
    ('fiche', 'Fiche du dossier (détails et répartitions)'),
    ('factures', 'Factures des parts'),
    ('packing', 'Packing lists des parts'),
    ('facture_globale', 'Facture globale'),
    ('packing_globale', 'Packing list globale'),
    ('cvi', 'CVI + BL'),
    ('declarations', 'Déclarations'),
)
# Cochés par défaut à l'ouverture de la fenêtre (s'ils existent) : pas la fiche, ni les factures des parts,
# ni la packing list globale.
PAR_DEFAUT = frozenset({'packing', 'facture_globale', 'cvi', 'declarations'})


def _existe(chemin):
    return bool(chemin) and Path(chemin).is_file()


def documents(licence):
    """{groupe: [(part ou None, libellé, chemin .docx)]} des fichiers générés encore présents."""
    resultat = {cle: [] for cle, _ in GROUPES}
    factures = licence.get('factures_parts') or {}
    for part in factures.get('parts') or []:
        fichiers = part.get('fichiers') or {}
        if _existe(fichiers.get('facture')):
            resultat['factures'].append((part.get('part'), f"Facture part {part.get('part')}", fichiers['facture']))
        if _existe(fichiers.get('packing list')):
            resultat['packing'].append((part.get('part'), f"Packing list part {part.get('part')}", fichiers['packing list']))
    globale = (factures.get('globale') or {}).get('fichiers') or {}
    for cle, groupe, libelle in (('facture', 'facture_globale', 'Facture globale'),
                                 ('packing list', 'packing_globale', 'Packing list globale')):
        if _existe(globale.get(cle)):
            resultat[groupe].append((None, libelle, globale[cle]))
    for chemin in (licence.get('cvi_parts') or {}).get('fichiers') or []:
        if _existe(chemin):
            resultat['cvi'].append((None, 'CVI + BL', chemin))
    declarations = sorted((licence.get('declarations') or {}).get('fichiers') or [],
                          key=lambda d: (int(d.get('part') or 0)))
    for d in declarations:
        if _existe(d.get('fichier')):
            resultat['declarations'].append((d.get('part'), f"Déclaration part {d.get('part')}", d['fichier']))
    return resultat


def ordonner(docs, choisis, par_part=False):
    """Liste ordonnée [(libellé, chemin ou 'fiche')]. Par part : facture, packing list puis déclaration
    de la part 1, puis de la part 2… ; les documents communs (fiche, globale, CVI) en tête."""
    if 'fiche' in choisis:
        sortie = [('Fiche du dossier', 'fiche')]
    else:
        sortie = []
    if not par_part:
        for cle, _ in GROUPES[1:]:
            if cle in choisis:
                sortie += [(libelle, chemin) for _, libelle, chemin in docs.get(cle, [])]
        return sortie
    for cle in ('facture_globale', 'packing_globale', 'cvi'):
        if cle in choisis:
            sortie += [(libelle, chemin) for _, libelle, chemin in docs.get(cle, [])]
    parts = sorted({p for cle in ('factures', 'packing', 'declarations') for p, _, _ in docs.get(cle, []) if p is not None},
                   key=lambda p: int(p))
    for part in parts:
        for cle in ('factures', 'packing', 'declarations'):
            if cle in choisis:
                sortie += [(libelle, chemin) for p, libelle, chemin in docs.get(cle, []) if p == part]
    return sortie


def assembler(licence, elements, destination, progression=None):
    """Convertit les Word en PDF et réunit tout dans « destination » ; renvoie (chemin, nombre de pages)."""
    import pymupdf
    from asydec.systeme import conversion_pdf
    from asydec.declarations import fiche_dossier
    words = [chemin for _, chemin in elements if chemin != 'fiche']
    pdfs = dict(zip(words, conversion_pdf.docx_vers_pdf_lot(words, progression))) if words else {}
    resultat = pymupdf.open()
    for libelle, chemin in elements:
        source = (pymupdf.open('pdf', fiche_dossier.pdf(licence)) if chemin == 'fiche'
                  else pymupdf.open(str(pdfs[chemin])))
        debut = resultat.page_count
        resultat.insert_pdf(source)
        resultat.set_toc(resultat.get_toc() + [[1, libelle, debut + 1]])
        source.close()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pages = resultat.page_count
    resultat.save(str(destination), garbage=3, deflate=True)
    resultat.close()
    return destination, pages
