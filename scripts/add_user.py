"""Create a user entry for hosted mode. Prints a line to add to PLUSFACTOR_USERS (separate entries with ';').
Usage: python3 scripts/add_user.py someone@firm.com"""
import getpass, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.hosting import hash_password

email = (sys.argv[1] if len(sys.argv) > 1 else input("Email: ")).strip().lower()
pw = getpass.getpass("Password (12+ characters): ")
if len(pw) < 12 or pw != getpass.getpass("Repeat: "):
    sys.exit("Passwords must match and be at least 12 characters.")
print(f"{email}:{hash_password(pw)}")
