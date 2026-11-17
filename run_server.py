"""
Launcher for System Kernel Web IDE Server.
"""

import uvicorn
import os
import sys

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    print(f"Starting System Kernel Web Developer Environment on http://{host}:{port} ...")
    uvicorn.run("server.app:app", host=host, port=port, reload=False)
