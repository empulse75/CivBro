import modules.scripts as scripts
import gradio as gr
import os
import sys

# Add extension root to path so we can import from src
extension_dir = os.path.dirname(os.path.dirname(__file__))
if extension_dir not in sys.path:
    sys.path.insert(0, extension_dir)

from src.main_ui import create_ui

def on_ui_tabs():
    interface = create_ui()
    return [(interface, "CivBro", "civbro_tab")]

try:
    from modules import script_callbacks
    script_callbacks.on_ui_tabs(on_ui_tabs)
except ImportError:
    pass
