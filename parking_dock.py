# -*- coding: utf-8 -*-
"""
parking_dock.py
---------------
Finestra del plugin, contiene:
  - Caricamento file GeoJSON e creazione dei layer
  - Informazioni sui parcheggi caricati
  - Strumenti per l'aggiunta, la rimozione e il salvataggio di parcheggi
  - Analisi spaziale tramite selezione rettangolare interattiva sulla mappa
  - Risultati dell'analisi spaziale
  - Log del plugin
"""

import os
import tempfile
import json
from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QGroupBox,
    QFrame,
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
    QgsCoordinateTransformContext,
    QgsFeatureRequest,
    QgsVectorFileWriter,
    QgsGeometry,
)

from .map_tool_extent import RectangleMapTool
from .layer_loader import load_geojson_to_layers
from .add_remove_tools import AddParkingMapTool, RemoveParkingMapTool


# ---------------------------------------------------------------------------
# Palette colori centralizzata
# ---------------------------------------------------------------------------
_C = {
    # Neutri
    "bg_panel":   "#f5f5f7",
    "bg_card":    "#ffffff",
    "border":     "#d1d1d6",
    "text":       "#1c1c1e",
    "text_muted": "#6c6c70",

    # Blu — Carica Layer, Salva modifiche
    "blue":       "#0071e3",
    "blue_hover": "#0077ed",
    "blue_press": "#005cbf",

    # Verde — Aggiungi, Seleziona Area
    "green":       "#28cd41",
    "green_hover": "#20a335",
    "green_press": "#178a2c",

    # Rosso — Rimuovi, Reset
    "red":         "#ff3b30",
    "red_hover":   "#d93025",
    "red_press":   "#b5271f",

    # Grigio disabilitato
    "disabled_bg":   "#e5e5ea",
    "disabled_text": "#aeaeb2",
    "disabled_bdr":  "#c7c7cc",

    # Accento info/risultati
    "accent_bg":  "#eaf4fb",
    "accent_bdr": "#aed6f1",
    "accent_txt": "#1a5276",
}


# ---------------------------------------------------------------------------
# Stili CSS globali
# ---------------------------------------------------------------------------
def _btn(bg, hover, pressed, text_color="#ffffff", disabled_bg=None, disabled_text=None, disabled_bdr=None):
    """Helper che genera il CSS per un QPushButton con stile Apple-like."""
    db  = disabled_bg   or _C["disabled_bg"]
    dt  = disabled_text or _C["disabled_text"]
    dbr = disabled_bdr  or _C["disabled_bdr"]
    return (
        f"QPushButton {{"
        f"  background-color: {bg}; color: {text_color};"
        f"  border: 1px solid {bg}; border-radius: 8px;"
        f"  padding: 7px 14px; min-height: 28px;"
        f"  font-size: 12px; font-weight: 600;"
        f"}}"
        f"QPushButton:hover   {{ background-color: {hover}; border-color: {hover}; }}"
        f"QPushButton:pressed {{ background-color: {pressed}; border-color: {pressed}; }}"
        f"QPushButton:disabled {{"
        f"  background-color: {db}; color: {dt}; border-color: {dbr};"
        f"}}"
    )


# Stili per singolo pulsante (applicati via setStyleSheet sul widget)
_BTN_NEUTRAL = _btn(
    bg="#e5e5ea", hover="#d1d1d6", pressed="#c7c7cc",
    text_color=_C["text"],
    disabled_bg=_C["disabled_bg"], disabled_text=_C["disabled_text"]
)
_BTN_BLUE    = _btn(_C["blue"],  _C["blue_hover"],  _C["blue_press"])
_BTN_GREEN   = _btn(_C["green"], _C["green_hover"], _C["green_press"])
_BTN_RED     = _btn(_C["red"],   _C["red_hover"],   _C["red_press"])

