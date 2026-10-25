# Run from the repository root with python -m PyInstaller --noconfirm this-file.spec
a = Analysis(['scripts/entrypoint.py'], pathex=['src'], binaries=[], datas=[],
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='SCUF-Automatic-Mapping',
          debug=False, strip=False, upx=False, console=False)
