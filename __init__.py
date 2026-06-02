# -*- coding: utf-8 -*-
"""
__init__.py — Punto di ingresso del plugin QGIS Parking Manager.
Espone classFactory(), unica funzione richiesta da QGIS per caricare il plugin.
"""


def classFactory(iface):
    """Istanzia e restituisce la classe principale del plugin."""
    from .parking_plugin import ParcheggiPlugin
    return ParcheggiPlugin(iface)
