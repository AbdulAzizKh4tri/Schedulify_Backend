import subprocess
import sys
import os
import venv

# Config
venv_dir = "venv"  # virtual environment folder
requirements_file = "requirements.txt"
fixture_file = "IEP_357.json"  # change if needed
reset_flag = "--reset" in sys.argv
no_venv = "--novenv" in sys.argv
no_req = "--noreq" in sys.argv

# Step 0: Create virtual environment if it doesn't exist
if not no_venv:
    if not os.path.exists(venv_dir):
        print("Creating virtual environment...")
        venv.create(venv_dir, with_pip=True)

    # Determine the python executable inside the venv
    if os.name == "nt":  # Windows
        python_exe = os.path.join(venv_dir, "Scripts", "python.exe")
    else:  # macOS/Linux
        python_exe = os.path.join(venv_dir, "bin", "python")

# Step 0b: Install requirements
if not no_req:
    if os.path.exists(requirements_file):
        print("Installing dependencies...")
        subprocess.run([python_exe, "-m", "pip", "install", "-r", requirements_file], check=True)

# Step 1: Make migrations
subprocess.run([python_exe, "manage.py", "makemigrations"], check=True)

# Step 2: Apply migrations
subprocess.run([python_exe, "manage.py", "migrate"], check=True)

# Step 3: Optional reset
if reset_flag:
    subprocess.run([python_exe, "manage.py", "flush", "--no-input"], check=True)
    if os.path.exists(fixture_file):
        subprocess.run([python_exe, "manage.py", "loaddata", fixture_file], check=True)

# Step 4: Run development server
subprocess.run([python_exe, "manage.py", "runserver", "0.0.0.0:8000"], check=True)
