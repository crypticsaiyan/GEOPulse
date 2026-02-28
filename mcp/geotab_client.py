"""
GEOPulse Geotab API Client

Wraps the Geotab API for all data-fetching and write-back operations.
Uses python-dotenv for credential management.

Functions:
    authenticate() -> credentials dict
    call(method, params) -> API response
    get_live_positions() -> list of vehicle positions
    get_live_events(from_version) -> exception events + version token
    get_driver_trips(driver_id, days_back) -> trip history
    get_driver_exceptions(driver_id, days_back) -> exception events
    get_active_faults() -> fault codes
    get_all_drivers() -> driver list
    create_group(name, vehicle_ids) -> group id
    create_rule(name, conditions, driver_id) -> rule id
    get_kpi_data(entity, days_back) -> OData KPI data
"""

from dotenv import load_dotenv
import os
import requests
from datetime import datetime, timedelta

load_dotenv()


class GeotabClient:
    """Geotab API client with authentication and data-fetching methods."""

    def __init__(self):
        self.server = os.getenv('GEOTAB_SERVER', 'my.geotab.com')
        self.database = os.getenv('GEOTAB_DATABASE')
        self.username = os.getenv('GEOTAB_USERNAME')
        self.password = os.getenv('GEOTAB_PASSWORD')
        self.url = f"https://{self.server}/apiv1"
        self.credentials = None

    def authenticate(self):
        """Authenticate with Geotab API and store credentials."""
        response = requests.post(self.url, json={
            "method": "Authenticate",
            "params": {
                "database": self.database,
                "userName": self.username,
                "password": self.password
            }
        })
        result = response.json()
        if "result" not in result:
            raise Exception(f"Authentication failed: {result.get('error', result)}")

        self.credentials = result["result"]["credentials"]

        # Handle server redirection
        path = result["result"].get("path", "")
        if path and "." in path and path.lower() != "thisserver":
            self.url = f"https://{path}/apiv1"

        return self.credentials

    def call(self, method, params=None):
        """Make an authenticated API call."""
        if not self.credentials:
            self.authenticate()

        payload = {
            "method": method,
            "params": {
                "credentials": self.credentials,
                **(params or {})
            }
        }
        response = requests.post(self.url, json=payload)
        result = response.json()

        if "error" in result:
            raise Exception(f"API error: {result['error']}")

        return result.get("result")

    def get_live_positions(self):
        """Get live vehicle positions via DeviceStatusInfo."""
        # TODO: Implement - Step 2a
        pass

    def get_live_events(self, from_version=None):
        """Get live exception events via GetFeed."""
        # TODO: Implement - Step 2b
        pass

    def get_driver_trips(self, driver_id, days_back=90):
        """Get per-driver historical trips."""
        # TODO: Implement - Step 2c
        pass

    def get_driver_exceptions(self, driver_id, days_back=90):
        """Get per-driver exception events."""
        # TODO: Implement - Step 2d
        pass

    def get_active_faults(self):
        """Get active fault codes from last 7 days."""
        # TODO: Implement - Step 2e
        pass

    def get_all_drivers(self):
        """Get all drivers (User with isDriver=True)."""
        # TODO: Implement - Step 2f
        pass

    def create_group(self, name, vehicle_ids, parent_id="GroupCompanyId"):
        """Write-back: Create a group in Geotab and assign vehicles."""
        # TODO: Implement - Step 2g
        pass

    def create_rule(self, name, conditions, driver_id):
        """Write-back: Create a coaching alert rule."""
        # TODO: Implement - Step 2h
        pass

    def get_kpi_data(self, entity="VehicleKpi_Daily", days_back=7):
        """Pull OData KPI data from Data Connector."""
        # TODO: Implement - Step 2i
        pass


# Quick test when run directly
if __name__ == "__main__":
    client = GeotabClient()
    try:
        client.authenticate()
        devices = client.call("Get", {"typeName": "Device"})
        print(f"✅ Geotab auth successful! Found {len(devices)} vehicles.")
    except Exception as e:
        print(f"❌ Geotab auth failed: {e}")
