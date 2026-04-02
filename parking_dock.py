# -*- coding: utf-8 -*-
"""
parking_dock.py
---------------
Finestra del plugin, contiene:
  - Caricamento file GeoJSON e creazione dei layer
  - Legenda 
  - Strumenti per l'aggiunta e la rimozione di parcheggi
  - Funzione per la selezione rettangolare interattiva sulla mappa
  - Grafico per l'analisi e la visualizzazione dei risultati
"""

import os
from typing import Optional

from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QColor, QFont, QIcon
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QGroupBox,
    QFrame,
    QSizePolicy,
    QProgressBar,
    QMessageBox,
    QScrollArea,
)

from qgis.gui import QgsDockWidget
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsRectangle,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsVectorFileWriter, 
)

from .map_tool_extent import RectangleMapTool
from .layer_loader import load_geojson_to_layers
from .add_remove_tools import AddParkingMapTool, RemoveParkingMapTool


# ---------------------------------------------------------------------------
# Stile CSS per il pannello principale 
# ---------------------------------------------------------------------------
_DOCK_STYLE = """
/* Sfondo bianco forzato su tutto il pannello sennò con il tema scuro di QGIS non si vede bene */
QWidget {
    background-color: #f5f5f5;
    color: #1a1a1a;
}
QScrollArea {
    background-color: #f5f5f5;
    border: none;
}

/* GroupBox: sfondo bianco, bordo grigio, titolo blu scuro leggibile */
QGroupBox {
    font-weight: bold;
    font-size: 11px;
    border: 1.5px solid #c0c0c0;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 6px;
    background-color: #ffffff;
    color: #1a1a1a;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
    background-color: #ffffff;
    color: #1a5276;
    font-size: 11px;
    font-weight: bold;
}

/* Label generiche — testo scuro esplicito */
QLabel {
    color: #1a1a1a;
    background-color: transparent;
    font-size: 11px;
}

/* Bottoni base */
QPushButton {
    border: 1px solid #aaa;
    border-radius: 6px;
    padding: 6px 12px;
    background-color: #e8e8e8;
    color: #1a1a1a;
    font-size: 11px;
    min-height: 23px;
}
QPushButton:hover   { background-color: #d0e4f5; border-color: #3498db; color: #1a1a1a; }
QPushButton:pressed { background-color: #b8d4ea; color: #1a1a1a; }
QPushButton:disabled { color: #888; background-color: #e0e0e0; border-color: #ccc; }

/* Bottone Carica Layer — blu */
QPushButton#btn_load {
    background-color: #2980b9;
    color: #ffffff;
    border-color: #1f6692;
    font-weight: bold;
}
QPushButton#btn_load:hover   { background-color: #1f6692; color: #ffffff; }
QPushButton#btn_load:disabled { background-color: #7fb3d3; color: #ddd; }

/* Bottone Seleziona Area — verde */
QPushButton#btn_select {
    background-color: #27ae60;
    color: #ffffff;
    border-color: #1e8449;
    font-weight: bold;
}
QPushButton#btn_select:hover { background-color: #1e8449; color: #ffffff; }

/* Bottone Reset — rosso */
QPushButton#btn_clear {
    background-color: #c0392b;
    color: #ffffff;
    border-color: #96281b;
    font-weight: bold;
}
QPushButton#btn_clear:hover { background-color: #96281b; color: #ffffff; }

/* Campo percorso file */
QLabel#lbl_path {
    color: #333333;
    font-size: 10px;
    padding: 4px 6px;
    border: 1px solid #c0c0c0;
    border-radius: 3px;
    background-color: #ffffff;
}

/* Label stato strumento */
QLabel#lbl_status {
    color: #2c3e50;
    font-size: 10px;
    padding: 2px 4px;
    background-color: transparent;
}
"""

_RESULT_CARD_STYLE = """
QFrame#result_card {
    background-color: #eaf4fb;
    border: 1px solid #aed6f1;
    border-radius: 6px;
    padding: 4px;
}
"""


