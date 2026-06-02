# -*- coding: utf-8 -*-
"""
parking_plugin.py — Classe wrapper del plugin QGIS Parking Manager.
Gestisce il ciclo di vita: registra l'azione nella toolbar (initGui)
e pulisce le risorse alla disattivazione (unload).
"""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis.core import QgsApplication


class ParcheggiPlugin:
    """Classe principale istanziata da QGIS tramite classFactory()."""

    def __init__(self, iface):
        """Salva il riferimento a iface e inizializza i puntatori a None."""
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dock_widget = None

    # ------------------------------------------------------------------
    # Ciclo di vita del plugin
    # ------------------------------------------------------------------

    def initGui(self):
        """Crea l'azione nella toolbar e aggiunge la DockWidget al pannello laterale."""
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
        self.action.setCheckable(True)
        self.action.triggered.connect(self._toggle_dock)

        self.iface.addPluginToMenu("&Parking Manager", self.action)
        self.iface.addToolBarIcon(self.action)

        # --- Crea e registra la DockWidget ---
        from .parking_dock import ParcheggiDock
        self.dock_widget = ParcheggiDock(self.iface)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)

        self.dock_widget.visibilityChanged.connect(self.action.setChecked)
        self.dock_widget.show()
        self.action.setChecked(True)

    def unload(self):
        """Rimuove azioni e widget, ripristinando lo stato dell'interfaccia."""
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
        """Mostra o nasconde la DockWidget al click sull'azione."""
        if self.dock_widget is not None:
            self.dock_widget.setVisible(checked)