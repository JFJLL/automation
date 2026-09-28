import os
import sys
from pathlib import Path
import uvicorn

if __name__ == "__main__":
    base_dir = Path(__file__).parent.resolve()
    os.chdir(str(base_dir))
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
    parent_dir = str(base_dir.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8092, reload=False)