# Foglio di stile globale del pannello
_DOCK_STYLE = f"""
QWidget {{
    background-color: {_C["bg_panel"]};
    color: {_C["text"]};
    font-family: -apple-system, "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
}}
QScrollArea {{
    background-color: {_C["bg_panel"]};
    border: none;
}}
QGroupBox {{
    font-weight: 700;
    font-size: 11px;
    border: 1px solid {_C["border"]};
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 8px;
    background-color: {_C["bg_card"]};
    color: {_C["text"]};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    background-color: {_C["bg_card"]};
    color: {_C["accent_txt"]};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.3px;
}}
QLabel {{
    color: {_C["text"]};
    background-color: transparent;
    font-size: 11px;
}}
QLabel#lbl_path {{
    color: {_C["text_muted"]};
    font-size: 10px;
    padding: 5px 8px;
    border: 1px solid {_C["border"]};
    border-radius: 6px;
    background-color: {_C["bg_card"]};
}}
QLabel#lbl_status {{
    color: {_C["text_muted"]};
    font-size: 10px;
    padding: 2px 4px;
    background-color: transparent;
}}
"""

_RESULT_CARD_STYLE = f"""
QFrame#result_card {{
    background-color: {_C["accent_bg"]};
    border: 1px solid {_C["accent_bdr"]};
    border-radius: 8px;
    padding: 4px;
}}
"""


