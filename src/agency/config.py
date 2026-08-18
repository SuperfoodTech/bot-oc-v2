"""
src/agency/config.py
====================
Configuration settings for the Agency Force Close module.
"""

import os

# Source of truth Google Sheet CSV URL for Agency
AGENCY_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vQ3tLKBNXDqRgBw0mNhKZFxgvKx-JoiTDzm_s5Ix1cm7O6HCv4IvExOLR2HSRVaXSsx82V348mcr9X4/"
    "pub?gid=0&single=true&output=csv"
)

# Agency specific Chrome Profile directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AGENCY_CHROME_PROFILE_DIR = os.path.join(PROJECT_ROOT, "secrets", "agency_chrome_profile")
