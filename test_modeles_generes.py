"""Cycle de validation interne et snapshots sur des données exclusivement temporaires."""
import copy
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET
import modeles_generes as M
import moteur
import gestion_locale as L
import ui.etapes as E
from test_references import declaration, item


class ModelesGeneresTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.racine=Path(self.temp.name)
        self.base=self.racine/'DONNEES/modeles_generes.db'
        self.source=self.racine/'source.xml'
        self.source.write_bytes(declaration([item(),'<Item/>',item(code='6304',poids='50',fob='25',colis='11')],
                                           poids='150',fob='175',colis='21',totales='250'))
        arbre=ET.parse(self.source)
        def assurer(parent,chemin):
            for nom in chemin.split('/'):
                enfant=parent.find(nom)
                parent=enfant if enfant is not None else ET.SubElement(parent,nom)
        for article in moteur.articles(arbre.getroot()):
            for chemin in ('Tarification/Value_item','Valuation_item/Weight_itm/Net_weight_itm',
                'Valuation_item/Total_cost_itm','Valuation_item/Total_CIF_itm','Valuation_item/Statistical_value',
                'Valuation_item/Alpha_coeficient_of_apportionment','Valuation_item/Item_Invoice/Amount_national_currency',
                'Valuation_item/Item_Invoice/Amount_foreign_currency','Valuation_item/item_external_freight/Amount_national_currency',
                'Valuation_item/item_external_freight/Amount_foreign_currency','Valuation_item/item_insurance/Amount_national_currency',
                'Valuation_item/item_insurance/Amount_foreign_currency'):
                assurer(article,chemin)
        for chemin in ('Valuation/Gs_Invoice/Amount_national_currency','Valuation/Gs_Invoice/Amount_foreign_currency',
            'Valuation/Gs_external_freight/Amount_national_currency','Valuation/Gs_external_freight/Amount_foreign_currency',
            'Valuation/Gs_insurance/Amount_national_currency','Valuation/Gs_insurance/Amount_foreign_currency',
            'Valuation/Total_cost','General_information/Value_details'):
            assurer(arbre.getroot(),chemin)
        arbre.write(self.source)
        resume=moteur.recalculer(arbre,[(140,90),(35,60)],[10,11])
        self.resultat={'nom':'proposition.xml','chemin':str(self.racine/'export.xml'),'resume':resume,
            'colis':[10,11],'fob':[140,35],'info':moteur.infos_dossier(arbre.getroot()),'alertes':[],'mode':'SAISI'}
        self.xml=ET.tostring(arbre.getroot())

    def enregistrer(self,export=None):
        return M.enregistrer(self.resultat,self.source,'alice',export=export,base=self.base)

    def test_sauvegarde_reouverture_et_deduplication(self):
        original=self.source.read_bytes()
        identifiant=self.enregistrer()
        self.assertEqual(self.enregistrer(),identifiant)
        liste=M.lister('en_attente',base=self.base)
        self.assertEqual(len(liste),1)
        self.assertEqual(liste[0]['id'],identifiant)
        self.assertEqual(liste[0]['statut'],'en_attente')
        self.assertTrue(liste[0]['cree_utc'].endswith('+00:00'))
        d=M.detail(identifiant,base=self.base)
        self.assertEqual(d['base_xml'],original)
        self.assertEqual(d['resultat'],self.resultat)
        self.assertEqual(len(d['evenements']),1)
        self.assertEqual(self.source.read_bytes(),original)

    def test_snapshots_survivent_a_source_et_export_supprimes(self):
        self.source_export=self.racine/'export.xml'
        self.source_export.write_bytes(self.xml)
        identifiant=self.enregistrer(self.source_export)
        self.source.unlink()
        self.source_export.unlink()
        d=M.detail(identifiant,base=self.base)
        self.assertEqual(d['resultat']['resume']['fob'],175)
        r=ET.fromstring(d['modele_xml'])
        self.assertEqual(r.find('Item/Valuation_item/Weight_itm/Gross_weight_itm').text,'90')
        self.assertEqual(len(d['evenements']),2)
        self.assertEqual(d['evenements'][1]['action'],'export')

    def test_valider_rejeter_et_remettre_attente_avec_historique(self):
        identifiant=self.enregistrer()
        M.changer_statut(identifiant,'valide','bob',base=self.base)
        M.changer_statut(identifiant,'valide','bob',base=self.base)
        with self.assertRaises(ValueError):
            M.changer_statut(identifiant,'rejete','bob',base=self.base)
        M.changer_statut(identifiant,'rejete','bob','Erreur de colis',base=self.base)
        M.changer_statut(identifiant,'en_attente','alice','À revoir',base=self.base)
        d=M.detail(identifiant,base=self.base)
        self.assertEqual([e['statut'] for e in d['evenements']],['en_attente','valide','rejete','en_attente'])
        self.assertEqual(d['evenements'][1]['auteur'],'bob')
        self.assertEqual(d['evenements'][2]['detail'],'Erreur de colis')

    def test_export_relie_ne_duplique_pas_et_ne_reinitialise_pas_validation(self):
        identifiant=self.enregistrer()
        M.changer_statut(identifiant,'valide','bob',base=self.base)
        export=self.racine/'export.xml'
        export.write_bytes(self.xml)
        self.assertEqual(self.enregistrer(export),identifiant)
        self.assertEqual(self.enregistrer(export),identifiant)
        self.assertEqual(len(M.lister(base=self.base)),1)
        d=M.detail(identifiant,base=self.base)
        self.assertEqual(d['statut'],'valide')
        self.assertEqual(len(d['evenements']),3)
        self.assertIn('sha256',d['evenements'][-1]['detail'])

    def test_nouvelle_repartition_nouveau_modele(self):
        premier=self.enregistrer()
        arbre=ET.parse(self.source)
        self.resultat['resume']=moteur.recalculer(arbre,[(145,95),(30,55)],[10,11])
        self.assertNotEqual(self.enregistrer(),premier)
        self.assertEqual(len(M.lister(base=self.base)),2)

    def test_apercu_modifie_incoherent_refuse(self):
        self.resultat['resume']['taxes_totales']+=1
        with self.assertRaises(ValueError):
            self.enregistrer()
        self.assertFalse(self.base.exists())

    def test_aucun_auteur_ni_statut_inconnu(self):
        with self.assertRaises(ValueError):
            M.enregistrer(self.resultat,self.source,' ',base=self.base)
        identifiant=self.enregistrer()
        with self.assertRaises(ValueError):
            M.changer_statut(identifiant,'accepte','alice',base=self.base)

    def test_snapshots_et_evenements_immuables(self):
        self.enregistrer()
        with sqlite3.connect(self.base) as conn:
            for requete in ("UPDATE modeles SET nom='autre'",'DELETE FROM modeles',
                            "UPDATE evenements SET auteur='autre'",'DELETE FROM evenements'):
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(requete)

    def test_reset_archive_base_et_preserve_source_et_export(self):
        self.enregistrer()
        export=self.racine/'CLIENT/1 - HISTORIQUE/export.xml'
        export.parent.mkdir(parents=True)
        export.write_bytes(self.xml)
        L.creer_compte('alice','motdepasse8',self.racine/'CONFIG_LOCAL')
        self.assertIn('DONNEES/modeles_generes.db',L.apercu_reset(self.racine))
        sauvegarde=L.reinitialiser('motdepasse8','REINITIALISER',self.racine)
        self.assertFalse(self.base.exists())
        self.assertTrue((sauvegarde/'DONNEES/modeles_generes.db').exists())
        self.assertTrue(self.source.exists())
        self.assertEqual(export.read_bytes(),self.xml)

    def test_proposition_sans_export_non_comparable(self):
        identifiant=self.enregistrer()
        with self.assertRaisesRegex(ValueError,'pas encore été exportée'):
            M.lire_export(identifiant,base=self.base)
        self.assertFalse(M.lister(base=self.base)[0]['exporte'])

    def test_export_exact_archive_meme_si_fichier_deplace(self):
        export=self.racine/'export.xml'
        contenu=self.xml+b'\n<!-- export exact -->'
        export.write_bytes(contenu)
        identifiant=self.enregistrer(export)
        export.unlink()
        self.assertEqual(M.lire_export(identifiant,base=self.base),contenu)
        self.assertTrue(M.lister(base=self.base)[0]['exporte'])
        with sqlite3.connect(self.base) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE exports_xml SET sha256='faux'")

    def test_ancien_evenement_export_fallback_empreinte_obligatoire(self):
        import hashlib,json
        identifiant=self.enregistrer()
        export=self.racine/'ancien.xml'
        export.write_bytes(self.xml)
        with sqlite3.connect(self.base) as conn:
            conn.execute("INSERT INTO evenements(modele_id,date_utc,auteur,action,statut,detail) VALUES(?,?,?,?,?,?)",
                (identifiant,M._maintenant(),'alice','export',None,json.dumps({'chemin':str(export),
                    'sha256':hashlib.sha256(self.xml).hexdigest()})))
        self.assertEqual(M.lire_export(identifiant,base=self.base),self.xml)
        export.write_bytes(self.xml+b'<!-- modifie -->')
        with self.assertRaisesRegex(ValueError,'modifié'):
            M.lire_export(identifiant,base=self.base)
        export.unlink()
        with self.assertRaisesRegex(ValueError,'introuvable'):
            M.lire_export(identifiant,base=self.base)