class _ResultCard(QFrame):
    """
    Widget a scheda per mostrare un singolo risultato numerico.

    Layout verticale:
      [icona/titolo]
      [valore grande]
      [sottotitolo]
    """

    def __init__(self, title: str, icon_char: str, parent=None):
        super().__init__(parent)
        self.setObjectName("result_card")
        self.setStyleSheet(_RESULT_CARD_STYLE)
        self.setMinimumWidth(110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        # Titolo
        lbl_title = QLabel(f"{icon_char}  {title}")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet(
            "font-size: 10px; color: #1a5276; font-weight: bold; "
            "background-color: transparent;"
        )
        layout.addWidget(lbl_title)

        # Valore numerico principale
        self.lbl_value = QLabel("—")
        self.lbl_value.setAlignment(Qt.AlignCenter)
        self.lbl_value.setStyleSheet(
            "font-size: 26px; font-weight: bold; color: #1a5276; "
            "background-color: transparent;"
        )
        layout.addWidget(self.lbl_value)

    def set_value(self, value):
        self.lbl_value.setText(str(value))

    def reset(self):
        self.lbl_value.setText("—")


class ParcheggiDock(QgsDockWidget):
    """
    Pannello principale del plugin
    """

    def __init__(self, iface):
        super().__init__("QGIS Parking Manager", iface.mainWindow())
        self.iface  = iface
        self.canvas = iface.mapCanvas()

        # Layer attivi
        self._layer_poly: Optional[QgsVectorLayer] = None
        self._layer_pts: Optional[QgsVectorLayer] = None

        # Map tool per la selezione rettangolare
        self._map_tool: Optional[RectangleMapTool] = None
        # Map tool precedente (ripristinato dopo la selezione o la modifica)
        self._prev_map_tool = None
        
        # Map tool per aggiunta/rimozione parcheggi
        self._add_tool:    Optional[AddParkingMapTool] = None
        self._remove_tool: Optional[RemoveParkingMapTool] = None

        # Imposta il contenuto del dock
        self._build_ui()
        self.setMinimumWidth(280)
        self.setMaximumWidth(420)

    # ======================================================================
    # Costruzione interfaccia grafica
    # ======================================================================

    def _build_ui(self):
        # Widget radice + scroll area
        root_widget = QWidget()
        root_widget.setStyleSheet(_DOCK_STYLE)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(root_widget)
        scroll.setFrameShape(QFrame.NoFrame)
        self.setWidget(scroll)

        main_layout = QVBoxLayout(root_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        # ---------- [Caricamento File GeoJSON] ----------
        grp_load = QGroupBox("Caricamento File GeoJSON")
        vb_load = QVBoxLayout(grp_load)

        # Etichetta percorso file
        self.lbl_path = QLabel("Nessun file selezionato")
        self.lbl_path.setObjectName("lbl_path")
        self.lbl_path.setWordWrap(True)
        vb_load.addWidget(self.lbl_path)

        # Bottoni Sfoglia e Carica
        hb_btns = QHBoxLayout()
        self.btn_browse = QPushButton("📁  Sfoglia…")
        self.btn_browse.setToolTip("Seleziona un file .geojson dal disco")
        self.btn_browse.clicked.connect(self._on_browse)

        self.btn_load = QPushButton("⬆  Carica Layer")
        self.btn_load.setObjectName("btn_load")
        self.btn_load.setEnabled(False)
        self.btn_load.setToolTip(
            "Carica il GeoJSON e crea i layer in memoria"
        )
        self.btn_load.clicked.connect(self._on_load)

        hb_btns.addWidget(self.btn_browse)
        hb_btns.addWidget(self.btn_load)
        vb_load.addLayout(hb_btns)

        # Progress bar (visibile solo durante il caricamento)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        vb_load.addWidget(self.progress)

        main_layout.addWidget(grp_load)

        # ---------- Informazioni Parcheggi Caricati ----------
        grp_info = QGroupBox("Informazioni sui Parcheggi Caricati")
        vb_info  = QVBoxLayout(grp_info)

        self.lbl_poly_count = QLabel("Parcheggi Poligonali caricati: —")
        self.lbl_pts_count  = QLabel("Punti di Parcheggio caricati: —")
        self.lbl_fee_yes    = QLabel("Parcheggi a pagamento: —")
        self.lbl_fee_no     = QLabel("Parcheggi gratuiti: —")
        self.lbl_fee_cond   = QLabel("Parcheggi con condizioni: —")

        for lbl in (
            self.lbl_poly_count,
            self.lbl_pts_count,
            self.lbl_fee_yes,
            self.lbl_fee_no,
            self.lbl_fee_cond,
        ):
            lbl.setStyleSheet(
                "font-size: 11px; padding: 2px 4px; "
                "color: #1a1a1a; background-color: transparent;"
            )
            vb_info.addWidget(lbl)

        main_layout.addWidget(grp_info)
        
        # ---------- Scheda per la Modifica dei Parcheggi ----------
        grp_edit = QGroupBox("Modifica Parcheggi")
        vb_edit = QVBoxLayout(grp_edit)

        lbl_edit_hint = QLabel(
            "Clicca sui bottoni per aggiungere o rimuovere un parcheggio"
        )
        lbl_edit_hint.setStyleSheet(
            "font-size: 10px; color: #444444; padding: 2px; "
            "background-color: transparent;"
        )
        lbl_edit_hint.setWordWrap(True)
        vb_edit.addWidget(lbl_edit_hint)

        hb_edit = QHBoxLayout()

        self.btn_add = QPushButton("Aggiungi")
        self.btn_add.setObjectName("btn_add")
        self.btn_add.setEnabled(False)
        self.btn_add.setToolTip(
            "Clicca sulla mappa per aggiungere un nuovo punto di parcheggio"
        )
        self.btn_add.setStyleSheet(
            "QPushButton { background-color: #1a5276; color: white; "
            "border-color: #154360; font-weight: bold; "
            "border-radius: 6px; padding: 6px 12px; min-height: 23px; }"
            "QPushButton:hover { background-color: #154360; color: white; }"
            "QPushButton:disabled { background-color: #aab7c4; color: #eee; border-color: #ccc; }"
        )
        self.btn_add.clicked.connect(self._on_activate_add)

        self.btn_remove = QPushButton("Rimuovi")
        self.btn_remove.setObjectName("btn_remove")
        self.btn_remove.setEnabled(False)
        self.btn_remove.setToolTip(
            "Clicca su un parcheggio esistente per rimuoverlo"
        )
        self.btn_remove.setStyleSheet(
            "QPushButton { background-color: #784212; color: white; "
            "border-color: #6e2c0e; font-weight: bold; "
            "border-radius: 6px; padding: 6px 12px; min-height: 23px; }"
            "QPushButton:hover { background-color: #6e2c0e; color: white; }"
            "QPushButton:disabled { background-color: #c4a882; color: #eee; border-color: #ccc; }"
        )
        self.btn_remove.clicked.connect(self._on_activate_remove)

        hb_edit.addWidget(self.btn_add)
        hb_edit.addWidget(self.btn_remove)
        vb_edit.addLayout(hb_edit)

        # Stato strumento modifica
        self.lbl_edit_status = QLabel("")
        self.lbl_edit_status.setObjectName("lbl_status")
        self.lbl_edit_status.setAlignment(Qt.AlignCenter)
        self.lbl_edit_status.setWordWrap(True)
        vb_edit.addWidget(self.lbl_edit_status)

        main_layout.addWidget(grp_edit)

        # ---------- Tool per la Selezione Spaziale ----------
        grp_sel = QGroupBox("Selezione Spaziale")
        vb_sel = QVBoxLayout(grp_sel)

        lbl_hint = QLabel(
            "Clicca il bottone, poi disegna un rettangolo sulla mappa tenendo premuto."
        )
        lbl_hint.setStyleSheet(
            "font-size: 10px; color: #444444; padding: 2px; "
            "background-color: transparent;"
        )
        lbl_hint.setWordWrap(True)
        vb_sel.addWidget(lbl_hint)

        hb_sel = QHBoxLayout()
        self.btn_select = QPushButton("🔍  Seleziona Area")
        self.btn_select.setObjectName("btn_select")
        self.btn_select.setEnabled(False)
        self.btn_select.setToolTip(
            "Attiva lo strumento di selezione rettangolare sulla mappa"
        )
        self.btn_select.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; "
            "border-color: #1e8449; font-weight: bold; "
            "border-radius: 6px; padding: 6px 12px; min-height: 23px; }"
            "QPushButton:hover { background-color: #1e8449; color: white; }"
            "QPushButton:disabled { background-color: #aab7c4; color: #eee; border-color: #ccc; }"
        )
        self.btn_select.clicked.connect(self._on_activate_selection)

        self.btn_clear = QPushButton("✖  Reset")
        self.btn_clear.setObjectName("btn_clear")
        self.btn_clear.setEnabled(False)
        self.btn_clear.setToolTip("Cancella la selezione e i risultati")
        self.btn_clear.clicked.connect(self._on_reset_selection)

        hb_sel.addWidget(self.btn_select)
        hb_sel.addWidget(self.btn_clear)
        vb_sel.addLayout(hb_sel)

        # Stato strumento
        self.lbl_tool_status = QLabel("")
        self.lbl_tool_status.setObjectName("lbl_status")
        self.lbl_tool_status.setAlignment(Qt.AlignCenter)
        vb_sel.addWidget(self.lbl_tool_status)

        main_layout.addWidget(grp_sel)


        # ---------- [5] Risultati ----------
        grp_results = QGroupBox("📊  Risultati Analisi")
        vb_results = QVBoxLayout(grp_results)

        cards_layout = QHBoxLayout()

        self.card_count = _ResultCard("Parcheggi", "🅿")
        self.card_capacity = _ResultCard("Posti auto", "🚗")

        cards_layout.addWidget(self.card_count)
        cards_layout.addWidget(self.card_capacity)
        vb_results.addLayout(cards_layout)

        # Dettaglio testuale
        self.lbl_detail = QLabel("")
        self.lbl_detail.setWordWrap(True)
        self.lbl_detail.setStyleSheet(
            "font-size: 10px; color: #2c3e50; padding: 4px; "
            "background-color: transparent;"
        )
        vb_results.addWidget(self.lbl_detail)


        # Separatore + bottone salvataggio
        line_save = QFrame()
        line_save.setFrameShape(QFrame.HLine)
        line_save.setFrameShadow(QFrame.Sunken)
        vb_edit.addWidget(line_save)

        self.btn_save = QPushButton("💾  Salva modifiche nel GeoJSON")
        self.btn_save.setEnabled(False)
        self.btn_save.setToolTip(
            "Sovrascrive il file GeoJSON originale con le modifiche correnti"
        )
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #6c3483; color: white; "
            "border-color: #5b2c6f; font-weight: bold; "
            "border-radius: 4px; padding: 6px 12px; min-height: 28px; }"
            "QPushButton:hover { background-color: #5b2c6f; color: white; }"
            "QPushButton:disabled { background-color: #c39bd3; color: #eee; }"
        )
        self.btn_save.clicked.connect(self._on_save_geojson)
        vb_edit.addWidget(self.btn_save)

        main_layout.addWidget(grp_results)

        # ---------- [6] Log / Stato ----------
        grp_log = QGroupBox("Log del Plugin")
        vb_log = QVBoxLayout(grp_log)

        self.lbl_log = QLabel("Plugin pronto all'uso. Carica un file GeoJSON per iniziare.")
        self.lbl_log.setWordWrap(True)
        self.lbl_log.setStyleSheet(
            "font-size: 10px; color: #1a1a1a; "
            "background-color: #ffffff; "
            "border: 1px solid #c0c0c0; "
            "border-radius: 3px; padding: 5px;"
        )
        self.lbl_log.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_log.setMinimumHeight(50)
        vb_log.addWidget(self.lbl_log)

        main_layout.addWidget(grp_log)
        main_layout.addStretch()

        # Memorizza la lista dei file recenti
        self._filepath: str = ""

    # ======================================================================
    # Slot: Caricamento File
    # ======================================================================

    def _on_browse(self):
        """Apre la finestra di dialogo per selezionare il file GeoJSON."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona file GeoJSON parcheggi",
            "",
            "GeoJSON Files (*.geojson *.json);;All Files (*)"
        )
        if not filepath:
            return

        self._filepath = filepath
        # Mostra solo il nome file per risparmiare spazio
        self.lbl_path.setText(os.path.basename(filepath))
        self.lbl_path.setToolTip(filepath)
        self.btn_load.setEnabled(True)
        self._log(f"File selezionato: {os.path.basename(filepath)}")

    def _on_load(self):
        """Carica il GeoJSON, crea e stilizza i layer, li aggiunge al progetto."""
        if not self._filepath:
            return

        self._log("Caricamento in corso…")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)   # indeterminate spinner
        self.btn_load.setEnabled(False)
        self.btn_browse.setEnabled(False)

        try:
            # --- Rimuove layer precedenti se già caricati ---
            self._remove_existing_layers()

            # --- Carica e stilizza i layer ---
            self._layer_poly, self._layer_pts = load_geojson_to_layers(
                self._filepath
            )

            # --- Imposta il CRS del progetto su EPSG:3004 PRIMA di
            #     aggiungere i layer, così il canvas eredita subito
            #     il sistema di riferimento corretto (Monte Mario Z2) ---
            epsg3004 = QgsCoordinateReferenceSystem("EPSG:3004")
            QgsProject.instance().setCrs(epsg3004)

            # --- Aggiunge al progetto QGIS ---
            QgsProject.instance().addMapLayer(self._layer_poly)
            QgsProject.instance().addMapLayer(self._layer_pts)

            # --- Zoom sull'extent del layer poligoni (già in EPSG:3004) ---
            self.canvas.setExtent(self._layer_poly.extent())
            self.canvas.refresh()

            # --- Aggiorna le statistiche nel pannello ---
            self._update_layer_info()

            # --- Abilita la selezione spaziale e i bottoni di modifica ---
            self.btn_save.setEnabled(True)
            self.btn_select.setEnabled(True)
            self.btn_add.setEnabled(True)
            self.btn_remove.setEnabled(True)

            n_poly = self._layer_poly.featureCount()
            n_pts = self._layer_pts.featureCount()
            self._log(
                f"Caricamento completato.\n"
                f"   • {n_poly} poligoni\n"
                f"   • {n_pts} punti\n"
                f"   • CRS impostato a EPSG:3004 - Monte Mario / Italy Zone 2"
            )

        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            self._log(f"❌ Errore: {exc}")
            QMessageBox.critical(
                self, "Errore di caricamento",
                f"Impossibile caricare il file GeoJSON:\n\n{exc}"
            )

        finally:
            self.progress.setVisible(False)
            self.progress.setRange(0, 100)
            self.btn_load.setEnabled(True)
            self.btn_browse.setEnabled(True)

    def _update_layer_info(self):
        """Aggiorna le etichette informative sui layer caricati."""
        if self._layer_poly is None:
            return

        n_poly = self._layer_poly.featureCount()
        n_pts = self._layer_pts.featureCount() if self._layer_pts else 0

        # Conta le feature per valore di 'fee'
        fee_yes = fee_no = fee_cond = 0
        for feat in self._layer_poly.getFeatures():
            val = feat["fee"]
            if val is None or str(val).strip() == "":
                continue
            v = str(val).lower().strip()
            if v == "yes":
                fee_yes += 1
            elif v == "no":
                fee_no += 1
            else:
                fee_cond += 1

        self.lbl_poly_count.setText(f"Parcheggi Poligonali caricati:  <b>{n_poly}</b>")
        self.lbl_pts_count.setText(f"Punti di Parcheggio caricati: <b>{n_pts}</b>")
        self.lbl_fee_yes.setText(
            f"Parcheggi a pagamento <span style='color:red'>■</span>:  <b>{fee_yes}</b>"
        )
        self.lbl_fee_no.setText(
            f"Parcheggi gratuiti <span style='color:green'>■</span>:   <b>{fee_no}</b>"
        )
        self.lbl_fee_cond.setText(
            f"Parcheggi con condizioni <span style='color:orange'>■</span>: <b>{fee_cond}</b>"
        )

        for lbl in (
            self.lbl_poly_count, self.lbl_pts_count,
            self.lbl_fee_yes, self.lbl_fee_no, self.lbl_fee_cond,
        ):
            lbl.setTextFormat(Qt.RichText)

    # ======================================================================
    # Slot: Aggiunta e Rimozione Parcheggi
    # ======================================================================

    def _on_activate_add(self):
        """Attiva o disattiva il tool di aggiunta parcheggio sul canvas."""
        if self._layer_pts is None:
            return

        # Controllo robusto: se la modalità 'add' è già attiva, annulla tutto
        if getattr(self, '_active_edit_mode', None) == 'add':
            self._on_edit_tool_finished()
            return

        # Imposta la modalità attuale su 'add'
        self._active_edit_mode = 'add'
        
        self._log("Strumento aggiunta parcheggio attivato, in attesa del click sulla mappa…")
        self._prev_map_tool = self.canvas.mapTool()
        self._add_tool = AddParkingMapTool(self.canvas, self._layer_pts)
        self._add_tool.feature_added.connect(self._on_feature_added)
        self._add_tool.tool_finished.connect(self._on_edit_tool_finished)
        self.canvas.setMapTool(self._add_tool)
        
        # Lascia il tasto "Aggiungi" abilitato per poterlo ricliccare e annullare
        self.btn_add.setEnabled(True) 
        self.btn_remove.setEnabled(False)
        self.lbl_edit_status.setText("Clicca sulla mappa per aggiungere un parcheggio... \n (Riclicca 'Aggiungi' per annullare l'operazione)")
        self.lbl_edit_status.setStyleSheet(
            "color: #000000; font-size: 10px; font-weight: bold;"
        )

    def _on_activate_remove(self):
        """Attiva o disattiva il tool di rimozione parcheggio sul canvas."""
        if self._layer_pts is None and self._layer_poly is None:
            return

        # Controllo robusto: se la modalità 'remove' è già attiva, annulla tutto
        if getattr(self, '_active_edit_mode', None) == 'remove':
            self._on_edit_tool_finished()
            return

        # Imposta la modalità attuale su 'remove'
        self._active_edit_mode = 'remove'

        target = self._layer_pts if self._layer_pts else self._layer_poly
        self._prev_map_tool = self.canvas.mapTool()
        self._remove_tool = RemoveParkingMapTool(self.canvas, target)
        self._remove_tool.feature_removed.connect(self._on_feature_removed)
        self._remove_tool.tool_finished.connect(self._on_edit_tool_finished)
        self.canvas.setMapTool(self._remove_tool)
        
        # Lascia il tasto "Rimuovi" abilitato per poterlo ricliccare e annullare
        self.btn_add.setEnabled(False)
        self.btn_remove.setEnabled(True)
        self.lbl_edit_status.setText("Clicca su un parcheggio per rimuoverlo... \n(Riclicca 'Rimuovi' per annullare l'operazione)")
        self.lbl_edit_status.setStyleSheet(
            "color: #000000; font-size: 10px; font-weight: bold;"
        )

    def _on_feature_added(self, feat):
        """Callback dopo l'aggiunta riuscita di un parcheggio."""
        name = feat["name"] if "name" in self._layer_pts.fields().names() else ""
        display = str(name) if name else "senza nome"
        self.lbl_edit_status.setText(f"Aggiunto: {display}")
        self.lbl_edit_status.setStyleSheet(
            "color: #1a5276; font-size: 10px; font-weight: bold;"
        )
        self._log(f"Parcheggio aggiunto con successo: {display}")
        # Termina il tool dopo l'aggiunta
        self._on_edit_tool_finished()

    def _on_feature_removed(self, name: str):
        """Callback dopo la rimozione riuscita di un parcheggio."""
        self.lbl_edit_status.setText(f"Rimosso: {name}")
        self.lbl_edit_status.setStyleSheet(
            "color: #784212; font-size: 10px; font-weight: bold;"
        )
        self._log(f"Parcheggio rimosso con successo: {name}")
        # Termina il tool dopo la rimozione
        self._on_edit_tool_finished()

    def _on_edit_tool_finished(self):
        """Ripristina il map tool precedente, resetta la modalità e riabilita i bottoni."""
        # Resetta la variabile di stato così i bottoni possono riattivare i tool
        self._active_edit_mode = None 
        
        self._restore_map_tool()
        
        self.btn_add.setEnabled(self._layer_pts is not None)
        self.btn_remove.setEnabled(
            self._layer_pts is not None or self._layer_poly is not None
        )
        self.lbl_edit_status.setText("")

    def _on_save_geojson(self):
        """
        Sovrascrive il file GeoJSON originale con il contenuto
        attuale dei layer (poligoni + punti) riproiettati in EPSG:4326,
        che è il CRS standard obbligatorio per i file GeoJSON (RFC 7946).
        """
        if not self._filepath:
            self._log("❌ Nessun file di origine trovato.")
            return

        import os
        from qgis.core import (
            QgsCoordinateReferenceSystem,
            QgsCoordinateTransformContext,
        )

        # GeoJSON deve essere in EPSG:4326 per specifica RFC 7946
        crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")

        # Opzioni di scrittura
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GeoJSON"
        options.fileEncoding = "UTF-8"
        options.ct = QgsCoordinateTransform(
            self._layer_poly.crs(),   # sorgente: EPSG:3004
            crs_4326,                  # destinazione: EPSG:4326
            QgsProject.instance()
        )

        # --- Salva un GeoJSON temporaneo per ogni layer ---
        import tempfile, json

        tmp_poly = tempfile.mktemp(suffix=".geojson")
        tmp_pts  = tempfile.mktemp(suffix=".geojson")

        err_poly, _ = QgsVectorFileWriter.writeAsVectorFormatV2(
            self._layer_poly,
            tmp_poly,
            QgsCoordinateTransformContext(),
            options,
        )

        options_pts = QgsVectorFileWriter.SaveVectorOptions()
        options_pts.driverName = "GeoJSON"
        options_pts.fileEncoding = "UTF-8"
        options_pts.ct = QgsCoordinateTransform(
            self._layer_pts.crs(),
            crs_4326,
            QgsProject.instance()
        )

        err_pts, _ = QgsVectorFileWriter.writeAsVectorFormatV2(
            self._layer_pts,
            tmp_pts,
            QgsCoordinateTransformContext(),
            options_pts,
        )

        if err_poly != QgsVectorFileWriter.NoError or \
           err_pts  != QgsVectorFileWriter.NoError:
            self._log("Errore durante la scrittura temporanea dei layer.")
            return

        # --- Unisce le feature dei 2 GeoJSON in un'unica FeatureCollection ---
        try:
            with open(tmp_poly, encoding="utf-8") as f:
                poly_data = json.load(f)
            with open(tmp_pts, encoding="utf-8") as f:
                pts_data = json.load(f)

            all_features = (
                poly_data.get("features", []) +
                pts_data.get("features",  [])
            )

            merged = {
                "type": "FeatureCollection",
                "features": all_features
            }

            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)

        except Exception as exc:
            self._log(f"❌ Errore durante il salvataggio:\n   {exc}")
            return
        finally:
            # Pulizia file temporanei
            for tmp in (tmp_poly, tmp_pts):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

        n_tot = len(all_features)
        self._log(
            f"Salvataggio completato!\n"
            f"   • {n_tot} parcheggi totali\n"
            f"   • Percorso del file: {os.path.basename(self._filepath)}"
        )

    # ======================================================================
    # Slot: Selezione Spaziale
    # ======================================================================

    def _on_activate_selection(self):
        """
        Tool per permettere all'utente di disegnare un rettangolo sulla mappa e
        iniziare l'analisi spaziale sui parcheggi che cadono all'interno dell'area selezionata.
        """
        if self._layer_poly is None:
            self._log("⚠️  Nessun layer caricato.")
            return

        # Salva il tool precedente e imposta il nuovo
        self._prev_map_tool = self.canvas.mapTool()

        self._map_tool = RectangleMapTool(self.canvas)
        self._map_tool.rectangle_selected.connect(self._on_rectangle_selected)
        self._map_tool.selection_cancelled.connect(self._on_selection_cancelled)

        self.canvas.setMapTool(self._map_tool)

        self.btn_select.setEnabled(False)
        self.btn_clear.setEnabled(True)
        self.lbl_tool_status.setText(
            "Disegna il rettangolo per la selezione dei parcheggi sulla mappa…"
        )
        self.lbl_tool_status.setStyleSheet(
            "color: #000000; font-size: 10px; font-weight: bold;"
        )
        self._log("Strumento per l'analisi dei parcheggi attivato")

    def _on_rectangle_selected(self, rect: QgsRectangle):
        """
        Callback chiamato dal RectangleMapTool quando l'utente ha
        terminato di disegnare il rettangolo.

        :param rect: Extent rettangolare selezionato nelle coordinate
                     del sistema di riferimento del canvas.
        """
        self._restore_map_tool()
        self.lbl_tool_status.setText("✅  Rettangolo acquisito. Analisi in corso…")
        self.lbl_tool_status.setStyleSheet(
            "color: #2980b9; font-size: 10px;"
        )

        self._run_spatial_analysis(rect)

    def _on_selection_cancelled(self):
        """Callback se l'utente preme Escape."""
        self._restore_map_tool()
        self.btn_select.setEnabled(True)
        self.lbl_tool_status.setText("⚠️  Selezione annullata.")
        self.lbl_tool_status.setStyleSheet(
            "color: #e67e22; font-size: 10px;"
        )
        self._log("Selezione annullata.")

    def _on_reset_selection(self):
        """Pulisce i risultati e reimposta l'interfaccia."""
        self._restore_map_tool()
        self.card_count.reset()
        self.card_capacity.reset()
        self.lbl_detail.setText("")
        self.lbl_tool_status.setText("")
        self.btn_select.setEnabled(self._layer_poly is not None)
        self.btn_clear.setEnabled(False)
        self._log("Reset effettuato.")

    def _restore_map_tool(self):
        """Ripristina il map tool precedente sul canvas."""
        if self._prev_map_tool is not None:
            self.canvas.setMapTool(self._prev_map_tool)
            self._prev_map_tool = None
        elif self._map_tool is not None:
            self.canvas.unsetMapTool(self._map_tool)
        self._map_tool = None

    # ======================================================================
    # Analisi Spaziale
    # ======================================================================

    def _run_spatial_analysis(self, rect: QgsRectangle):
        """
        Conta i parcheggi (poligoni) che cadono nell'area selezionata
        e somma il valore dell'attributo ``capacity``.

        Algoritmo:
          1. Trasforma il rettangolo nel CRS del layer se necessario
          2. Usa QgsFeatureRequest con filterRect per pre-filtraggio BBOX
          3. Per ogni feature filtrata verifica l'intersezione geometrica
             reale (non solo BBOX) con QgsGeometry.intersects()
          4. Somma capacity per le feature selezionate

        :param rect: QgsRectangle nel CRS del canvas (di solito EPSG:4326
                     o quello del progetto).
        """
        if self._layer_poly is None:
            return

        # --- Trasformazione CRS ---
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        layer_crs = self._layer_poly.crs()

        if canvas_crs != layer_crs:
            transform = QgsCoordinateTransform(
                canvas_crs, layer_crs, QgsProject.instance()
            )
            rect = transform.transformBoundingBox(rect)

        # --- Costruisce il rettangolo come QgsGeometry per il test preciso ---
        from qgis.core import QgsGeometry
        rect_geom = QgsGeometry.fromRect(rect)

        # --- Iterazione con filterRect (pre-filtro rapido su BBOX) ---
        request = QgsFeatureRequest().setFilterRect(rect)
        request.setFlags(QgsFeatureRequest.ExactIntersect)  # intersezione esatta

        count_parking = 0
        total_capacity = 0
        capacity_missing = 0
        fee_breakdown = {"yes": 0, "no": 0, "conditional": 0, "unknown": 0}

        for feat in self._layer_poly.getFeatures(request):
            count_parking += 1

            # Somma capacity
            cap_val = feat["capacity"]
            if cap_val is not None and str(cap_val).strip() != "":
                try:
                    total_capacity += int(cap_val)
                except (TypeError, ValueError):
                    capacity_missing += 1
            else:
                capacity_missing += 1

            # Classifica per fee
            fee_val = feat["fee"]
            if fee_val is None or str(fee_val).strip() == "":
                fee_breakdown["unknown"] += 1
            else:
                v = str(fee_val).lower().strip()
                if v == "yes":
                    fee_breakdown["yes"] += 1
                elif v == "no":
                    fee_breakdown["no"] += 1
                else:
                    fee_breakdown["conditional"] += 1

        # --- Aggiorna l'interfaccia con i risultati ---
        self._display_results(
            count_parking,
            total_capacity,
            capacity_missing,
            fee_breakdown,
        )

    def _display_results(
        self,
        count: int,
        capacity: int,
        cap_missing: int,
        fee_breakdown: dict,
    ):
        """
        Aggiorna i widget di risultato con i valori dell'analisi.

        :param count:        Numero di parcheggi nell'area selezionata
        :param capacity:     Somma dei posti auto disponibili
        :param cap_missing:  Numero di feature senza attributo capacity
        :param fee_breakdown: Dizionario con conteggio per categoria fee
        """
        self.card_count.set_value(count)
        self.card_capacity.set_value(capacity if capacity > 0 else "N/D")

        # Dettaglio fee
        detail_parts = []
        if fee_breakdown["yes"]:
            detail_parts.append(f"🔴 A pagamento: {fee_breakdown['yes']}")
        if fee_breakdown["no"]:
            detail_parts.append(f"🟢 Gratuiti: {fee_breakdown['no']}")
        if fee_breakdown["conditional"]:
            detail_parts.append(
                f"🟠 Condizionale: {fee_breakdown['conditional']}"
            )
        if fee_breakdown["unknown"]:
            detail_parts.append(
                f"⚪ Fee non specificato: {fee_breakdown['unknown']}"
            )
        if cap_missing:
            detail_parts.append(
                f"\nAttenzione! Ci sono {cap_missing} parcheggi che non specificano la capacità e non sono inclusi nel totale dei posti auto."
            )

        self.lbl_detail.setText("\n\n".join(detail_parts))

        self.lbl_tool_status.setText("✅  Analisi dei parcheggi completata")
        self.lbl_tool_status.setStyleSheet(
            "color: #1e8449; font-size: 10px; font-weight: bold;"
        )
        self.btn_select.setEnabled(True)

        self._log(
            f"Risultati selezione:\n"
            f"   • Parcheggi nell'area: {count}\n"
            f"   • Posti auto totali: {capacity}\n"
            f"   • Pagamento: {fee_breakdown['yes']} | "
            f"Gratuiti: {fee_breakdown['no']} | "
            f"Condizionali: {fee_breakdown['conditional']}"
        )

    # ======================================================================
    # Utilità
    # ======================================================================

    def _remove_existing_layers(self):
        """
        Rimuove dal progetto i layer precedentemente creati dal plugin,
        se esistenti, per evitare duplicati a ogni ricaricamento.
        """
        project = QgsProject.instance()
        to_remove = []
        for lid, layer in project.mapLayers().items():
            if layer.name() in (
                "Parcheggi – Aree (Poligoni) [EPSG:3004]",
                "Parcheggi – Stalli/Ingressi (Punti) [EPSG:3004]",
                # Compatibilità con versioni precedenti del plugin
                "Parcheggi – Aree (Poligoni)",
                "Parcheggi – Stalli/Ingressi (Punti)",
            ):
                to_remove.append(lid)
        if to_remove:
            project.removeMapLayers(to_remove)
        self._layer_poly = None
        self._layer_pts = None

    def _log(self, message: str):
        """Scrive un messaggio nel widget di log del pannello."""
        self.lbl_log.setText(message)

    def cleanup(self):
        """
        Pulisce le risorse prima che il dock venga distrutto.
        Chiamata da ParcheggiPlugin.unload().
        """
        self._restore_map_tool()
        self._remove_existing_layers()