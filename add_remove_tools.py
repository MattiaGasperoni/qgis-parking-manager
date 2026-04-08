# -*- coding: utf-8 -*-
"""
add_remove_tools.py
-------------------
Strumenti mappa e dialogo per aggiungere e rimuovere parcheggi
direttamente dalla mappa interattiva.

Classi:
  - AddParkingDialog    → finestra di dialogo per inserire gli attributi
                          del nuovo parcheggio (name, fee, capacity, surface)
  - AddParkingMapTool   → strumento mappa: click sinistro sul canvas
                          aggiunge un punto nel layer punti
  - RemoveParkingMapTool → strumento mappa: click sinistro sul canvas
                           rimuove la feature più vicina al punto cliccato
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QDialogButtonBox,
    QMessageBox,
    QFrame,
)

from qgis.gui import QgsMapTool, QgsVertexMarker
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsSpatialIndex,
    QgsFeatureRequest,
)


# ===========================================================================
# Dialogo attributi nuovo parcheggio
# ===========================================================================

class AddParkingDialog(QDialog):
    """
    Finestra modale moderna per inserire gli attributi del nuovo parcheggio.

    Campi:
      - name     : nome del parcheggio
      - fee      : tariffazione (yes / no)
      - capacity : numero posti auto
      - surface  : tipo di superficie
      - operator : gestore del parcheggio       
      - covered  : parcheggio coperto           
      - lit      : illuminazione notturna       
      - access   : tipo di accesso              
    """

    # Palette colori
    _PRIMARY   = "#1a5276"
    _ACCENT    = "#2980b9"
    _BG        = "#f4f6f9"
    _CARD_BG   = "#ffffff"
    _BORDER    = "#dce3ec"
    _TEXT      = "#1a1a2e"
    _MUTED     = "#7f8c8d"
    _SUCCESS   = "#27ae60"
    _DANGER    = "#e74c3c"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuovo Parcheggio")
        self.setMinimumWidth(420)
        self.setMinimumHeight(540)
        self.setModal(True)

        # Sfondo generale
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {self._BG};
                color: {self._TEXT};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11px;
            }}
            QLabel {{
                color: {self._TEXT};
                background: transparent;
            }}
            QLabel.section-title {{
                font-size: 10px;
                font-weight: bold;
                color: {self._MUTED};
                letter-spacing: 1px;
            }}
            QLineEdit, QComboBox {{
                background-color: {self._CARD_BG};
                border: 1.5px solid {self._BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                color: {self._TEXT};
                font-size: 11px;
                min-height: 28px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {self._ACCENT};
            }}
            QLineEdit::placeholder {{
                color: {self._MUTED};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QFrame#card {{
                background-color: {self._CARD_BG};
                border: 1px solid {self._BORDER};
                border-radius: 10px;
            }}
            QPushButton#btn_ok {{
                background-color: {self._SUCCESS};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 12px;
                min-height: 36px;
            }}
            QPushButton#btn_ok:hover {{
                background-color: #1e8449;
            }}
            QPushButton#btn_cancel {{
                background-color: {self._CARD_BG};
                color: {self._MUTED};
                border: 1.5px solid {self._BORDER};
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 12px;
                min-height: 36px;
            }}
            QPushButton#btn_cancel:hover {{
                background-color: #f0f0f0;
                color: {self._DANGER};
                border-color: {self._DANGER};
            }}
            QComboBox QAbstractItemView {{
                background-color: #2c3e50;
                color: #ffffff;
                selection-background-color: {self._ACCENT};
                selection-color: #ffffff;
                border: 1px solid {self._BORDER};
                border-radius: 4px;
                padding: 4px;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 24px;
                padding: 4px 8px;
                color: #ffffff;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {self._ACCENT};
                color: #ffffff;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── Header ──────────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet(f"""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {self._PRIMARY},
                stop:1 {self._ACCENT}
            );
            border-radius: 10px;
        """)
        hb = QHBoxLayout(header)
        hb.setContentsMargins(16, 12, 16, 12)

        icon_lbl = QLabel("🅿")
        icon_lbl.setStyleSheet(
            "font-size: 28px; background: transparent; color: white;"
        )
        title_lbl = QLabel("Aggiungi Parcheggio")
        title_lbl.setStyleSheet(
            "font-size: 15px; font-weight: bold; "
            "color: white; background: transparent;"
        )
        sub_lbl = QLabel("Compila i campi del nuovo parcheggio da aggiungere alla mappa")
        sub_lbl.setStyleSheet(
            "font-size: 10px; color: rgba(255,255,255,0.8); "
            "background: transparent;"
        )

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.addWidget(title_lbl)
        text_col.addWidget(sub_lbl)

        hb.addWidget(icon_lbl)
        hb.addSpacing(8)
        hb.addLayout(text_col)
        hb.addStretch()
        root.addWidget(header)

        # ── Card: Informazioni principali ───────────────────────────
        root.addWidget(self._section_label("📋  INFORMAZIONI PRINCIPALI"))
        card1 = self._make_card()
        form1 = QFormLayout(card1)
        form1.setContentsMargins(14, 12, 14, 12)
        form1.setSpacing(10)
        form1.setLabelAlignment(Qt.AlignRight)

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("es. Parcheggio Piazza Roma")
        form1.addRow("Nome:", self.edit_name)

        self.combo_access = QComboBox()
        self.combo_access.addItem("— Non specificato —", "")
        self.combo_access.addItem("🌐  Pubblico",         "yes")
        self.combo_access.addItem("🔒  Privato",          "private")
        self.combo_access.addItem("🛍  Solo clienti",     "customers")
        self.combo_access.addItem("🏢  Solo residenti",   "residents")
        form1.addRow("Accesso:", self.combo_access)

        root.addWidget(card1)

        # ── Card: Tariffe e capacità ────────────────────────────────
        root.addWidget(self._section_label("💶  TARIFFE E CAPACITÀ"))
        card2 = self._make_card()
        form2 = QFormLayout(card2)
        form2.setContentsMargins(14, 12, 14, 12)
        form2.setSpacing(10)
        form2.setLabelAlignment(Qt.AlignRight)

        self.combo_fee = QComboBox()
        self.combo_fee.addItem("— Non specificato —", "")
        self.combo_fee.addItem("✅  Gratuito",          "no")
        self.combo_fee.addItem("💳  A pagamento",       "yes")
        form2.addRow("Tariffa:", self.combo_fee)

        self.edit_capacity = QLineEdit()
        self.edit_capacity.setPlaceholderText("es. 120  (lascia vuoto se sconosciuto)")
        form2.addRow("Posti auto:", self.edit_capacity)

        root.addWidget(card2)

        # ── Card: Caratteristiche fisiche ───────────────────────────
        root.addWidget(self._section_label("🏗  CARATTERISTICHE FISICHE"))
        card3 = self._make_card()
        form3 = QFormLayout(card3)
        form3.setContentsMargins(14, 12, 14, 12)
        form3.setSpacing(10)
        form3.setLabelAlignment(Qt.AlignRight)

        self.combo_surface = QComboBox()
        self.combo_surface.addItem("— Non specificato —",  "")
        self.combo_surface.addItem("🛣  Asfalto",           "asphalt")
        self.combo_surface.addItem("🧱  Cemento",           "concrete")
        self.combo_surface.addItem("🔲  Pavé",              "paving_stones")
        self.combo_surface.addItem("🪨  Ghiaia",            "gravel")
        self.combo_surface.addItem("🌿  Erba",              "grass")
        self.combo_surface.addItem("🌱  Terreno",           "ground")
        self.combo_surface.addItem("🏜  Sabbia",            "sand")
        self.combo_surface.addItem("❓  Non pavimentato",  "unpaved")
        form3.addRow("Superficie:", self.combo_surface)

        self.combo_covered = QComboBox()
        self.combo_covered.addItem("— Non specificato —", "")
        self.combo_covered.addItem("☀️  All'aperto",       "no")
        self.combo_covered.addItem("🏠  Coperto",          "yes")
        form3.addRow("Copertura:", self.combo_covered)

        self.combo_lit = QComboBox()
        self.combo_lit.addItem("— Non specificato —",  "")
        self.combo_lit.addItem("💡  Illuminato",        "yes")
        self.combo_lit.addItem("🌑  Non illuminato",    "no")
        form3.addRow("Illuminazione:", self.combo_lit)

        root.addWidget(card3)

        # ── Bottoni ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_cancel = QPushButton("✖  Annulla")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_ok = QPushButton("✅  Aggiungi Parcheggio")
        self.btn_ok.setObjectName("btn_ok")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._on_accept)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_ok)
        root.addLayout(btn_row)

    # ── Helper UI ───────────────────────────────────────────────────

    def _make_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        return card

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 9px; font-weight: bold; "
            f"color: {self._MUTED}; letter-spacing: 1px; "
            f"background: transparent; padding: 0 2px;"
        )
        return lbl

    # ── Validazione ─────────────────────────────────────────────────

    def _on_accept(self):
        cap_text = self.edit_capacity.text().strip()
        if cap_text:
            try:
                int(cap_text)
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Valore non valido",
                    f"Il campo 'Posti auto' deve essere un numero intero\n"
                    f"(hai inserito: '{cap_text}').",
                )
                return
        self.accept()

    # ── Proprietà (valori in inglese per il GeoJSON) ─────────────────

    @property
    def name(self) -> str:
        return self.edit_name.text().strip()

    @property
    def fee(self) -> str:
        return self.combo_fee.currentData()

    @property
    def capacity(self):
        t = self.edit_capacity.text().strip()
        return int(t) if t else None

    @property
    def surface(self) -> str:
        return self.combo_surface.currentData()

    @property
    def covered(self) -> str:
        return self.combo_covered.currentData()

    @property
    def lit(self) -> str:
        return self.combo_lit.currentData()

    @property
    def access(self) -> str:
        return self.combo_access.currentData()

# ===========================================================================
# Map Tool — Aggiunta parcheggio
# ===========================================================================

class AddParkingMapTool(QgsMapTool):
    """
    Strumento mappa per aggiungere un nuovo parcheggio puntuale.

    Al click sinistro:
      1. Mostra il dialogo AddParkingDialog per inserire gli attributi
      2. Riproietta le coordinate dal CRS del canvas al CRS del layer
      3. Aggiunge la feature al layer punti in memoria
      4. Emette il segnale ``feature_added`` con la feature inserita

    Signals:
        feature_added (QgsFeature): emesso dopo l'inserimento riuscito
        tool_finished: emesso quando l'utente preme Escape
    """

    feature_added = pyqtSignal(object)   # QgsFeature
    tool_finished = pyqtSignal()

    def __init__(self, canvas, layer_pts: QgsVectorLayer):
        """
        :param canvas:    Canvas mappa di QGIS
        :param layer_pts: Layer punti in memoria (EPSG:3004)
        """
        super().__init__(canvas)
        self.canvas = canvas
        self._layer = layer_pts
        self.setCursor(Qt.CrossCursor)

        # Marker visivo temporaneo durante l'hover
        self._marker = QgsVertexMarker(canvas)
        self._marker.setColor(QColor("#27ae60"))
        self._marker.setIconType(QgsVertexMarker.ICON_CROSS)
        self._marker.setIconSize(12)
        self._marker.setPenWidth(2)
        self._marker.hide()

    def canvasMoveEvent(self, event):
        """Mostra il marker nella posizione del cursore."""
        pt = self.toMapCoordinates(event.pos())
        self._marker.setCenter(pt)
        self._marker.show()

    def canvasPressEvent(self, event):
        """Al click sinistro apre il dialogo e aggiunge la feature."""
        if event.button() != Qt.LeftButton:
            return

        try:
            _ = self._layer.isValid()
        except RuntimeError:
            QMessageBox.warning(
                self.canvas.window(), "Errore",
                "Il layer punti non è più disponibile.\nRicarica il GeoJSON."
            )
            self.tool_finished.emit()
            return

        # Coordinate nel CRS del canvas (EPSG:3004 se il progetto è impostato)
        map_point = self.toMapCoordinates(event.pos())

        # Riproietta dal CRS canvas → CRS del layer (entrambi EPSG:3004
        # normalmente, ma gestiamo il caso generale)
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        layer_crs = self._layer.crs()
        if canvas_crs != layer_crs:
            transform = QgsCoordinateTransform(
                canvas_crs, layer_crs, QgsProject.instance()
            )
            map_point = transform.transform(map_point)

        # Apre il dialogo attributi
        dlg = AddParkingDialog(self.canvas.window())
        if dlg.exec_() != QDialog.Accepted:
            return   # utente ha annullato

        # Costruisce la feature
        feat = QgsFeature(self._layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(map_point))

        # Imposta gli attributi — solo i campi presenti nel layer
        field_names = [f.name() for f in self._layer.fields()]
        if "name"     in field_names: feat.setAttribute("name",     dlg.name or None)
        if "fee"      in field_names: feat.setAttribute("fee",      dlg.fee or None)
        if "capacity" in field_names: feat.setAttribute("capacity", dlg.capacity)
        if "surface"  in field_names: feat.setAttribute("surface",  dlg.surface or None)
        if "amenity"  in field_names: feat.setAttribute("amenity",  "parking")
        if "covered"  in field_names: feat.setAttribute("covered",  dlg.covered  or None)
        if "lit"      in field_names: feat.setAttribute("lit",      dlg.lit      or None)
        if "access"   in field_names: feat.setAttribute("access",   dlg.access   or None)
        
        # Aggiunge al layer
        self._layer.dataProvider().addFeatures([feat])
        self._layer.updateExtents()
        self._layer.triggerRepaint()

        self.feature_added.emit(feat)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._cleanup()
            self.tool_finished.emit()

    def deactivate(self):
        self._cleanup()
        super().deactivate()

    def _cleanup(self):
        self._marker.hide()
        self.canvas.scene().removeItem(self._marker)


# ===========================================================================
# Map Tool — Rimozione parcheggio
# ===========================================================================

class RemoveParkingMapTool(QgsMapTool):
    """
    Strumento mappa per rimuovere un parcheggio cliccandoci sopra.

    Al click sinistro:
      1. Cerca la feature più vicina al punto cliccato (entro una
         tolleranza di 20 pixel canvas)
      2. Chiede conferma all'utente
      3. Elimina la feature dal layer

    Funziona su entrambi i layer (punti e poligoni): il layer da
    interrogare viene passato come parametro e può essere cambiato
    dall'esterno tramite ``set_target_layer()``.

    Signals:
        feature_removed (str): emesso dopo la rimozione, con il nome
                               del parcheggio eliminato
        tool_finished: emesso quando l'utente preme Escape
    """

    feature_removed = pyqtSignal(str)
    tool_finished = pyqtSignal()

    def __init__(self, canvas, layer: QgsVectorLayer):
        super().__init__(canvas)
        self.canvas = canvas
        self._layer = layer
        self.setCursor(Qt.PointingHandCursor)

    def set_target_layer(self, layer: QgsVectorLayer):
        """Cambia il layer su cui agisce lo strumento."""
        self._layer = layer

    def canvasPressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        try:
            _ = self._layer.isValid()
        except RuntimeError:
            QMessageBox.warning(
                self.canvas.window(), "Errore",
                "Il layer non è più disponibile.\nRicarica il GeoJSON."
            )
            self.tool_finished.emit()
            return

        # Calcola la tolleranza di ricerca in unità mappa
        # (equivalente a ~20 pixel sul canvas)
        tolerance = self._pixel_tolerance(20)

        click_pt = self.toMapCoordinates(event.pos())

        # Riproietta nel CRS del layer se necessario
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        layer_crs = self._layer.crs()
        if canvas_crs != layer_crs:
            transform = QgsCoordinateTransform(
                canvas_crs, layer_crs, QgsProject.instance()
            )
            click_pt = transform.transform(click_pt)

        # Cerca feature nell'area di tolleranza
        search_rect = QgsGeometry.fromPointXY(click_pt).buffer(
            tolerance, 5
        ).boundingBox()

        request = QgsFeatureRequest().setFilterRect(search_rect)
        candidates = list(self._layer.getFeatures(request))

        if not candidates:
            QMessageBox.information(
                self.canvas.window(),
                "Nessun parcheggio trovato",
                "Nessun parcheggio trovato in prossimità del punto cliccato.\n"
                "Prova a cliccare più vicino al centro del parcheggio.",
            )
            return

        # Se più candidati, prende il più vicino al punto cliccato
        click_geom = QgsGeometry.fromPointXY(click_pt)
        feat = min(
            candidates,
            key=lambda f: f.geometry().distance(click_geom)
        )

        # Nome da mostrare nella conferma
        name_val = feat["name"] if "name" in self._layer.fields().names() else None
        display_name = str(name_val) if name_val else f"ID {feat.id()}"

        # Chiede conferma
        reply = QMessageBox.question(
            self.canvas.window(),
            "Conferma rimozione",
            f"Vuoi rimuovere il parcheggio:\n\n"
            f"  📍 {display_name}\n\n"
            f"L'operazione non è reversibile.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        # Elimina la feature
        self._layer.dataProvider().deleteFeatures([feat.id()])
        self._layer.updateExtents()
        self._layer.triggerRepaint()

        self.feature_removed.emit(display_name)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.tool_finished.emit()

    def deactivate(self):
        super().deactivate()

    def _pixel_tolerance(self, pixels: int) -> float:
        """Converte N pixel in unità mappa in base alla scala corrente."""
        mupp = self.canvas.mapUnitsPerPixel()
        return mupp * pixels