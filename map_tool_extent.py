# -*- coding: utf-8 -*-
"""
map_tool_extent.py — Strumento mappa per la selezione rettangolare interattiva.
Disegna un rubber-band sul canvas al click-and-drag e restituisce il
QgsRectangle selezionato tramite il segnale rectangle_selected.
"""

from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtGui import QColor

from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.core import QgsWkbTypes, QgsPointXY, QgsRectangle


class RectangleMapTool(QgsMapTool):
    """
    Map tool che emette rectangle_selected (QgsRectangle) al mouse-release
    e selection_cancelled se l'utente preme Escape.
    """

    rectangle_selected = pyqtSignal(object)
    selection_cancelled = pyqtSignal()

    def __init__(self, canvas):
        """Inizializza il rubber-band e imposta il cursore a croce."""
        super().__init__(canvas)
        self.canvas = canvas

        self._start_point: QgsPointXY | None = None
        self._end_point: QgsPointXY | None = None
        self._is_drawing = False

        self._rubber_band = QgsRubberBand(
            self.canvas, QgsWkbTypes.PolygonGeometry
        )
        self._rubber_band.setColor(QColor(0, 120, 215, 80))
        self._rubber_band.setStrokeColor(QColor(0, 80, 180, 220))
        self._rubber_band.setWidth(2)
        self._rubber_band.setLineStyle(Qt.DashLine)

        self.setCursor(Qt.CrossCursor)

    # ------------------------------------------------------------------
    # Override degli eventi mouse
    # ------------------------------------------------------------------

    def canvasPressEvent(self, event):
        """Registra il punto di inizio al click sinistro."""
        if event.button() == Qt.LeftButton:
            self._start_point = self.toMapCoordinates(event.pos())
            self._end_point = self._start_point
            self._is_drawing = True
            self._update_rubber_band()

    def canvasMoveEvent(self, event):
        """Aggiorna il rubber-band durante il trascinamento."""
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
        """Ridisegna il rubber-band con i quattro vertici del rettangolo corrente."""
        if self._start_point is None or self._end_point is None:
            return
        self._rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        rect = self._build_rectangle()
        if rect:
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
        """Azzera lo stato interno e pulisce il rubber-band."""
        self._start_point = None
        self._end_point = None
        self._is_drawing = False
        self._rubber_band.reset()

    def deactivate(self):
        """Chiamata da QGIS alla disattivazione: pulisce e delega al parent."""
        self._reset()
        super().deactivate()