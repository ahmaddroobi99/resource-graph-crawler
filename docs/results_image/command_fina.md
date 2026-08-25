cd "C:\Users\ahmad\OneDrive\Desktop\POP"

# Activate (if not already)
.venv\Scripts\activate

# Run tests
python -m pytest -q

# Run the crawler (gets the 6 passwords)
python main.py

# Unlock the 7th (once you have a German exit)
python scripts\fetch_geo.py --proxy socks5h://YOUR_GERMAN_PROXY:PORT
# or
python main.py --proxy socks5h://YOUR_GERMAN_PROXY:PORT