# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
hiddenimports += collect_submodules('app')
hiddenimports += collect_submodules('pdfplumber')
hiddenimports += collect_submodules('pdfminer')
hiddenimports += collect_submodules('openpyxl')
hiddenimports += collect_submodules('pandas')
hiddenimports += collect_submodules('PIL')
hiddenimports += collect_submodules('pydantic')
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# OCR de VICTORIA ART: pypdfium2 trae un binario nativo (pdfium), y openai
# necesita el CA bundle de certifi para las llamadas HTTPS.
for _pkg in ('pypdfium2', 'openai', 'certifi'):
    _r = collect_all(_pkg)
    datas += _r[0]; binaries += _r[1]; hiddenimports += _r[2]

# Override editable de equivalencias de SECCION (lo consume app/utils/seccion.py
# desde <bundle>/_internal/config/). Incluye, p.ej., LA HOLANDO GENERALES R.C.
# -> RESPONSABILIDAD CIVIL. El cliente puede editarlo sin recompilar.
datas += [('config/equivalencias_seccion.json', 'config')]


a = Analysis(
    ['app\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='ConsolidadorCCTT',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ConsolidadorCCTT',
)
