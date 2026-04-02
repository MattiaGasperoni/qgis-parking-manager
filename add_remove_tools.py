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
    Finestra modale per inserire gli attributi del nuovo parcheggio
    prima di aggiungerlo al layer.

    Campi proposti:
      - name     : nome del parcheggio (testo libero)
      - fee      : yes / no / condizionale
      - capacity : numero intero (posti auto)
      - surface  : tipo di superficie (lista predefinita)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aggiungi Parcheggio")
        self.setMinimumWidth(320)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- Intestazione ---
        lbl_header = QLabel("Inserisci i dati del nuovo parcheggio:")
        lbl_header.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #1a5276;"
        )
        layout.addWidget(lbl_header)

        # Separatore
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # --- Form dei campi ---
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)

        # name
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("es. Parcheggio Centrale")
        form.addRow("Nome:", self.edit_name)

        # fee
        self.combo_fee = QComboBox()
        self.combo_fee.addItems(["yes", "no", ""])
        self.combo_fee.setToolTip(
            "yes = a pagamento  |  no = gratuito  |  vuoto = non specificato"
        )
        form.addRow("Fee:", self.combo_fee)

        # capacity
        self.edit_capacity = QLineEdit()
        self.edit_capacity.setPlaceholderText("es. 50  (lascia vuoto se sconosciuto)")
        form.addRow("Capacità:", self.edit_capacity)

        # surface
        self.combo_surface = QComboBox()
        self.combo_surface.addItems([
            "",           # non specificato
            "asphalt",
            "concrete",
            "paving_stones",
            "gravel",
            "ground",
            "grass",
            "sand",
            "unpaved",
        ])
        form.addRow("Superficie:", self.combo_surface)

        layout.addLayout(form)

        # --- Pulsanti OK / Annulla ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
        )
        buttons.button(QDialogButtonBox.Ok).setText("✅  Aggiungi")
        buttons.button(QDialogButtonBox.Cancel).setText("✖  Annulla")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        """Valida il campo capacity prima di chiudere."""
        cap_text = self.edit_capacity.text().strip()
        if cap_text:
            try:
                int(cap_text)
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Valore non valido",
                    "Il campo 'Capacità' deve essere un numero intero\n"
                    f"(hai inserito: '{cap_text}').",
                )
                return
        self.accept()

    # ------------------------------------------------------------------
    # Proprietà di accesso ai valori inseriti
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.edit_name.text().strip()

    @property
    def fee(self) -> str:
        return self.combo_fee.currentText().strip()

    @property
    def capacity(self):
        """Restituisce int se specificato, None altrimenti."""
        t = self.edit_capacity.text().strip()
        return int(t) if t else None

    @property
    def surface(self) -> str:
        return self.combo_surface.currentText().strip()


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