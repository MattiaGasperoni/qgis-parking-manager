# QGIS Parking Manager

A custom **QGIS Desktop plugin** built with **PyQGIS** and **Qt** for loading, visualizing, and interactively managing geospatial parking infrastructure datasets directly within the QGIS map canvas. Developed as a university project for the **Geomatics** course at the **University of Urbino**.

---

## Table of Contents
- [Overview](#overview)
- [Architecture & Key Modules](#architecture--key-modules)
- [Features](#features)
- [Project Structure](#project-structure)
- [Installation](#installation)
  - [Method 1: Manual Installation in QGIS Profile](#method-1-manual-installation-in-qgis-profile)
  - [Method 2: Install from ZIP](#method-2-install-from-zip)
- [Usage](#usage)

---

## Overview

**QGIS Parking Manager** extends QGIS with a dedicated dockable control panel and custom interactive map tools tailored for urban parking data workflows. It streamlines the lifecycle of parking vector layers—from automated layer ingestion and spatial extent selection to feature-level creation, attribute updates, and deletion.

---

## Architecture & Key Modules

The plugin follows standard QGIS plugin architecture (`classFactory` entry point in `__init__.py`) and separates UI components, layer management, and canvas interaction into modular Python files:

* **`parking_plugin.py`**: Core plugin lifecycle controller (`initGui`, `unload`), registering toolbar actions, menu entries, and initializing the dock widget.
* **`parking_dock.py`**: Main `QDockWidget` interface providing controls for layer selection, attribute inspection, filtering, and triggering spatial editing workflows.
* **`layer_loader.py`**: Handles loading, validating, and styling geospatial parking layers (e.g., GeoJSON / vector sources) into the active `QgsProject`.
* **`add_remove_tools.py`**: Implements interactive feature creation, modification, and deletion logic synchronized with QGIS edit buffers and attribute schemas.
* **`map_tool_extent.py`**: Custom `QgsMapTool` subclass enabling users to draw and capture bounding boxes / spatial extents directly on the map canvas.
* **`metadata.txt`**: Standard QGIS plugin manifest defining plugin name, version, minimum QGIS compatibility, and entry metadata.

---

## Features

* **Dockable Workspace (`QDockWidget`)**: Integrates natively into the QGIS interface without obstructing the map canvas.
* **Streamlined Layer Ingestion**: Loads and configures parking vector layers with structured schemas and symbology.
* **Interactive Feature Editing**: Dedicated tools to add new parking spots/areas or remove existing features directly from the map.
* **Canvas Extent Selection Tool**: Custom map tool allowing rubber-band bounding box selection on the canvas for spatial filtering and localized operations.

---

## Project Structure

```text
qgis-parking-manager/
├── __init__.py             # QGIS plugin entry point (classFactory)
├── metadata.txt            # QGIS plugin metadata and version manifest
├── icon.png                # Toolbar and plugin manager icon
├── parking_plugin.py       # Plugin lifecycle, toolbar, and menu integration
├── parking_dock.py         # Dockable UI panel and user interaction logic
├── layer_loader.py         # Vector/GeoJSON layer loading and validation
├── add_remove_tools.py     # Feature addition and removal operations
└── map_tool_extent.py      # Custom QgsMapTool for interactive extent selection
```

---

## Installation

### Prerequisites
- **QGIS 3.x** (tested with Python 3.12 runtime environment)

### Method 1: Manual Installation in QGIS Profile

1. Locate your active QGIS user plugins directory:
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows**: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
2. Clone this repository into that folder:
   ```bash
   git clone https://github.com/mattiagasperoni/qgis-parking-manager.git
   ```
3. Restart QGIS, open **Plugins → Manage and Install Plugins...**, navigate to **Installed**, and enable **QGIS Parking Manager**.

### Method 2: Install from ZIP

1. Download the repository as a `.zip` archive (or zip the root folder).
2. In QGIS, open **Plugins → Manage and Install Plugins... → Install from ZIP**.
3. Select the `.zip` archive and click **Install Plugin**.

---

## Usage

1. Click the **Parking Manager** icon in the QGIS toolbar (or access it via the **Plugins** menu) to open the dockable panel.
2. Load a parking dataset via the layer loader controls.
3. Use the extent selection tool to define an area of interest on the map canvas, or toggle the add/remove tools to interactively edit parking features.
