import os
import sys
import subprocess


def install_dependencies():
    print("CivBro: Installing Python dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "gradio"],
                              stdout=sys.stdout, stderr=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"CivBro: pip install warning: {e}")


if __name__ == "__main__":
    install_dependencies()
