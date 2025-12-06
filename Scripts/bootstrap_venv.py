"""
Bootstrap virtual environment for Scripts tools.
- Creates .venv (if missing)
- Installs requirements from Scripts/requirements.txt
- Prints activation instructions

Run:
  python bootstrap_venv.py
"""

import os
import sys
import subprocess
import venv
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
VENV_DIR = SCRIPTS_DIR / ".venv"
REQ_FILE = SCRIPTS_DIR / "requirements.txt"


def run(cmd, env=None):
	print(f"$ {' '.join(cmd)}")
	subprocess.check_call(cmd, env=env)


def ensure_venv():
	if VENV_DIR.exists():
		print(f"Using existing venv: {VENV_DIR}")
		return
	print(f"Creating venv at: {VENV_DIR}")
	venv.EnvBuilder(with_pip=True, clear=False).create(VENV_DIR)


def pip_install():
	if not REQ_FILE.exists():
		raise FileNotFoundError(f"Missing requirements file: {REQ_FILE}")
	python_exe = VENV_DIR / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
	run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
	run([str(python_exe), "-m", "pip", "install", "-r", str(REQ_FILE)])


def print_activate_help():
	if os.name == "nt":
		act = VENV_DIR / "Scripts" / "activate"
		print(f"Activate: {act}")
		print(f"PowerShell: {VENV_DIR / 'Scripts' / 'Activate.ps1'}")
	else:
		print(f"source {VENV_DIR}/bin/activate")


def main():
	ensure_venv()
	pip_install()
	print("Venv ready.")
	print_activate_help()


if __name__ == "__main__":
	main()