class ActionsModelesGeneresTest(unittest.TestCase):
    def page(self):
        return SimpleNamespace(resultat={'apercu':True},fichier=None,
            app=SimpleNamespace(base='base.xml',utilisateur='alice',session_verrouillee=False,
                pages={'modeles_generes':SimpleNamespace(filtre=Mock())},montrer=Mock(),calculer=Mock(return_value={'chemin':'export.xml'})),
            message=Mock(),generer=Mock(),finder=Mock(),comparer_bouton=Mock())

    def test_sauvegarde_explicite_et_navigation(self):
        page=self.page()
        with patch.object(M,'enregistrer',return_value=7) as sauver,patch.object(E.messagebox,'showinfo'):
            E.PageVerifier.conserver_proposition(page)
        sauver.assert_called_once_with(page.resultat,'base.xml','alice')
        page.app.montrer.assert_called_once_with('modeles_generes')

    def test_actions_verrouillees(self):
        page=self.page()
        page.app.session_verrouillee=True
        with patch.object(M,'enregistrer') as sauver,patch.object(E.messagebox,'askyesno') as confirmer:
            E.PageVerifier.conserver_proposition(page)
            E.PageVerifier.enregistrer(page)
        sauver.assert_not_called()
        confirmer.assert_not_called()

    def test_export_reussi_si_archivage_echoue_pas_de_faux_message_echec(self):
        page=self.page()
        page.resultat={'nom':'export.xml','alertes':[]}
        with patch.object(E.messagebox,'askyesno',return_value=True), \
             patch.object(M,'enregistrer',side_effect=OSError('base occupée')), \
             patch.object(E.messagebox,'showwarning') as avertir,patch.object(E.messagebox,'showerror') as erreur:
            E.PageVerifier.enregistrer(page)
        self.assertEqual(page.fichier,'export.xml')
        erreur.assert_not_called()
        self.assertIn('XML créé',avertir.call_args.args[0])
        page.generer.configure.assert_called_once_with(state='disabled',text='Généré  ✓')


if __name__=='__main__':
    unittest.main()
