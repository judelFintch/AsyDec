"""Écriture anglaise des montants et poids pour les factures commerciales."""
from decimal import Decimal, ROUND_HALF_UP

PETITS = 'ZERO ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN ELEVEN TWELVE THIRTEEN FOURTEEN FIFTEEN SIXTEEN SEVENTEEN EIGHTEEN NINETEEN'.split()
DIZAINES = 'ZERO TEN TWENTY THIRTY FORTY FIFTY SIXTY SEVENTY EIGHTY NINETY'.split()


def entier(n):
    if n < 20:
        return PETITS[n]
    if n < 100:
        return DIZAINES[n//10] + (' '+PETITS[n%10] if n%10 else '')
    if n < 1000:
        return PETITS[n//100]+' HUNDRED'+(' '+entier(n%100) if n%100 else '')
    for limite, nom in ((10**12,'TRILLION'),(10**9,'BILLION'),(10**6,'MILLION'),(1000,'THOUSAND')):
        if n >= limite:
            return entier(n//limite)+' '+nom+(' '+entier(n%limite) if n%limite else '')
    raise ValueError('Nombre hors limites.')


def nombre(valeur, monnaie=False):
    d=Decimal(str(valeur)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    if not d.is_finite() or d < 0 or d >= 10**15:
        raise ValueError('Valeur non prise en charge pour le montant en lettres.')
    unites=int(d)
    cents=int((d-unites)*100)
    if monnaie:
        return entier(unites)+(' AND '+entier(cents)+' CENTS' if cents else '')
    return entier(unites)+(' POINT '+PETITS[cents//10]+' '+PETITS[cents%10] if cents else '')
