# -*- coding: utf-8 -*-
"""
Parcheggi Plugin - Entry Point
Punto di ingresso obbligatorio per ogni plugin QGIS.
La funzione classFactory() viene chiamata da QGIS al caricamento.
"""


def classFactory(iface):
    """
    Istanzia e restituisce la classe principale del plugin.

    :param iface: QgsInterface — oggetto che fornisce l'accesso alle
                  API di QGIS (canvas, layer tree, barre degli strumenti…).
    :type iface:  QgsInterface
    :returns:     Istanza della classe ParcheggiPlugin.
    :rtype:       ParcheggiPlugin
    """
    from .parking_plugin import ParcheggiPlugin
    return ParcheggiPlugin(iface)
