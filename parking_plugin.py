# -*- coding: utf-8 -*-
"""
parking_plugin.py
-----------------
Classe principale del plugin Parcheggi per QGIS.

Gestisce il ciclo di vita del plugin:
  - initGui()   → registra azioni e crea la DockWidget
  - unload()    → rimuove azioni e pulisce le risorse
"""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis.core import QgsApplication


class ParcheggiPlugin:
    """
    Classe wrapper che QGIS istanzia attraverso classFactory().

    Non contiene logica di business: delega tutto alla DockWidget
    (parking_dock.py), che implementa la GUI e l'analisi dati.
    """

    def __init__(self, iface):
        """
        Costruttore.

        :param iface: Riferimento all'oggetto QgsInterface di QGIS,
                      che consente di interagire con il canvas, i layer,
                      i menu e le toolbar.
        :type iface:  QgsInterface
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        # Azione nella toolbar / menu — inizializzata in initGui()
        self.action = None

        # Widget della finestra ancorata — inizializzato in initGui()
        self.dock_widget = None

    # ------------------------------------------------------------------
    # Ciclo di vita del plugin
    # ------------------------------------------------------------------

    def initGui(self):
        """
        Chiamata da QGIS quando il plugin viene attivato.

        Crea l'azione nella toolbar e registra la DockWidget nel
        pannello laterale di QGIS.
        """
        # --- Icona: usa quella QGIS di default se non trovata ---
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        if not os.path.exists(icon_path):
            icon = QgsApplication.getThemeIcon("/mActionAddOgrLayer.svg")
        else:
            icon = QIcon(icon_path)

        # --- Azione nella toolbar Plugins ---
        self.action = QAction(
            icon,
            "Parking Manager",
            self.iface.mainWindow()
        )
        self.action.setObjectName("parcheggiAction")
        self.action.setStatusTip(
            "Apre il pannello di analisi avanzata dei parcheggi GeoJSON"
        )
        self.action.setCheckable(True)   # permette lo stato attivo/inattivo
        self.action.triggered.connect(self._toggle_dock)

        # Aggiunge l'azione al menu Plugins e alla toolbar Plugins
        self.iface.addPluginToMenu("&Parking Manager", self.action)
        self.iface.addToolBarIcon(self.action)

        # --- Crea e registra la DockWidget ---
        from .parking_dock import ParcheggiDock
        self.dock_widget = ParcheggiDock(self.iface)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)

        # Sincronizza il toggle dell'azione con la visibilità del dock
        self.dock_widget.visibilityChanged.connect(self.action.setChecked)

        # Mostra il pannello all'avvio
        self.dock_widget.show()
        self.action.setChecked(True)

    def unload(self):
        """
        Chiamata da QGIS quando il plugin viene disattivato / rimosso.

        Deve rimuovere tutte le azioni e ripristinare lo stato
        dell'interfaccia come era prima del caricamento.
        """
        # Ripristina il map tool di default prima di uscire
        if self.dock_widget is not None:
            self.dock_widget.cleanup()
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.deleteLater()
            self.dock_widget = None

        if self.action is not None:
            self.iface.removePluginMenu("&Parking Manager", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

    # ------------------------------------------------------------------
    # Slot privati
    # ------------------------------------------------------------------

    def _toggle_dock(self, checked: bool):
        """Mostra o nasconde la DockWidget in risposta al click sull'azione."""
        if self.dock_widget is not None:
            self.dock_widget.setVisible(checked)
