# -*- coding: utf-8 -*-
"""
layer_loader.py
---------------
Funzioni di utilità per il caricamento e la preparazione dei layer
a partire da un file GeoJSON di parcheggi.

Responsabilità:
  - parse_geojson()          → separa feature per tipo geometria
  - build_memory_layer()     → crea un QgsVectorLayer in memoria
  - apply_fee_symbology()    → simbologia categorizzata sull'attributo 'fee'
  - apply_name_labels()      → etichette automatiche con il campo 'name'
  - load_geojson_to_layers() → funzione di alto livello che orchestra tutto
"""

from typing import Tuple, List, Dict, Any

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsFields,
    QgsField,
    QgsProject,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    # Simbologia
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsSymbol,
    QgsFillSymbol,
    QgsMarkerSymbol,
    # Etichette
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsTextFormat,
    QgsTextBufferSettings,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont

# CRS sorgente dei file GeoJSON (standard RFC 7946)
CRS_SOURCE = "EPSG:4326"
# CRS di destinazione richiesto dal corso — Monte Mario / Italy Zone 2
CRS_TARGET = "EPSG:3004"


# ===========================================================================
# Costanti di colore per la simbologia 'fee'
# ===========================================================================

# Dizionario: valore fee → (colore_riempimento, colore_bordo, etichetta_legenda)
FEE_STYLE: Dict[str, Tuple[str, str, str]] = {
    "yes":   ("#e74c3c", "#c0392b", "A pagamento (fee=yes)"),
    "no":    ("#27ae60", "#1e8449", "Gratuito (fee=no)"),
    # Valori condizionali (orari) → arancione
    "_cond": ("#f39c12", "#d68910", "Condizionale / Orario"),
    # Nessun valore specificato → grigio
    "_none": ("#95a5a6", "#7f8c8d", "Non specificato"),
}


# ===========================================================================
# Parsing del GeoJSON
# ===========================================================================

