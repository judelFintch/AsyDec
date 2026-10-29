"""Thème, couleurs et petits composants visuels communs à toutes les pages."""
import tkinter as tk
from tkinter import ttk

from asydec.formats import nombre  # noqa: F401 - réexporté : « from ui.theme import nombre »

try:
    import sv_ttk
except ImportError:  # thème facultatif : l'interface reste utilisable sans lui
    sv_ttk = None

POLICE = "Helvetica Neue"
FOND = "#FFFFFF"
FOND_LATERAL = "#F3F4F6"
FOND_ACTIF = "#E0E7FF"
TEXTE = "#111827"
TEXTE_DOUX = "#6B7280"
ACCENT = "#2563EB"
OK = "#15803D"
ALERTE = "#B45309"
ERREUR = "#B91C1C"
FOND_OK = "#ECFDF5"
FOND_ALERTE = "#FFFBEB"
FOND_ERREUR = "#FEF2F2"


def appliquer(fenetre):
    if sv_ttk:
        sv_ttk.set_theme("light", fenetre)
    else:
        ttk.Style(fenetre).theme_use("clam")
    style = ttk.Style(fenetre)
    style.configure("Titre.TLabel", font=(POLICE, 20, "bold"), foreground=TEXTE)
    style.configure("SousTitre.TLabel", font=(POLICE, 12), foreground=TEXTE_DOUX)
    style.configure("Section.TLabel", font=(POLICE, 13, "bold"), foreground=TEXTE)
    style.configure("Doux.TLabel", font=(POLICE, 11), foreground=TEXTE_DOUX)
    style.configure("Valeur.TLabel", font=(POLICE, 18, "bold"), foreground=TEXTE)
    style.configure("ValeurAccent.TLabel", font=(POLICE, 20, "bold"), foreground=ACCENT)
    style.configure("Entete.TLabel", font=(POLICE, 11, "bold"), foreground=TEXTE_DOUX)
    style.configure("Total.TLabel", font=(POLICE, 12, "bold"), foreground=TEXTE)
    style.configure("Ok.TLabel", font=(POLICE, 11, "bold"), foreground=OK)
    style.configure("Alerte.TLabel", font=(POLICE, 11, "bold"), foreground=ALERTE)
    style.configure("Erreur.TLabel", font=(POLICE, 11, "bold"), foreground=ERREUR)
    style.configure("Treeview", rowheight=28, font=(POLICE, 12))
    style.configure("Treeview.Heading", font=(POLICE, 11, "bold"))


def bouton(parent, texte, commande, principal=False, **options):
    style = "Accent.TButton" if principal and sv_ttk else "TButton"
    return ttk.Button(parent, text=texte, command=commande, style=style, **options)




def entete_page(parent, titre, sous_titre=""):
    ttk.Label(parent, text=titre, style="Titre.TLabel").pack(anchor="w")
    if sous_titre:
        ttk.Label(parent, text=sous_titre, style="SousTitre.TLabel", wraplength=820,
                  justify="left").pack(anchor="w", pady=(2, 14))


class Carte(ttk.Frame):
    """Indicateur : petit libellé gris, grande valeur."""

    def __init__(self, parent, libelle, detail=False, style_valeur="Valeur.TLabel"):
        super().__init__(parent, padding=(14, 10))
        self.configure(relief="solid", borderwidth=1)
        ttk.Label(self, text=libelle, style="Doux.TLabel").pack(anchor="w")
        self.valeur = tk.StringVar(value="—")
        self.etiquette = ttk.Label(self, textvariable=self.valeur, style=style_valeur)
        self.etiquette.pack(anchor="w")
        # Ligne secondaire facultative (décomposition, écart…), absente des cartes existantes.
        self.detail = tk.StringVar(value="")
        if detail:
            ttk.Label(self, textvariable=self.detail, style="Doux.TLabel", wraplength=300).pack(anchor="w")

    def definir(self, texte, detail=None):
        self.valeur.set(texte)
        if detail is not None:
            self.detail.set(detail)


class Message(tk.Frame):
    """Encadré coloré : succès, alertes ou erreur. Caché tant qu'il est vide."""

    COULEURS = {"ok": (FOND_OK, OK), "alerte": (FOND_ALERTE, ALERTE), "erreur": (FOND_ERREUR, ERREUR)}

    def __init__(self, parent):
        super().__init__(parent, padx=14, pady=10)
        self.titre = tk.Label(self, font=(POLICE, 12, "bold"), anchor="w", justify="left")
        self.titre.pack(fill="x")
        self.lignes = tk.Label(self, font=(POLICE, 12), anchor="w", justify="left", wraplength=800)
        self.lignes.pack(fill="x")

    def afficher(self, genre, titre, lignes=()):
        fond, couleur = self.COULEURS[genre]
        self.configure(bg=fond, highlightbackground=couleur, highlightthickness=1)
        self.titre.configure(text=titre, bg=fond, fg=couleur)
        self.lignes.configure(text="\n".join(lignes), bg=fond, fg=TEXTE)
        self.lignes.pack_configure(pady=(4, 0) if lignes else 0)

    def vider(self):
        for w in (self, self.titre, self.lignes):
            w.configure(bg=FOND)
        self.configure(highlightthickness=0)
        self.titre.configure(text="")
        self.lignes.configure(text="")


def tableau(parent, colonnes, hauteur=8):
    """Treeview avec barre de défilement. colonnes = [(clé, titre, largeur, alignement)]."""
    cadre = ttk.Frame(parent)
    arbre = ttk.Treeview(cadre, columns=[c[0] for c in colonnes], show="headings", height=hauteur)
    for cle, titre, largeur, align in colonnes:
        arbre.heading(cle, text=titre, anchor=align)
        arbre.column(cle, width=largeur, anchor=align, stretch=(align == "w"))
    defil = ttk.Scrollbar(cadre, orient="vertical", command=arbre.yview)
    arbre.configure(yscrollcommand=defil.set)
    arbre.pack(side="left", fill="both", expand=True)
    defil.pack(side="right", fill="y")
    arbre.tag_configure("alerte", foreground=ALERTE)
    arbre.tag_configure("total", font=(POLICE, 12, "bold"))
    return cadre, arbre
