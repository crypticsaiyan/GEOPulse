#!/usr/bin/env python3
"""
GEOPulse — Connection Test Script

Verifies all external service connections:
1. Geotab API auth → returns vehicle count
2. Google Gemini API → sends test prompt
3. Google Maps API → geocodes test address
4. DuckDB → creates table, inserts, queries

Run: python tests/test_connection.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

PASS = "✅"
FAIL = "❌"
SKIP = "⏭️"


def test_geotab():
    """Test 1: Geotab API Authentication"""
    print("\n" + "=" * 50)
    print("TEST 1: Geotab API Authentication")
    print("=" * 50)

    database = os.getenv("GEOTAB_DATABASE")
    username = os.getenv("GEOTAB_USERNAME")
    password = os.getenv("GEOTAB_PASSWORD")
    server = os.getenv("GEOTAB_SERVER", "my.geotab.com")

    if not all([database, username, password]):
        print(f"{SKIP} Skipped — GEOTAB_DATABASE, GEOTAB_USERNAME, or GEOTAB_PASSWORD not set in .env")
        return False

    try:
        import requests

        url = f"https://{server}/apiv1"
        auth_response = requests.post(url, json={
            "method": "Authenticate",
            "params": {
                "database": database,
                "userName": username,
                "password": password
            }
        }, timeout=15)

        result = auth_response.json()
        if "error" in result:
            print(f"{FAIL} Auth failed: {result['error']}")
            return False

        credentials = result["result"]["credentials"]

        # Handle server redirection
        path = result["result"].get("path", "")
        if path and "." in path and path.lower() != "thisserver":
            url = f"https://{path}/apiv1"

        # Get vehicle count
        device_response = requests.post(url, json={
            "method": "Get",
            "params": {
                "typeName": "Device",
                "credentials": credentials
            }
        }, timeout=15)

        devices = device_response.json().get("result", [])
        print(f"{PASS} Geotab auth successful!")
        print(f"   Database: {database}")
        print(f"   Server: {server}")
        print(f"   Vehicles found: {len(devices)}")
        return True

    except Exception as e:
        print(f"{FAIL} Geotab connection failed: {e}")
        return False


def test_gemini():
    """Test 2: Google Gemini API"""
    print("\n" + "=" * 50)
    print("TEST 2: Google Gemini API")
    print("=" * 50)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(f"{SKIP} Skipped — GEMINI_API_KEY not set in .env")
        return False

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content("Say 'GEOPulse connection test successful' in exactly those words.")

        print(f"{PASS} Gemini API connected!")
        print(f"   Model: gemini-2.0-flash")
        print(f"   Response: {response.text[:100]}...")
        return True

    except Exception as e:
        print(f"{FAIL} Gemini API failed: {e}")
        return False


def test_google_maps():
    """Test 3: Google Maps API"""
    print("\n" + "=" * 50)
    print("TEST 3: Google Maps Geocoding API")
    print("=" * 50)

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print(f"{SKIP} Skipped — GOOGLE_MAPS_API_KEY not set in .env")
        return False

    try:
        import requests

        response = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={
                "address": "Geotab Inc, Oakville, Ontario, Canada",
                "key": api_key
            },
            timeout=10
        )

        data = response.json()
        if data.get("status") == "OK":
            location = data["results"][0]["geometry"]["location"]
            print(f"{PASS} Google Maps API connected!")
            print(f"   Test geocode: Geotab HQ")
            print(f"   Lat: {location['lat']}, Lng: {location['lng']}")
            return True
        else:
            print(f"{FAIL} Maps API error: {data.get('status')} — {data.get('error_message', 'No details')}")
            return False

    except Exception as e:
        print(f"{FAIL} Google Maps failed: {e}")
        return False


def test_duckdb():
    """Test 4: DuckDB Local Database"""
    print("\n" + "=" * 50)
    print("TEST 4: DuckDB Local Database")
    print("=" * 50)

    try:
        import duckdb

        # Use temp path for test
        conn = duckdb.connect(":memory:")

        # Create test table
        conn.execute("""
            CREATE TABLE test_fleet (
                vehicle_id VARCHAR,
                driver_name VARCHAR,
                deviation_score DOUBLE
            )
        """)

        # Insert test data
        conn.execute("""
            INSERT INTO test_fleet VALUES
            ('V001', 'Marcus', 23.5),
            ('V002', 'Elena', 87.2),
            ('V003', 'James', 45.0)
        """)

        # Query
        result = conn.execute("SELECT * FROM test_fleet ORDER BY deviation_score DESC").fetchall()

        conn.close()

        print(f"{PASS} DuckDB initialized successfully!")
        print(f"   Version: {duckdb.__version__}")
        print(f"   Test query returned {len(result)} rows")
        print(f"   Sample: {result[0][1]} — deviation score {result[0][2]}")
        return True

    except Exception as e:
        print(f"{FAIL} DuckDB failed: {e}")
        return False


if __name__ == "__main__":
    print("🚀 GEOPulse Connection Test Suite")
    print("=" * 50)

    results = {
        "Geotab API": test_geotab(),
        "Gemini API": test_gemini(),
        "Google Maps": test_google_maps(),
        "DuckDB": test_duckdb(),
    }

    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for name, passed in results.items():
        icon = PASS if passed else FAIL
        print(f"  {icon} {name}")

    passed_count = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n  {passed_count}/{total} tests passed")

    if passed_count == total:
        print("\n🎉 All systems go! GEOPulse is ready to build.")
    else:
        print("\n⚠️  Some tests failed. Fill in missing credentials in .env and re-run.")
