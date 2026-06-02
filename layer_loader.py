# -*- coding: utf-8 -*-
"""
layer_loader.py — Caricamento e preparazione dei layer da GeoJSON.
Espone parse_geojson, build_memory_layer, apply_fee_symbology,
apply_name_labels e load_geojson_to_layers (funzione di alto livello).
"""

from typing import Tuple, List, Dict, Any

from qgis.core import (
    QgsRuleBasedRenderer,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsFields,
    QgsField,
    QgsProject,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsSymbol,
    QgsFillSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsTextFormat,
    QgsTextBufferSettings,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont

# CRS sorgente dei file GeoJSON (standard RFC 7946)
CRS_SOURCE = "EPSG:4326"
# CRS di destinazione — Monte Mario / Italy Zone 2
CRS_TARGET = "EPSG:3004"


# ===========================================================================
# Costanti di colore per la simbologia 'fee'
# ===========================================================================

# Dizionario: valore fee → (colore_riempimento, colore_bordo, etichetta_legenda)
FEE_STYLE: Dict[str, Tuple[str, str, str]] = {
    "yes":   ("#e74c3c", "#c0392b", "A pagamento (fee=yes)"),
    "no":    ("#27ae60", "#1e8449", "Gratuito (fee=no)"),
    "_cond": ("#f39c12", "#d68910", "Condizionale / Orario"),
    "_none": ("#95a5a6", "#7f8c8d", "Non specificato"),
}
MOTORHOME_COLOR  = "#9b59b6"
MOTORHOME_BORDER = "#7d3c98"


# ===========================================================================
# Parsing del GeoJSON
# ===========================================================================

def parse_geojson(
    filepath: str,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Legge il GeoJSON e suddivide le feature in tre liste:
    punti, poligoni/multipoligoni e altri tipi geometrici.
    """
    import json

    with open(filepath, encoding="utf-8") as fh:
        data = json.load(fh)

    if data.get("type") != "FeatureCollection":
        raise ValueError(
            f"Il file '{filepath}' non è una FeatureCollection GeoJSON valida."
        )

    points: List[Dict] = []
    polygons: List[Dict] = []
    others: List[Dict] = []

    for feat in data.get("features", []):
        geom = feat.get("geometry")
        if geom is None:
            continue
        gtype = geom.get("type", "")
        if gtype == "Point":
            points.append(feat)
        elif gtype in ("Polygon", "MultiPolygon"):
            polygons.append(feat)
        else:
            others.append(feat)

    return points, polygons, others


# ===========================================================================
# Costruzione layer in memoria
# ===========================================================================

def _collect_fields(features: List[Dict]) -> QgsFields:
    """
    Inferisce lo schema dei campi (Int / Double / String) analizzando
    le proprietà di tutte le feature. Garantisce sempre la presenza
    dei campi standard usati dal dialogo di aggiunta parcheggio.
    """
    all_keys: List[str] = []
    seen: set = set()
    for feat in features:
        for k in feat.get("properties", {}).keys():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    # Campi standard sempre presenti nel layer QGIS
    standard_fields = [
        "name", "fee", "capacity", "surface",
        "amenity", "covered", "lit", "access", "motorhome"
    ]
    for sf in standard_fields:
        if sf not in seen:
            all_keys.append(sf)
            seen.add(sf)

    fields = QgsFields()
    for key in all_keys:
        values = [
            feat["properties"].get(key)
            for feat in features
            if feat["properties"].get(key) is not None
        ]
        if not values:
            fields.append(QgsField(key, QVariant.String))
            continue

        # Prova int
        try:
            for v in values:
                int(v)
            fields.append(QgsField(key, QVariant.Int))
            continue
        except (TypeError, ValueError):
            pass

        # Prova double
        try:
            for v in values:
                float(v)
            fields.append(QgsField(key, QVariant.Double))
            continue
        except (TypeError, ValueError):
            pass

        fields.append(QgsField(key, QVariant.String))

    return fields


def extract_features_and_create_layer(
    features: List[Dict],
    layer_name: str,
    geometry_type: str,
    crs: str = "EPSG:4326",
) -> QgsVectorLayer:
    """
    Crea un QgsVectorLayer in memoria popolato con le feature GeoJSON fornite.
    Converte le geometrie in WKT e assegna gli attributi rispettando i tipi inferiti.
    """
    import json

    uri = f"{geometry_type}?crs={crs}"
    layer = QgsVectorLayer(uri, layer_name, "memory")

    if not layer.isValid():
        raise RuntimeError(
            f"Impossibile creare il layer in memoria '{layer_name}'."
        )

    fields = _collect_fields(features)
    provider = layer.dataProvider()
    provider.addAttributes(fields)
    layer.updateFields()

    qgs_features: List[QgsFeature] = []
    for raw_feat in features:
        qf = QgsFeature(layer.fields())

        # Geometria
        geom_dict = raw_feat.get("geometry")
        if geom_dict:
            qf.setGeometry(
                QgsGeometry.fromWkt(
                    _geojson_geom_to_wkt(geom_dict)
                )
            )

        # Attributi
        props = raw_feat.get("properties", {}) or {}
        for field in layer.fields():
            fname = field.name()
            val = props.get(fname)
            if val is None:
                qf.setAttribute(fname, None)
            else:
                try:
                    if field.type() == QVariant.Int:
                        qf.setAttribute(fname, int(val))
                    elif field.type() == QVariant.Double:
                        qf.setAttribute(fname, float(val))
                    else:
                        qf.setAttribute(fname, str(val))
                except (TypeError, ValueError):
                    qf.setAttribute(fname, str(val) if val else None)

        qgs_features.append(qf)

    provider.addFeatures(qgs_features)
    layer.updateExtents()
    return layer


def _geojson_geom_to_wkt(geom_dict: Dict) -> str:
    """Converte un dizionario geometria GeoJSON in stringa WKT."""
    import json
    from qgis.core import QgsGeometry
    geom = QgsGeometry.fromWkt("")
    geom_str = json.dumps(geom_dict)
    return QgsGeometry.fromEWkt(geom_str).asWkt() if False else _json_to_wkt(geom_dict)


def _json_to_wkt(geom_dict: Dict) -> str:
    """
    Converte manualmente geometria GeoJSON in WKT
    per i tipi Point, Polygon e MultiPolygon.
    """
    gtype = geom_dict["type"]
    coords = geom_dict["coordinates"]

    if gtype == "Point":
        return f"POINT ({coords[0]} {coords[1]})"

    elif gtype == "Polygon":
        rings = []
        for ring in coords:
            pts = ", ".join(f"{c[0]} {c[1]}" for c in ring)
            rings.append(f"({pts})")
        return f"POLYGON ({', '.join(rings)})"

    elif gtype == "MultiPolygon":
        polys = []
        for poly in coords:
            rings = []
            for ring in poly:
                pts = ", ".join(f"{c[0]} {c[1]}" for c in ring)
                rings.append(f"({pts})")
            polys.append(f"({', '.join(rings)})")
        return f"MULTIPOLYGON ({', '.join(polys)})"

    else:
        # Fallback per LineString o tipi non gestiti
        flat = ", ".join(f"{c[0]} {c[1]}" for c in coords)
        return f"LINESTRING ({flat})"


# ===========================================================================
# Riproiezione EPSG:4326 → EPSG:3004
# ===========================================================================

def reproject_layer(
    source_layer: QgsVectorLayer,
    target_crs_code: str = CRS_TARGET,
) -> QgsVectorLayer:
    """
    Riproietta source_layer (EPSG:4326) nel CRS indicato e
    restituisce un nuovo layer in memoria con le geometrie trasformate.
    """
    src_crs = QgsCoordinateReferenceSystem(CRS_SOURCE)
    dst_crs = QgsCoordinateReferenceSystem(target_crs_code)

    transform = QgsCoordinateTransform(
        src_crs, dst_crs, QgsProject.instance()
    )

    geom_type_name = QgsWkbTypes.displayString(source_layer.wkbType())
    uri = f"{geom_type_name}?crs={target_crs_code}"
    dest_layer = QgsVectorLayer(uri, source_layer.name(), "memory")

    if not dest_layer.isValid():
        raise RuntimeError(
            f"Impossibile creare il layer riproiettato '{source_layer.name()}' "
            f"in {target_crs_code}."
        )

    provider = dest_layer.dataProvider()
    provider.addAttributes(source_layer.fields())
    dest_layer.updateFields()

    reprojected: List[QgsFeature] = []
    for src_feat in source_layer.getFeatures():
        dst_feat = QgsFeature(dest_layer.fields())
        dst_feat.setAttributes(src_feat.attributes())

        geom = QgsGeometry(src_feat.geometry())
        if not geom.isNull():
            geom.transform(transform)
        dst_feat.setGeometry(geom)

        reprojected.append(dst_feat)

    provider.addFeatures(reprojected)
    dest_layer.updateExtents()
    return dest_layer


# ===========================================================================
# Simbologia categorizzata per 'fee'
# ===========================================================================

def apply_fee_symbology(layer: QgsVectorLayer) -> None:
    """
    Applica una simbologia rule-based al layer in base all'attributo 'fee'
    (camper=viola, pagamento=rosso, gratuito=verde, condizionale=arancione, N/D=grigio).
    """
    is_point = layer.geometryType() == QgsWkbTypes.PointGeometry

    def _make_sym(color, border):
        if is_point:
            return QgsMarkerSymbol.createSimple({
                "name": "circle", "color": color,
                "color_border": border, "size": "3.0", "outline_width": "0.4",
            })
        else:
            return QgsFillSymbol.createSimple({
                "color": color, "color_border": border,
                "width_border": "0.4", "style": "solid",
            })

    root = QgsRuleBasedRenderer.Rule(None)

    # 1. Camper ammessi → viola (priorità massima)
    r_camper = QgsRuleBasedRenderer.Rule(_make_sym("#9b59b6", "#7d3c98"))
    r_camper.setFilterExpression('"motorhome" = \'yes\'')
    r_camper.setLabel("Camper ammessi")
    root.appendChild(r_camper)

    # 2. A pagamento → rosso
    r_yes = QgsRuleBasedRenderer.Rule(_make_sym("#e74c3c", "#c0392b"))
    r_yes.setFilterExpression('"fee" = \'yes\' AND ("motorhome" IS NULL OR "motorhome" != \'yes\')')
    r_yes.setLabel("A pagamento")
    root.appendChild(r_yes)

    # 3. Gratuito → verde
    r_no = QgsRuleBasedRenderer.Rule(_make_sym("#27ae60", "#1e8449"))
    r_no.setFilterExpression('"fee" = \'no\' AND ("motorhome" IS NULL OR "motorhome" != \'yes\')')
    r_no.setLabel("Gratuito")
    root.appendChild(r_no)

    # 4. Condizionale → arancione
    r_cond = QgsRuleBasedRenderer.Rule(_make_sym("#f39c12", "#d68910"))
    r_cond.setFilterExpression(
        '"fee" IS NOT NULL AND "fee" != \'\' AND "fee" != \'yes\' AND "fee" != \'no\' '
        'AND ("motorhome" IS NULL OR "motorhome" != \'yes\')'
    )
    r_cond.setLabel("Condizionale / Orario")
    root.appendChild(r_cond)

    # 5. Non specificato → grigio (ELSE)
    r_none = QgsRuleBasedRenderer.Rule(_make_sym("#95a5a6", "#7f8c8d"))
    r_none.setIsElse(True)
    r_none.setLabel("Non specificato")
    root.appendChild(r_none)

    layer.setRenderer(QgsRuleBasedRenderer(root))
    layer.triggerRepaint()


# ===========================================================================
# Etichette automatiche
# ===========================================================================

def apply_name_labels(layer: QgsVectorLayer) -> None:
    """
    Configura le etichette automatiche sul campo 'name' (Arial 9pt grassetto,
    buffer bianco). Non fa nulla se il campo 'name' è assente nel layer.
    """
    field_names = [f.name() for f in layer.fields()]
    if "name" not in field_names:
        return

    text_format = QgsTextFormat()
    font = QFont("Arial", 9)
    font.setBold(True)
    text_format.setFont(font)
    text_format.setSize(9)
    text_format.setColor(QColor(0, 0, 0))

    buffer_settings = QgsTextBufferSettings()
    buffer_settings.setEnabled(True)
    buffer_settings.setSize(1.0)
    buffer_settings.setColor(QColor(255, 255, 255, 200))
    text_format.setBuffer(buffer_settings)

    label_settings = QgsPalLayerSettings()
    label_settings.fieldName = "name"
    label_settings.isExpression = False
    label_settings.enabled = True
    label_settings.setFormat(text_format)
    label_settings.drawLabels = True

    layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()


# ===========================================================================
# Funzione di alto livello
# ===========================================================================

def load_geojson_to_layers(
    filepath: str,
    target_crs: str = CRS_TARGET,
) -> Tuple[QgsVectorLayer, QgsVectorLayer]:
    """
    Carica un GeoJSON e restituisce (layer_poligoni, layer_punti) in EPSG:3004,
    già stilizzati con simbologia fee e etichette nome.
    """
    points_feat, polygons_feat, _ = parse_geojson(filepath)

    # Layer temporanei in EPSG:4326
    _tmp_poly = extract_features_and_create_layer(
        polygons_feat, layer_name="_tmp_poly", geometry_type="MultiPolygon", crs=CRS_SOURCE,
    )
    _tmp_pts = extract_features_and_create_layer(
        points_feat, layer_name="_tmp_pts", geometry_type="Point", crs=CRS_SOURCE,
    )

    # Riproiezione in EPSG:3004
    layer_poly = reproject_layer(_tmp_poly, target_crs)
    layer_poly.setName("Parcheggi – Poligoni")

    layer_pts = reproject_layer(_tmp_pts, target_crs)
    layer_pts.setName("Parcheggi – Punti")

    del _tmp_poly, _tmp_pts

    # Simbologia ed etichette
    apply_fee_symbology(layer_poly)
    apply_name_labels(layer_poly)

    apply_fee_symbology(layer_pts)
    apply_name_labels(layer_pts)

    return layer_poly, layer_pts