def parse_geojson(
    filepath: str,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Legge un file GeoJSON e suddivide le feature per tipo geometrico.

    Restituisce tre liste di dizionari GeoJSON feature:
      - ``points``   : Point (singolo punto — ingressi, stalli)
      - ``polygons`` : Polygon e MultiPolygon (aree parcheggio)
      - ``others``   : LineString e altri tipi non gestiti

    :param filepath: Percorso assoluto al file .geojson
    :raises FileNotFoundError: se il file non esiste
    :raises ValueError:        se il JSON non è una FeatureCollection valida
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
    Analizza le proprietà di tutte le feature e costruisce uno schema
    di campi QgsFields con i tipi più appropriati.

    Regole di tipo inferenza:
      - Se tutti i valori non-nulli sono interi → QVariant.Int
      - Se tutti sono numerici (float) → QVariant.Double
      - Altrimenti → QVariant.String
    """
    # Raccoglie tutti i nomi dei campi presenti nel dataset
    all_keys: List[str] = []
    seen: set = set()
    for feat in features:
        for k in feat.get("properties", {}).keys():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    # Inferisce il tipo per ogni campo
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

        # Default: stringa
        fields.append(QgsField(key, QVariant.String))

    return fields


def build_memory_layer(
    features: List[Dict],
    layer_name: str,
    geometry_type: str,
    crs: str = "EPSG:4326",
) -> QgsVectorLayer:
    """
    Crea un QgsVectorLayer in memoria a partire da una lista di
    feature GeoJSON dizionario.

    :param features:      Lista di dizionari feature GeoJSON
    :param layer_name:    Nome visualizzato nel pannello layer di QGIS
    :param geometry_type: Tipo geometria per la URI ("Point", "Polygon",
                          "MultiPolygon", …)
    :param crs:           Codice EPSG del sistema di riferimento
    :returns:             Layer vettoriale in memoria, già popolato
    :raises RuntimeError: se il layer non viene creato correttamente
    """
    import json

    # Usa MultiPolygon per accogliere sia Polygon che MultiPolygon
    uri = f"{geometry_type}?crs={crs}"
    layer = QgsVectorLayer(uri, layer_name, "memory")

    if not layer.isValid():
        raise RuntimeError(
            f"Impossibile creare il layer in memoria '{layer_name}'."
        )

    # --- Schema dei campi ---
    fields = _collect_fields(features)
    provider = layer.dataProvider()
    provider.addAttributes(fields)
    layer.updateFields()

    # --- Aggiunge le feature ---
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
                # Conversione al tipo dichiarato del campo
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
    """
    Converte un dizionario geometria GeoJSON in una stringa WKT.
    Usa QgsGeometry.fromEWkt() indirettamente tramite json→QgsGeometry.

    Nota: QgsGeometry.fromWkt() non accetta GeoJSON direttamente;
    si usa il percorso JSON→QgsGeometry.asWkt().
    """
    import json
    from qgis.core import QgsGeometry
    geom = QgsGeometry.fromWkt("")
    # fromEWkt non esiste in tutte le versioni; usiamo fromWkt con conversione
    # intermedia tramite il metodo ufficiale asGeometry da stringa JSON
    geom_str = json.dumps(geom_dict)
    return QgsGeometry.fromEWkt(geom_str).asWkt() if False else _json_to_wkt(geom_dict)


def _json_to_wkt(geom_dict: Dict) -> str:
    """
    Converte geometria GeoJSON in WKT manualmente per i tipi usati
    nel dataset parcheggi (Point, Polygon, MultiPolygon).
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
        # Fallback per LineString o altri tipi presenti nel dataset
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
    Riproietta tutte le geometrie di ``source_layer`` nel sistema di
    riferimento indicato da ``target_crs_code`` e restituisce un nuovo
    QgsVectorLayer in memoria con il CRS corretto.

    Il layer sorgente deve essere in ``EPSG:4326`` (lat/lon WGS84),
    come da specifica GeoJSON RFC 7946.  Il target default è
    ``EPSG:3004`` (Monte Mario / Italy Zone 2), obbligatorio per
    lavori tecnici sull'Italia centro-orientale (Marche).

    La trasformazione usa il datum shift ufficiale NTv2 se disponibile
    nell'installazione QGIS/PROJ; in caso contrario PROJ applica il
    Molodensky standard (errore < 1 m, accettabile per dati OSM).

    :param source_layer:    Layer in memoria in EPSG:4326
    :param target_crs_code: Codice EPSG di destinazione (default EPSG:3004)
    :returns:               Nuovo layer in memoria nel CRS di destinazione
    :raises RuntimeError:   Se la creazione del layer destinazione fallisce
    """
    src_crs = QgsCoordinateReferenceSystem(CRS_SOURCE)
    dst_crs = QgsCoordinateReferenceSystem(target_crs_code)

    # Oggetto di trasformazione (usa il contesto del progetto corrente
    # per applicare eventuali datum shift configurati dall'utente)
    transform = QgsCoordinateTransform(
        src_crs, dst_crs, QgsProject.instance()
    )

    # Determina il tipo geometrico WKB per la URI del nuovo layer
    geom_type_name = QgsWkbTypes.displayString(
        source_layer.wkbType()
    )

    uri = f"{geom_type_name}?crs={target_crs_code}"
    dest_layer = QgsVectorLayer(uri, source_layer.name(), "memory")

    if not dest_layer.isValid():
        raise RuntimeError(
            f"Impossibile creare il layer riproiettato '{source_layer.name()}' "
            f"in {target_crs_code}."
        )

    # Copia lo schema dei campi sorgente nel layer destinazione
    provider = dest_layer.dataProvider()
    provider.addAttributes(source_layer.fields())
    dest_layer.updateFields()

    # Riproietta e copia ogni feature
    reprojected: List[QgsFeature] = []
    for src_feat in source_layer.getFeatures():
        dst_feat = QgsFeature(dest_layer.fields())

        # Copia attributi invariati
        dst_feat.setAttributes(src_feat.attributes())

        # Riproietta la geometria
        geom = QgsGeometry(src_feat.geometry())   # copia esplicita
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
    Applica al layer poligonale una simbologia categorizzata basata
    sul campo ``fee``.

    Classi:
      - ``yes``       → rosso    (#e74c3c)
      - ``no``        → verde    (#27ae60)
      - valori orario → arancione(#f39c12)
      - vuoto/None    → grigio   (#95a5a6)

    :param layer: Layer vettoriale poligonale già caricato.
    """
    if "fee" not in [f.name() for f in layer.fields()]:
        return  # Campo assente: nessuna simbologia

    # Raccoglie i valori distinti di 'fee' presenti nel layer
    fee_values = set()
    for feat in layer.getFeatures():
        val = feat["fee"]
        if val and str(val).strip():
            fee_values.add(str(val).strip())

    categories: List[QgsRendererCategory] = []

    for val in sorted(fee_values):
        val_lower = val.lower()

        if val_lower == "yes":
            style_key = "yes"
        elif val_lower == "no":
            style_key = "no"
        else:
            # Qualsiasi valore condizionale (orari, "Private", ecc.)
            style_key = "_cond"

        color_hex, border_hex, label = FEE_STYLE[style_key]

        sym = QgsFillSymbol.createSimple({
            "color":         color_hex,
            "color_border":  border_hex,
            "width_border":  "0.4",
            "style":         "solid",
        })

        # Etichetta nella legenda: valore originale + descrizione
        legend_label = f"{val} — {label.split('(')[0].strip()}"
        categories.append(QgsRendererCategory(val, sym, legend_label))

    # Categoria per valori nulli / non specificati
    null_color, null_border, null_label = FEE_STYLE["_none"]
    null_sym = QgsFillSymbol.createSimple({
        "color":        null_color,
        "color_border": null_border,
        "width_border": "0.3",
        "style":        "solid",
    })
    categories.append(
        QgsRendererCategory("", null_sym, null_label)
    )

    renderer = QgsCategorizedSymbolRenderer("fee", categories)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


# ===========================================================================
# Simbologia layer punti
# ===========================================================================

def apply_point_symbology(layer: QgsVectorLayer) -> None:
    """
    Applica al layer puntuale una simbologia semplice con cerchio blu
    per rappresentare gli ingressi/stalli.

    :param layer: Layer vettoriale puntuale.
    """
    sym = QgsMarkerSymbol.createSimple({
        "name":          "circle",
        "color":         "#2980b9",
        "color_border":  "#1a5276",
        "size":          "3.0",
        "outline_width": "0.4",
    })
    layer.renderer().setSymbol(sym)
    layer.triggerRepaint()


# ===========================================================================
# Etichette automatiche
# ===========================================================================

def apply_name_labels(layer: QgsVectorLayer) -> None:
    """
    Configura le etichette automatiche usando il campo ``name``.

    Impostazioni:
      - Testo: nero, grassetto, 9pt
      - Buffer: bianco semitrasparente per leggibilità su sfondo qualsiasi
      - Posizionamento: centroide (Over Point / Over Polygon)

    Se il campo ``name`` non esiste nel layer, la funzione ritorna
    silenziosamente senza applicare alcuna etichetta.

    :param layer: Layer vettoriale (punti o poligoni).
    """
    field_names = [f.name() for f in layer.fields()]
    if "name" not in field_names:
        return

    # --- Formato testo ---
    text_format = QgsTextFormat()
    font = QFont("Arial", 9)
    font.setBold(True)
    text_format.setFont(font)
    text_format.setSize(9)
    text_format.setColor(QColor(0, 0, 0))

    # --- Buffer (alone bianco) ---
    buffer_settings = QgsTextBufferSettings()
    buffer_settings.setEnabled(True)
    buffer_settings.setSize(1.0)
    buffer_settings.setColor(QColor(255, 255, 255, 200))
    text_format.setBuffer(buffer_settings)

    # --- Impostazioni di posizionamento ---
    label_settings = QgsPalLayerSettings()
    label_settings.fieldName = "name"
    label_settings.isExpression = False
    label_settings.enabled = True
    label_settings.setFormat(text_format)

    # Attiva l'etichettatura solo sulle feature con 'name' compilato
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
    Funzione principale: carica un GeoJSON di parcheggi e restituisce
    due layer in memoria **riproiettati in EPSG:3004**, già stilizzati
    e pronti per essere aggiunti al progetto QGIS.

    Passi eseguiti:
      1. Parsing del GeoJSON e separazione per tipo geometria
      2. Creazione layer temporanei in EPSG:4326 (CRS nativo GeoJSON)
      3. Riproiezione in ``target_crs`` (default EPSG:3004)
      4. Simbologia categorizzata 'fee' sul layer poligoni
      5. Simbologia semplice sul layer punti
      6. Etichette 'name' su entrambi i layer

    :param filepath:   Percorso assoluto al file .geojson
    :param target_crs: CRS di destinazione (default ``EPSG:3004``)
    :returns:          Coppia (layer_poligoni, layer_punti) in EPSG:3004
    :raises:           FileNotFoundError, ValueError, RuntimeError
    """
    points_feat, polygons_feat, _ = parse_geojson(filepath)

    # ---- Step 1: layer temporanei in EPSG:4326 (coord lon/lat del GeoJSON) ----
    _tmp_poly = build_memory_layer(
        polygons_feat,
        layer_name="_tmp_poly",
        geometry_type="MultiPolygon",
        crs=CRS_SOURCE,
    )
    _tmp_pts = build_memory_layer(
        points_feat,
        layer_name="_tmp_pts",
        geometry_type="Point",
        crs=CRS_SOURCE,
    )

    # ---- Step 2: riproiezione in EPSG:3004 ----
    layer_poly = reproject_layer(_tmp_poly, target_crs)
    layer_poly.setName("Parcheggi – Aree (Poligoni) [EPSG:3004]")

    layer_pts = reproject_layer(_tmp_pts, target_crs)
    layer_pts.setName("Parcheggi – Stalli/Ingressi (Punti) [EPSG:3004]")

    # I layer temporanei non servono più
    del _tmp_poly, _tmp_pts

    # ---- Step 3: simbologia ed etichette sui layer riproiettati ----
    apply_fee_symbology(layer_poly)
    apply_name_labels(layer_poly)

    apply_point_symbology(layer_pts)
    apply_name_labels(layer_pts)

    return layer_poly, layer_pts
