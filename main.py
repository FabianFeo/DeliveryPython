import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from citydelivery.presentacion.menu import iniciar_menu_interactivo

if __name__ == "__main__":
    iniciar_menu_interactivo()
