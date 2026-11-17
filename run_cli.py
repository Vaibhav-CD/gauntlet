"""
Launcher for System Kernel Interactive Developer CLI.
"""

import sys
from cli.main import run_cli

if __name__ == "__main__":
    project_root = sys.argv[1] if len(sys.argv) > 1 else "."
    run_cli(project_root)
