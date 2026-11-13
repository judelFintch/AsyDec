"""Parcours de connexion sans dépendance à un écran graphique."""
from contextlib import ExitStack
from unittest import TestCase
from unittest.mock import patch

from asydec.ui import connexion as C


class Variable:
    def __init__(self, value=''):
        self.valeur = value

    def get(self):
        return self.valeur

    def set(self, valeur):
        self.valeur = valeur


class Widget:
    def __init__(self, *args, **kwargs):
        self.options = kwargs
        self.resultat = None

    def pack(self, **kwargs):
        pass

    def configure(self, **kwargs):
        self.options.update(kwargs)

    def __getattr__(self, nom):
        return lambda *args, **kwargs: None


class ConnexionTest(TestCase):
    def parcours(self, action, existe=True, illisible=False):
        widgets = []
        entrees = []
        fenetre = Widget()

        def widget(*args, **kwargs):
            w = Widget(*args, **kwargs)
            widgets.append(w)
            return w

        def entree(*args, **kwargs):
            w = widget(*args, **kwargs)
            entrees.append(kwargs['textvariable'])
            return w

        def bouton(parent, texte, commande, **kwargs):
            return widget(text=texte, command=commande)

        def cliquer(texte):
            next(w for w in widgets if w.options.get('text') == texte).options['command']()

        fenetre.mainloop = lambda: action(cliquer, entrees)
        with ExitStack() as pile:
            pile.enter_context(patch.object(C.tk, 'Tk', return_value=fenetre))
            pile.enter_context(patch.object(C.tk, 'StringVar', Variable))
            for nom in ('Frame', 'Label'):
                pile.enter_context(patch.object(C.ttk, nom, side_effect=widget))
            pile.enter_context(patch.object(C.ttk, 'Entry', side_effect=entree))
            pile.enter_context(patch.object(C.theme, 'appliquer'))
            pile.enter_context(patch.object(C.theme, 'bouton', side_effect=bouton))
            pile.enter_context(patch.object(C.local, 'compte_existe', return_value=existe))
            pile.enter_context(patch.object(C.local, 'identifiant_compte',
                side_effect=C.local.CompteIllisible('Compte illisible') if illisible else None,
                return_value='AncienCompte'))
            return C.demander_connexion()

    def test_login_permet_de_recreer_compte_illisible_apres_confirmation(self):
        def action(cliquer, entrees):
            cliquer('Créer un compte')
            for variable, valeur in zip(entrees, ('NouveauCompte', 'motdepasse', 'motdepasse')):
                variable.set(valeur)
            cliquer('Créer mon compte et continuer')
        with patch.object(C.local, 'recreer_compte_illisible', return_value=('NouveauCompte', '/copie.json')) as recreer, \
             patch.object(C.messagebox, 'askyesno', return_value=True), \
             patch.object(C.messagebox, 'showinfo'):
            self.assertEqual(self.parcours(action, illisible=True), 'NouveauCompte')
        recreer.assert_called_once_with('NouveauCompte', 'motdepasse')

    def test_annuler_confirmation_ne_change_pas_le_compte(self):
        def action(cliquer, entrees):
            cliquer('Créer un compte')
            entrees[1].set('motdepasse')
            entrees[2].set('motdepasse')
            cliquer('Créer mon compte et continuer')
        with patch.object(C.local, 'recreer_compte_illisible') as recreer, \
             patch.object(C.messagebox, 'askyesno', return_value=False):
            self.assertIsNone(self.parcours(action, illisible=True))
        recreer.assert_not_called()

    def test_bouton_creation_ne_remplace_pas_un_compte_lisible(self):
        with patch.object(C.local, 'recreer_compte_illisible') as recreer, \
             patch.object(C.local, 'creer_compte') as creer:
            self.assertIsNone(self.parcours(lambda cliquer, entrees: cliquer('Créer un compte')))
        recreer.assert_not_called()
        creer.assert_not_called()
