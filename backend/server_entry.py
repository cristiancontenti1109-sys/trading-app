import os
import sys
import uvicorn

# PyInstaller freezes the module tree; uvicorn can't import 'main' by string
# in the frozen context, so we import the app object directly.
from main import app  # noqa: E402

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8001'))
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='info')
