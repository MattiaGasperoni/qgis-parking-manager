# -*- coding: utf-8 -*-
"""
map_tool_extent.py
------------------
Strumento mappa personalizzato per la selezione rettangolare interattiva.

Estende QgsMapTool per catturare click-and-drag sul canvas e
restituire il rettangolo di selezione (QgsRectangle) tramite un
segnale PyQt5.

Uso tipico:
    tool = RectangleMapTool(canvas)
    tool.rectangle_selected.connect(my_callback)
    canvas.setMapTool(tool)
"""

from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtGui import QColor

from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.core import QgsWkbTypes, QgsPointXY, QgsRectangle


class RectangleMapTool(QgsMapTool):
    """
    Map tool che disegna un rettangolo rubber-band sul canvas e
    emette il segnale ``rectangle_selected`` con il QgsRectangle
    finale quando l'utente rilascia il tasto del mouse.

    Signals:
        rectangle_selected (QgsRectangle): emesso al mouse-release
            con l'extent selezionato.
        selection_cancelled: emesso se l'utente preme Escape.
    """

    rectangle_selected = pyqtSignal(object)   # QgsRectangle
    selection_cancelled = pyqtSignal()

    def __init__(self, canvas):
        """
        :param canvas: Il canvas mappa di QGIS.
        :type canvas:  QgsMapCanvas
        """
        super().__init__(canvas)
        self.canvas = canvas

        # --- Stato interno ---
        self._start_point: QgsPointXY | None = None
        self._end_point: QgsPointXY | None = None
        self._is_drawing = False

        # --- Rubber band (rettangolo visivo) ---
        self._rubber_band = QgsRubberBand(
            self.canvas, QgsWkbTypes.PolygonGeometry
        )
        self._rubber_band.setColor(QColor(0, 120, 215, 80))     # riempimento blu trasparente
        self._rubber_band.setStrokeColor(QColor(0, 80, 180, 220))  # bordo blu scuro
        self._rubber_band.setWidth(2)
        self._rubber_band.setLineStyle(Qt.DashLine)

        # Cambia il cursore del mouse per segnalare lo strumento attivo
        self.setCursor(Qt.CrossCursor)

    # ------------------------------------------------------------------
    # Override degli eventi mouse (API QgsMapTool)
    # ------------------------------------------------------------------

    def canvasPressEvent(self, event):
        """Registra il punto di inizio al click sinistro."""
        if event.button() == Qt.LeftButton:
            self._start_point = self.toMapCoordinates(event.pos())
            self._end_point = self._start_point
            self._is_drawing = True
            self._update_rubber_band()

    def canvasMoveEvent(self, event):
        """Aggiorna il rubber band durante il trascinamento."""
        if self._is_drawing:
            self._end_point = self.toMapCoordinates(event.pos())
            self._update_rubber_band()

    def canvasReleaseEvent(self, event):
        """Al rilascio emette il segnale con il rettangolo finale."""
        if event.button() == Qt.LeftButton and self._is_drawing:
            self._end_point = self.toMapCoordinates(event.pos())
            self._is_drawing = False
            self._rubber_band.reset()

            rect = self._build_rectangle()
            if rect and not rect.isEmpty():
                self.rectangle_selected.emit(rect)
            else:
                # Selezione troppo piccola: avvisa e annulla
                self.selection_cancelled.emit()

    def keyPressEvent(self, event):
        """Escape annulla la selezione in corso."""
        if event.key() == Qt.Key_Escape:
            self._reset()
            self.selection_cancelled.emit()

    # ------------------------------------------------------------------
    # Metodi interni
    # ------------------------------------------------------------------

    def _update_rubber_band(self):
        """Disegna il rubber band aggiornato con i punti correnti."""
        if self._start_point is None or self._end_point is None:
            return
        self._rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        rect = self._build_rectangle()
        if rect:
            # Aggiunge i 4 vertici del rettangolo al rubber band
            self._rubber_band.addPoint(
                QgsPointXY(rect.xMinimum(), rect.yMinimum()), False
            )
            self._rubber_band.addPoint(
                QgsPointXY(rect.xMaximum(), rect.yMinimum()), False
            )
            self._rubber_band.addPoint(
                QgsPointXY(rect.xMaximum(), rect.yMaximum()), False
            )
            self._rubber_band.addPoint(
                QgsPointXY(rect.xMinimum(), rect.yMaximum()), True
            )
            self._rubber_band.show()

    def _build_rectangle(self) -> QgsRectangle | None:
        """Costruisce il QgsRectangle dai due punti d'angolo."""
        if self._start_point is None or self._end_point is None:
            return None
        return QgsRectangle(self._start_point, self._end_point)

    def _reset(self):
        """Pulisce lo stato interno e il rubber band."""
        self._start_point = None
        self._end_point = None
        self._is_drawing = False
        self._rubber_band.reset()

    def deactivate(self):
        """Chiamata da QGIS quando lo strumento viene disattivato."""
        self._reset()
        super().deactivate()