# ---------------------------------------------------------------------------
# Widget scheda risultato
# ---------------------------------------------------------------------------
class _ResultCard(QFrame):
    """
    Widget a scheda per mostrare un singolo risultato numerico.

    Layout verticale:
      [icona / titolo]
      [valore grande]
    """

    def __init__(self, title: str, icon_char: str, parent=None):
        super().__init__(parent)
        self.setObjectName("result_card")
        self.setStyleSheet(_RESULT_CARD_STYLE)
        self.setMinimumWidth(110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        lbl_title = QLabel(f"{icon_char}  {title}")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet(
            f"font-size: 10px; color: {_C['accent_txt']}; font-weight: bold; "
            "background-color: transparent;"
        )
        layout.addWidget(lbl_title)

        self.lbl_value = QLabel("—")
        self.lbl_value.setAlignment(Qt.AlignCenter)
        self.lbl_value.setStyleSheet(
            f"font-size: 26px; font-weight: bold; color: {_C['accent_txt']}; "
            "background-color: transparent;"
        )
        layout.addWidget(self.lbl_value)

    def set_value(self, value):
        self.lbl_value.setText(str(value))

    def reset(self):
        self.lbl_value.setText("—")


# ---------------------------------------------------------------------------
# Dock principale
# ---------------------------------------------------------------------------
class ParcheggiDock(QgsDockWidget):
    """Pannello principale del plugin QGIS Parking Manager."""

    def __init__(self, iface):
        super().__init__("QGIS Parking Manager", iface.mainWindow())
        self.iface  = iface
        self.canvas = iface.mapCanvas()

        # Layer attivi
        self._layer_poly: Optional[QgsVectorLayer] = None
        self._layer_pts:  Optional[QgsVectorLayer] = None

        # Percorso del file GeoJSON corrente
        self._filepath: str = ""

        # Map tool per la selezione rettangolare
        self._map_tool: Optional[RectangleMapTool] = None
        # Map tool precedente (ripristinato dopo selezione / modifica)
        self._prev_map_tool = None

        # Map tool per aggiunta / rimozione parcheggi
        self._add_tool:    Optional[AddParkingMapTool]    = None
        self._remove_tool: Optional[RemoveParkingMapTool] = None

        # Modalità di editing attiva ('add' | 'remove' | None)
        self._active_edit_mode = None

        self._build_ui()
        self.setMinimumWidth(280)
        self.setMaximumWidth(420)

    # ======================================================================
    # Costruzione interfaccia grafica
    # ======================================================================

    def _build_ui(self):
        root_widget = QWidget()
        root_widget.setStyleSheet(_DOCK_STYLE)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(root_widget)
        scroll.setFrameShape(QFrame.NoFrame)
        self.setWidget(scroll)

        main_layout = QVBoxLayout(root_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        main_layout.addWidget(self._build_section_load())
        main_layout.addWidget(self._build_section_info())
        main_layout.addWidget(self._build_section_edit())
        main_layout.addWidget(self._build_section_spatial())
        main_layout.addWidget(self._build_section_results())
        main_layout.addWidget(self._build_section_log())
        main_layout.addStretch()

    # ------------------------------------------------------------------
    # Sezione 1 — Caricamento File GeoJSON
    # ------------------------------------------------------------------

    def _build_section_load(self) -> QGroupBox:
        grp = QGroupBox("Caricamento File GeoJSON")
        layout = QVBoxLayout(grp)
        layout.setSpacing(8)

        # Etichetta percorso file
        self.lbl_path = QLabel("Nessun file selezionato")
        self.lbl_path.setObjectName("lbl_path")
        self.lbl_path.setWordWrap(True)
        layout.addWidget(self.lbl_path)

        # Bottoni Sfoglia + Carica Layer
        hb = QHBoxLayout()
        hb.setSpacing(8)

        self.btn_browse = QPushButton("📁  Sfoglia…")
        self.btn_browse.setStyleSheet(_BTN_NEUTRAL)
        self.btn_browse.setToolTip("Seleziona un file .geojson dal disco")
        self.btn_browse.clicked.connect(self._on_browse)

        self.btn_load = QPushButton("⬆  Carica Layer")
        self.btn_load.setStyleSheet(_BTN_BLUE)
        self.btn_load.setEnabled(False)
        self.btn_load.setToolTip("Carica il GeoJSON e crea i layer in memoria")
        self.btn_load.clicked.connect(self._on_load)

        hb.addWidget(self.btn_browse)
        hb.addWidget(self.btn_load)
        layout.addLayout(hb)

        # Progress bar (visibile solo durante il caricamento)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        layout.addWidget(self.progress)

        return grp

    # ------------------------------------------------------------------
    # Sezione 2 — Informazioni Parcheggi Caricati
    # ------------------------------------------------------------------

    def _build_section_info(self) -> QGroupBox:
        grp = QGroupBox("Informazioni sui Parcheggi Caricati")
        layout = QVBoxLayout(grp)
        layout.setSpacing(4)

        self.lbl_poly_count = QLabel("Parcheggi Poligonali caricati: —")
        self.lbl_pts_count  = QLabel("Punti di Parcheggio caricati: —")
        self.lbl_fee_yes    = QLabel("Parcheggi a pagamento: —")
        self.lbl_fee_no     = QLabel("Parcheggi gratuiti: —")
        self.lbl_fee_cond   = QLabel("Parcheggi con condizioni: —")
        self.lbl_fee_none   = QLabel("Parcheggi senza informazioni: —")

        for lbl in (
            self.lbl_poly_count, self.lbl_pts_count,
            self.lbl_fee_yes, self.lbl_fee_no,
            self.lbl_fee_cond, self.lbl_fee_none,
        ):
            lbl.setStyleSheet(
                f"font-size: 11px; padding: 2px 4px; "
                f"color: {_C['text']}; background-color: transparent;"
            )
            layout.addWidget(lbl)

        return grp

    # ------------------------------------------------------------------
    # Sezione 3 — Aggiunta, Rimozione e Salvataggio
    # ------------------------------------------------------------------

    def _build_section_edit(self) -> QGroupBox:
        grp = QGroupBox("Modifica Parcheggi")
        layout = QVBoxLayout(grp)
        layout.setSpacing(8)

        hint = QLabel("Clicca sui bottoni per aggiungere o rimuovere un parcheggio.")
        hint.setStyleSheet(
            f"font-size: 10px; color: {_C['text_muted']}; "
            "padding: 2px; background-color: transparent;"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Riga Aggiungi + Rimuovi
        hb_edit = QHBoxLayout()
        hb_edit.setSpacing(8)

        self.btn_add = QPushButton("＋  Aggiungi")
        self.btn_add.setStyleSheet(_BTN_GREEN)
        self.btn_add.setEnabled(False)
        self.btn_add.setToolTip("Clicca sulla mappa per aggiungere un nuovo punto di parcheggio")
        self.btn_add.clicked.connect(self._on_activate_add)

        self.btn_remove = QPushButton("－  Rimuovi")
        self.btn_remove.setStyleSheet(_BTN_RED)
        self.btn_remove.setEnabled(False)
        self.btn_remove.setToolTip("Clicca su un parcheggio esistente per rimuoverlo")
        self.btn_remove.clicked.connect(self._on_activate_remove)

        hb_edit.addWidget(self.btn_add)
        hb_edit.addWidget(self.btn_remove)
        layout.addLayout(hb_edit)

        # Stato strumento modifica
        self.lbl_edit_status = QLabel("")
        self.lbl_edit_status.setObjectName("lbl_status")
        self.lbl_edit_status.setAlignment(Qt.AlignCenter)
        self.lbl_edit_status.setWordWrap(True)
        layout.addWidget(self.lbl_edit_status)

        # Separatore
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(f"color: {_C['border']};")
        layout.addWidget(sep)

        # Bottone Salva
        self.btn_save = QPushButton("💾  Salva modifiche nel GeoJSON")
        self.btn_save.setStyleSheet(_BTN_BLUE)
        self.btn_save.setEnabled(False)
        self.btn_save.setToolTip("Sovrascrive il file GeoJSON originale con le modifiche correnti")
        self.btn_save.clicked.connect(self._on_save_geojson)
        layout.addWidget(self.btn_save)

        return grp

    # ------------------------------------------------------------------
    # Sezione 4 — Analisi Spaziale
    # ------------------------------------------------------------------

    def _build_section_spatial(self) -> QGroupBox:
        grp = QGroupBox("Analisi Spaziale")
        layout = QVBoxLayout(grp)
        layout.setSpacing(8)

        hint = QLabel(
            "Clicca il bottone, poi disegna un rettangolo sulla mappa tenendo premuto."
        )
        hint.setStyleSheet(
            f"font-size: 10px; color: {_C['text_muted']}; "
            "padding: 2px; background-color: transparent;"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Riga Seleziona Area + Reset
        hb_sel = QHBoxLayout()
        hb_sel.setSpacing(8)

        self.btn_select = QPushButton("🔍  Seleziona Area")
        self.btn_select.setStyleSheet(_BTN_GREEN)
        self.btn_select.setEnabled(False)
        self.btn_select.setToolTip("Attiva lo strumento di selezione rettangolare sulla mappa")
        self.btn_select.clicked.connect(self._on_activate_selection)

        self.btn_clear = QPushButton("✖  Reset")
        self.btn_clear.setStyleSheet(_BTN_RED)
        self.btn_clear.setEnabled(False)
        self.btn_clear.setToolTip("Cancella la selezione e i risultati")
        self.btn_clear.clicked.connect(self._on_reset_selection)

        hb_sel.addWidget(self.btn_select)
        hb_sel.addWidget(self.btn_clear)
        layout.addLayout(hb_sel)

        # Stato strumento selezione
        self.lbl_tool_status = QLabel("")
        self.lbl_tool_status.setObjectName("lbl_status")
        self.lbl_tool_status.setAlignment(Qt.AlignCenter)
        self.lbl_tool_status.setWordWrap(True)
        layout.addWidget(self.lbl_tool_status)

        return grp

    # ------------------------------------------------------------------
    # Sezione 5 — Risultati Analisi Spaziale
    # ------------------------------------------------------------------

    def _build_section_results(self) -> QGroupBox:
        grp = QGroupBox("📊  Risultati Analisi Spaziale")
        layout = QVBoxLayout(grp)
        layout.setSpacing(8)

        # Schede numeriche
        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)

        self.card_count    = _ResultCard("Parcheggi", "🅿")
        self.card_capacity = _ResultCard("Posti auto", "🚗")

        cards_row.addWidget(self.card_count)
        cards_row.addWidget(self.card_capacity)
        layout.addLayout(cards_row)

        # Dettaglio testuale
        self.lbl_detail = QLabel("")
        self.lbl_detail.setWordWrap(True)
        self.lbl_detail.setStyleSheet(
            f"font-size: 10px; color: {_C['text']}; "
            "padding: 4px; background-color: transparent;"
        )
        layout.addWidget(self.lbl_detail)

        return grp

    # ------------------------------------------------------------------
    # Sezione 6 — Log del Plugin
    # ------------------------------------------------------------------

    def _build_section_log(self) -> QGroupBox:
        grp = QGroupBox("Log del Plugin")
        layout = QVBoxLayout(grp)

        self.lbl_log = QLabel("Plugin pronto all'uso. Carica un file GeoJSON per iniziare.")
        self.lbl_log.setWordWrap(True)
        self.lbl_log.setStyleSheet(
            f"font-size: 10px; color: {_C['text']}; "
            f"background-color: {_C['bg_card']}; "
            f"border: 1px solid {_C['border']}; "
            "border-radius: 6px; padding: 6px;"
        )
        self.lbl_log.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_log.setMinimumHeight(50)
        layout.addWidget(self.lbl_log)

        return grp

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
        self.progress.setRange(0, 0)   # spinner indeterminato
        self.btn_load.setEnabled(False)
        self.btn_browse.setEnabled(False)

        try:
            self._remove_existing_layers()

            self._layer_poly, self._layer_pts = load_geojson_to_layers(self._filepath)

            # Imposta il CRS del progetto su EPSG:3004 prima di aggiungere i layer
            QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:3004"))

            QgsProject.instance().addMapLayer(self._layer_poly)
            QgsProject.instance().addMapLayer(self._layer_pts)

            self.canvas.setExtent(self._layer_poly.extent())
            self.canvas.refresh()

            self._update_layer_info()

            # Abilita tutti i bottoni post-caricamento
            self.btn_save.setEnabled(True)
            self.btn_select.setEnabled(True)
            self.btn_add.setEnabled(True)
            self.btn_remove.setEnabled(True)

            n_poly = self._layer_poly.featureCount()
            n_pts  = self._layer_pts.featureCount()
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

    # ======================================================================
    # Slot: Informazioni Layer
    # ======================================================================

    def _update_layer_info(self):
        """Aggiorna le etichette informative sui layer caricati."""
        if self._layer_poly is None:
            return

        n_poly = self._layer_poly.featureCount()
        n_pts  = self._layer_pts.featureCount() if self._layer_pts else 0

        fee_yes = fee_no = fee_cond = fee_none = 0
        for feat in self._layer_poly.getFeatures():
            val     = feat["fee"]
            v       = str(val).strip()
            v_lower = v.lower()
            if v_lower == "yes":
                fee_yes += 1
            elif v_lower == "no":
                fee_no += 1
            elif v_lower in ("privat", "private") or any(c in v for c in (":", "-", "00")):
                fee_cond += 1
            else:
                fee_none += 1

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
        self.lbl_fee_none.setText(
            f"Parcheggi senza informazioni <span style='color:gray'>■</span>: <b>{fee_none}</b>"
        )

        for lbl in (
            self.lbl_poly_count, self.lbl_pts_count,
            self.lbl_fee_yes, self.lbl_fee_no,
            self.lbl_fee_cond, self.lbl_fee_none,
        ):
            lbl.setTextFormat(Qt.RichText)

    # ======================================================================
    # Slot: Aggiunta e Rimozione Parcheggi
    # ======================================================================

    def _on_activate_add(self):
        """Attiva o disattiva il tool di aggiunta parcheggio sul canvas."""
        if self._layer_pts is None:
            return

        # Se già attivo, annulla
        if self._active_edit_mode == 'add':
            self._on_edit_tool_finished()
            return

        self._active_edit_mode = 'add'
        self._prev_map_tool = self.canvas.mapTool()

        self._add_tool = AddParkingMapTool(self.canvas, self._layer_pts)
        self._add_tool.feature_added.connect(self._on_feature_added)
        self._add_tool.tool_finished.connect(self._on_edit_tool_finished)
        self.canvas.setMapTool(self._add_tool)

        self.btn_add.setEnabled(True)
        self.btn_remove.setEnabled(False)
        self.lbl_edit_status.setText(
            "Clicca sulla mappa per aggiungere un parcheggio…\n"
            "(Riclicca 'Aggiungi' per annullare)"
        )
        self.lbl_edit_status.setStyleSheet(
            f"color: {_C['text']}; font-size: 10px; font-weight: bold;"
        )
        self._log("Strumento aggiunta parcheggio attivato, in attesa del click sulla mappa…")

    def _on_activate_remove(self):
        """Attiva o disattiva il tool di rimozione parcheggio sul canvas."""
        if self._layer_pts is None and self._layer_poly is None:
            return

        # Se già attivo, annulla
        if self._active_edit_mode == 'remove':
            self._on_edit_tool_finished()
            return

        self._active_edit_mode = 'remove'

        target = self._layer_pts if self._layer_pts else self._layer_poly
        self._prev_map_tool = self.canvas.mapTool()

        self._remove_tool = RemoveParkingMapTool(self.canvas, target)
        self._remove_tool.feature_removed.connect(self._on_feature_removed)
        self._remove_tool.tool_finished.connect(self._on_edit_tool_finished)
        self.canvas.setMapTool(self._remove_tool)

        self.btn_add.setEnabled(False)
        self.btn_remove.setEnabled(True)
        self.lbl_edit_status.setText(
            "Clicca su un parcheggio per rimuoverlo…\n"
            "(Riclicca 'Rimuovi' per annullare)"
        )
        self.lbl_edit_status.setStyleSheet(
            f"color: {_C['text']}; font-size: 10px; font-weight: bold;"
        )
        self._log("Strumento rimozione parcheggio attivato, in attesa del click sulla mappa…")

    def _on_feature_added(self, feat):
        """Callback dopo l'aggiunta riuscita di un parcheggio."""
        name = feat["name"] if "name" in self._layer_pts.fields().names() else ""
        display = str(name) if name else "senza nome"
        self.lbl_edit_status.setText(f"✅  Aggiunto: {display}")
        self.lbl_edit_status.setStyleSheet(
            f"color: {_C['accent_txt']}; font-size: 10px; font-weight: bold;"
        )
        self._log(f"Parcheggio aggiunto con successo: {display}")
        self._on_edit_tool_finished()

    def _on_feature_removed(self, name: str):
        """Callback dopo la rimozione riuscita di un parcheggio."""
        self.lbl_edit_status.setText(f"🗑  Rimosso: {name}")
        self.lbl_edit_status.setStyleSheet(
            f"color: {_C['red']}; font-size: 10px; font-weight: bold;"
        )
        self._log(f"Parcheggio rimosso con successo: {name}")
        self._on_edit_tool_finished()

    def _on_edit_tool_finished(self):
        """Ripristina il map tool precedente, resetta la modalità e riabilita i bottoni."""
        self._active_edit_mode = None
        self._restore_map_tool()
        self.btn_add.setEnabled(self._layer_pts is not None)
        self.btn_remove.setEnabled(
            self._layer_pts is not None or self._layer_poly is not None
        )
        self.lbl_edit_status.setText("")
        self._log("")

    def _on_save_geojson(self):
        """
        Sovrascrive il file GeoJSON originale con il contenuto attuale dei layer
        (poligoni + punti) riproiettati in EPSG:4326 (RFC 7946).
        """
        if not self._filepath:
            self._log("❌ Nessun file di origine trovato.")
            return

        crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")

        def _write_tmp(layer) -> str:
            tmp = tempfile.mktemp(suffix=".geojson")
            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName   = "GeoJSON"
            opts.fileEncoding = "UTF-8"
            opts.ct = QgsCoordinateTransform(
                layer.crs(), crs_4326, QgsProject.instance()
            )
            err, _ = QgsVectorFileWriter.writeAsVectorFormatV2(
                layer, tmp, QgsCoordinateTransformContext(), opts
            )
            if err != QgsVectorFileWriter.NoError:
                raise RuntimeError(f"Errore scrittura temporanea layer: {layer.name()}")
            return tmp

        tmp_poly = tmp_pts = None
        try:
            tmp_poly = _write_tmp(self._layer_poly)
            tmp_pts  = _write_tmp(self._layer_pts)

            with open(tmp_poly, encoding="utf-8") as f:
                poly_data = json.load(f)
            with open(tmp_pts, encoding="utf-8") as f:
                pts_data = json.load(f)

            all_features = (
                poly_data.get("features", []) +
                pts_data.get("features",  [])
            )
            merged = {"type": "FeatureCollection", "features": all_features}

            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)

        except Exception as exc:
            self._log(f"❌ Errore durante il salvataggio:\n   {exc}")
            return

        finally:
            for tmp in (tmp_poly, tmp_pts):
                if tmp:
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
        Attiva il tool per disegnare un rettangolo sulla mappa e
        avviare l'analisi spaziale dei parcheggi nell'area selezionata.
        """
        if self._layer_poly is None:
            self._log("⚠️  Nessun layer caricato.")
            return

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
            f"color: {_C['text']}; font-size: 10px; font-weight: bold;"
        )
        self._log("Strumento per l'analisi dei parcheggi attivato")

    def _on_rectangle_selected(self, rect: QgsRectangle):
        """Callback chiamato quando l'utente ha terminato di disegnare il rettangolo."""
        self._restore_map_tool()
        self.lbl_tool_status.setText("✅  Rettangolo acquisito. Analisi in corso…")
        self.lbl_tool_status.setStyleSheet(
            f"color: {_C['blue']}; font-size: 10px;"
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
          3. Verifica l'intersezione geometrica esatta con ExactIntersect
          4. Somma capacity e classifica per fee

        :param rect: QgsRectangle nel CRS del canvas.
        """
        if self._layer_poly is None:
            return

        # Trasformazione CRS se necessaria
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        layer_crs  = self._layer_poly.crs()
        if canvas_crs != layer_crs:
            transform = QgsCoordinateTransform(
                canvas_crs, layer_crs, QgsProject.instance()
            )
            rect = transform.transformBoundingBox(rect)

        request = QgsFeatureRequest().setFilterRect(rect)
        request.setFlags(QgsFeatureRequest.ExactIntersect)

        count_parking    = 0
        total_capacity   = 0
        capacity_missing = 0
        fee_breakdown    = {"yes": 0, "no": 0, "conditional": 0, "unknown": 0}

        for feat in self._layer_poly.getFeatures(request):
            count_parking += 1

            cap_val = feat["capacity"]
            if cap_val is not None and str(cap_val).strip() != "":
                try:
                    total_capacity += int(cap_val)
                except (TypeError, ValueError):
                    capacity_missing += 1
            else:
                capacity_missing += 1

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

        self._display_results(count_parking, total_capacity, capacity_missing, fee_breakdown)

    def _display_results(self, count: int, capacity: int, cap_missing: int, fee_breakdown: dict):
        """
        Aggiorna i widget di risultato con i valori dell'analisi.

        :param count:         Numero di parcheggi nell'area selezionata
        :param capacity:      Somma dei posti auto disponibili
        :param cap_missing:   Numero di feature senza attributo capacity
        :param fee_breakdown: Dizionario con conteggio per categoria fee
        """
        self.card_count.set_value(count)
        self.card_capacity.set_value(capacity if capacity > 0 else "N/D")

        detail_parts = []
        if fee_breakdown["yes"]:
            detail_parts.append(f"🔴 A pagamento: {fee_breakdown['yes']}")
        if fee_breakdown["no"]:
            detail_parts.append(f"🟢 Gratuiti: {fee_breakdown['no']}")
        if fee_breakdown["conditional"]:
            detail_parts.append(f"🟠 Condizionale: {fee_breakdown['conditional']}")
        if fee_breakdown["unknown"]:
            detail_parts.append(f"⚪ Fee non specificato: {fee_breakdown['unknown']}")
        if cap_missing:
            detail_parts.append(
                f"\nAttenzione! {cap_missing} parcheggi non specificano la capacità "
                "e non sono inclusi nel totale dei posti auto."
            )

        self.lbl_detail.setText("\n\n".join(detail_parts))

        self.lbl_tool_status.setText("✅  Analisi dei parcheggi completata")
        self.lbl_tool_status.setStyleSheet(
            f"color: {_C['green_press']}; font-size: 10px; font-weight: bold;"
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
        project   = QgsProject.instance()
        to_remove = [
            lid for lid, layer in project.mapLayers().items()
            if layer.name() in ("Parcheggi – Poligoni", "Parcheggi – Punti")
        ]
        if to_remove:
            project.removeMapLayers(to_remove)
        self._layer_poly = None
        self._layer_pts  = None

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