import uvicorn
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

if __name__ == "__main__":
    from core.config import config
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.PORT,
        reload=config.DEBUG,
        app_dir="src"
    )