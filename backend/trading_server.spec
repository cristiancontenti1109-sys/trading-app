# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['server_entry.py'],
    pathex=[str(Path.cwd())],
    binaries=[],
    datas=[
        ('app', 'app'),
    ],
    hiddenimports=[
        # uvicorn internals
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.loops.uvloop',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.protocols.websockets.wsproto_impl',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # SQLAlchemy
        'sqlalchemy.dialects.sqlite',
        'aiosqlite',
        # passlib
        'passlib.handlers.bcrypt',
        'passlib.handlers.sha2_crypt',
        # jose
        'jose',
        'jose.backends',
        # email validation (pydantic dep)
        'email_validator',
        # APScheduler
        'apscheduler.schedulers.asyncio',
        'apscheduler.triggers.interval',
        'apscheduler.triggers.cron',
        # routers / services (make sure they're all pulled in)
        'app.routers.auth',
        'app.routers.watchlist',
        'app.routers.signals',
        'app.routers.instruments',
        'app.routers.trades',
        'app.routers.chat',
        'app.routers.alpaca',
        'app.routers.smc',
        'app.services.market_data',
        'app.services.signal_service',
        'app.services.notification_service',
        'app.websocket.manager',
        # sklearn
        'sklearn',
        'sklearn.utils._cython_blas',
        'sklearn.neighbors.typedefs',
        'sklearn.neighbors.quad_tree',
        'sklearn.tree._utils',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'test',
        'unittest',
        'distutils',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='trading_server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='trading_server',
)
