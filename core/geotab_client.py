"""
GEOPulse Geotab API Client — Full Implementation

Wraps the Geotab API for all data-fetching and write-back operations.
Uses DuckDB caching to minimize API calls.

Functions:
    authenticate() -> credentials dict
    call(method, params) -> API response
    get_live_positions() -> vehicle positions (cached 10s)
    get_live_events(from_version) -> exception events (no cache)
    get_driver_trips(driver_id, days_back) -> trip history (cached 1hr)
    get_driver_exceptions(driver_id, days_back) -> exceptions (cached 1hr)
    get_all_drivers() -> driver list (cached 10min)
    get_all_devices() -> device list (cached 10min)
    create_group(name, vehicle_ids) -> group id
    create_rule(name, conditions, driver_id) -> rule id
    get_kpi_data(entity, days_back) -> OData KPI data (cached 1hr)
"""

from dotenv import load_dotenv
import os
import json
import hashlib
import logging
import requests
from datetime import datetime, timedelta, timezone

load_dotenv()

logger = logging.getLogger(__name__)


class GeotabClient:
    """Geotab API client with authentication, data-fetching, and caching."""

    def __init__(self, db_cache=None):
        self.server = os.getenv("GEOTAB_SERVER", "my.geotab.com")
        self.database = os.getenv("GEOTAB_DATABASE")
        self.username = os.getenv("GEOTAB_USERNAME")
        self.password = os.getenv("GEOTAB_PASSWORD")
        self.url = f"https://{self.server}/apiv1"
        self.credentials = None
        self.cache = db_cache  # Optional DuckDBCache for response caching
        self._device_map = None  # Lazy device name lookup
        self._driver_map = None  # Lazy driver name lookup
        self._rule_map = None    # Lazy rule name lookup
        self._event_version = None  # GetFeed version token

    def authenticate(self):
        """Authenticate with Geotab API and store credentials."""
        response = requests.post(self.url, json={
            "method": "Authenticate",
            "params": {
                "database": self.database,
                "userName": self.username,
                "password": self.password
            }
        }, timeout=15)
        result = response.json()
        if "result" not in result:
            raise Exception(f"Authentication failed: {result.get('error', result)}")

        self.credentials = result["result"]["credentials"]

        # Handle server redirection
        path = result["result"].get("path", "")
        if path and "." in path and path.lower() != "thisserver":
            self.url = f"https://{path}/apiv1"
            self.server = path

        logger.info(f"Authenticated to {self.database} on {self.server}")
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
        response = requests.post(self.url, json=payload, timeout=30)
        result = response.json()

        if "error" in result:
            raise Exception(f"API error: {result['error']}")

        return result.get("result")

    def _cached_call(self, cache_key, ttl_seconds, method, params=None):
        """Make a cached API call. Returns cached response if fresh."""
        if self.cache:
            params_hash = hashlib.sha256(json.dumps(params or {}, sort_keys=True).encode()).hexdigest()[:16]
            cached = self.cache.get_api_cache(cache_key, params_hash, ttl_seconds)
            if cached:
                logger.debug(f"Cache hit: {cache_key}")
                return cached

        result = self.call(method, params)

        if self.cache and result:
            params_hash = hashlib.sha256(json.dumps(params or {}, sort_keys=True).encode()).hexdigest()[:16]
            self.cache.set_api_cache(cache_key, params_hash, result, ttl_seconds)

        return result

    # === Lookup Maps (built once, cached in memory) ===

    def _build_device_map(self):
        """Build device_id -> device_name lookup."""
        if self._device_map is None:
            devices = self.get_all_devices()
            self._device_map = {d["id"]: d["name"] for d in devices}
        return self._device_map

    def _build_driver_map(self):
        """Build driver_id -> driver_name lookup."""
        if self._driver_map is None:
            drivers = self.get_all_drivers()
            self._driver_map = {}
            for d in drivers:
                name = d.get("name", "")
                first = d.get("firstName", "")
                last = d.get("lastName", "")
                display = f"{first} {last}".strip() if (first or last) else name
                self._driver_map[d["id"]] = display
        return self._driver_map

    def _build_rule_map(self):
        """Build rule_id -> rule_name lookup."""
        if self._rule_map is None:
            rules = self._cached_call("rules", 600, "Get", {"typeName": "Rule"})
            self._rule_map = {r["id"]: r.get("name", "Unknown Rule") for r in (rules or [])}
        return self._rule_map

    # === Data-Fetching Methods ===

    def get_live_positions(self):
        """Get live vehicle positions via DeviceStatusInfo. Cached 10s."""
        statuses = self._cached_call("live_positions", 10, "Get", {"typeName": "DeviceStatusInfo"})
        device_map = self._build_device_map()

        positions = []
        for s in (statuses or []):
            device_id = s.get("device", {}).get("id", "")
            positions.append({
                "device_id": device_id,
                "device_name": device_map.get(device_id, "Unknown"),
                "latitude": s.get("latitude", 0),
                "longitude": s.get("longitude", 0),
                "speed": s.get("speed", 0),
                "bearing": s.get("bearing", 0),
                "is_driving": s.get("isDriving", False),
                "last_communication": str(s.get("dateTime", "")),
            })
        return positions

    def get_live_events(self, from_version=None):
        """Get live exception events via GetFeed. NOT cached (streaming)."""
        version = from_version or self._event_version

        params = {"typeName": "ExceptionEvent"}
        if version:
            params["fromVersion"] = version
        else:
            # First call: get recent events — use 7 days so demo DBs show variety
            params["resultsLimit"] = 200

        try:
            if version:
                result = self.call("GetFeed", params)
                events = result.get("data", []) if isinstance(result, dict) else result
                new_version = result.get("toVersion") if isinstance(result, dict) else None
            else:
                # Initial load: use Get with 7-day date filter for variety
                now = datetime.now(timezone.utc)
                params["search"] = {"fromDate": (now - timedelta(days=7)).isoformat()}
                events = self.call("Get", params)
                # Bootstrap a GetFeed version token so subsequent polls only return new events
                try:
                    feed_result = self.call("GetFeed", {"typeName": "ExceptionEvent", "resultsLimit": 1})
                    if isinstance(feed_result, dict):
                        new_version = feed_result.get("toVersion")
                except Exception:
                    pass
                if not new_version:
                    new_version = None
        except Exception as e:
            logger.warning(f"GetFeed failed, falling back to Get: {e}")
            now = datetime.now(timezone.utc)
            events = self.call("Get", {
                "typeName": "ExceptionEvent",
                "search": {"fromDate": (now - timedelta(days=7)).isoformat()},
                "resultsLimit": 200
            })
            new_version = None

        if new_version:
            self._event_version = new_version

        device_map = self._build_device_map()
        rule_map = self._build_rule_map()
        driver_map = self._build_driver_map()

        formatted = []
        for e in (events or []):
            # Safe reference extraction — handles both dict and string fields
            device_ref = e.get("device", {})
            device_id = device_ref.get("id", "") if isinstance(device_ref, dict) else str(device_ref)

            # rule field: Geotab sometimes returns a plain string ID, not a dict
            rule_ref = e.get("rule", {})
            if isinstance(rule_ref, dict):
                rule_id = rule_ref.get("id", "")
            elif isinstance(rule_ref, str) and rule_ref:
                rule_id = rule_ref
            else:
                rule_id = ""

            driver_ref = e.get("driver", {})
            driver_id = driver_ref.get("id", "") if isinstance(driver_ref, dict) else (
                "" if str(driver_ref) == "UnknownDriverId" else str(driver_ref))

            # Location — ExceptionEvent carries a `location` point (y=lat, x=lon)
            loc = e.get("location", {}) or {}
            lat = loc.get("y") or loc.get("lat") or 0
            lon = loc.get("x") or loc.get("lon") or loc.get("lng") or 0

            # activeFrom can be a datetime object or an ISO string
            active_from_raw = e.get("activeFrom", "")
            if hasattr(active_from_raw, "isoformat"):
                active_from_str = active_from_raw.isoformat()
            else:
                active_from_str = str(active_from_raw)

            active_to_raw = e.get("activeTo", "")
            if hasattr(active_to_raw, "isoformat"):
                active_to_str = active_to_raw.isoformat()
            else:
                active_to_str = str(active_to_raw)

            formatted.append({
                "id": e.get("id", ""),
                "device_id": device_id,
                "device_name": device_map.get(device_id, "Unknown"),
                "rule_id": rule_id,
                "rule_name": rule_map.get(rule_id, "Unknown Rule") if rule_id else "Unknown Rule",
                "driver_id": driver_id,
                "driver_name": driver_map.get(driver_id, ""),
                "active_from": active_from_str,
                "active_to": active_to_str,
                "duration": str(e.get("duration", "")),
                "latitude": lat,
                "longitude": lon,
            })
        return {"events": formatted, "version": new_version or self._event_version}

    def get_driver_trips(self, driver_id, days_back=90):
        """Get per-driver historical trips. Cached 1hr."""
        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(days=days_back)).isoformat()
        to_date = now.isoformat()

        params = {
            "typeName": "Trip",
            "search": {
                "fromDate": from_date,
                "toDate": to_date,
                "userSearch": {"id": driver_id}
            }
        }
        trips = self._cached_call(f"driver_trips_{driver_id}_{days_back}", 3600, "Get", params)

        formatted = []
        for t in (trips or []):
            start = t.get("dateTime", t.get("start", ""))
            stop = t.get("nextTripStart", t.get("stop", ""))
            distance_km = t.get("distance", 0)

            # Parse duration — Geotab returns "HH:MM:SS" or "D.HH:MM:SS" strings
            duration = self._parse_duration(t.get("drivingDuration", 0))
            idle_duration = self._parse_duration(t.get("idlingDuration", 0))

            # Device ID — handle dict or string reference
            device_ref = t.get("device", {})
            device_id = device_ref.get("id", "") if isinstance(device_ref, dict) else str(device_ref)

            # Driver ID — handle dict, string, or "UnknownDriverId"
            driver_ref = t.get("driver", {})
            trip_driver_id = ""
            if isinstance(driver_ref, dict):
                trip_driver_id = driver_ref.get("id", "")
            elif isinstance(driver_ref, str) and driver_ref != "UnknownDriverId":
                trip_driver_id = driver_ref

            formatted.append({
                "trip_id": t.get("id", ""),
                "driver_id": trip_driver_id or driver_id,
                "device_id": device_id,
                "start_time": str(start),
                "stop_time": str(stop),
                "distance": distance_km,  # km
                "max_speed": t.get("maximumSpeed", t.get("maxSpeed", 0)),
                "average_speed": t.get("averageSpeed", 0),
                "duration_seconds": duration,
                "idle_duration_seconds": idle_duration,
                "trip_date": str(start)[:10] if start else "",
            })
        return formatted

    def get_device_trips(self, device_id, days_back=7):
        """Get trips for a specific device/vehicle. Cached 1hr."""
        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(days=days_back)).isoformat()
        to_date = now.isoformat()

        params = {
            "typeName": "Trip",
            "search": {
                "fromDate": from_date,
                "toDate": to_date,
                "deviceSearch": {"id": device_id}
            }
        }
        trips = self._cached_call(f"device_trips_{device_id}_{days_back}", 3600, "Get", params)

        formatted = []
        for t in (trips or []):
            start = t.get("dateTime", t.get("start", ""))
            stop = t.get("nextTripStart", t.get("stop", ""))
            distance_km = t.get("distance", 0)

            duration = self._parse_duration(t.get("drivingDuration", 0))
            idle_duration = self._parse_duration(t.get("idlingDuration", 0))

            device_ref = t.get("device", {})
            dev_id = device_ref.get("id", "") if isinstance(device_ref, dict) else str(device_ref)

            driver_ref = t.get("driver", {})
            driver_id = ""
            if isinstance(driver_ref, dict):
                driver_id = driver_ref.get("id", "")
            elif isinstance(driver_ref, str) and driver_ref != "UnknownDriverId":
                driver_id = driver_ref

            formatted.append({
                "trip_id": t.get("id", ""),
                "driver_id": driver_id,
                "device_id": dev_id or device_id,
                "start_time": str(start),
                "stop_time": str(stop),
                "distance": distance_km,
                "max_speed": t.get("maximumSpeed", t.get("maxSpeed", 0)),
                "average_speed": t.get("averageSpeed", 0),
                "duration_seconds": duration,
                "idle_duration_seconds": idle_duration,
                "trip_date": str(start)[:10] if start else "",
            })
        return formatted

    @staticmethod
    def _parse_duration(value):
        """Parse Geotab duration format to seconds. Handles 'HH:MM:SS', 'D.HH:MM:SS', or numeric."""
        if isinstance(value, (int, float)):
            return float(value)
        if not value or not isinstance(value, str):
            return 0.0
        try:
            parts = str(value).split(":")
            if len(parts) == 3:
                h, m, s = parts
                # Handle day prefix like "1.02:30:00"
                if "." in h:
                    day_part, h = h.split(".", 1)
                    return int(day_part) * 86400 + int(h) * 3600 + int(m) * 60 + float(s)
                return int(h) * 3600 + int(m) * 60 + float(s)
            elif len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
        except (ValueError, IndexError):
            pass
        return 0.0

    def get_driver_exceptions(self, driver_id, days_back=90):
        """Get per-driver exception events. Cached 1hr."""
        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(days=days_back)).isoformat()

        params = {
            "typeName": "ExceptionEvent",
            "search": {
                "fromDate": from_date,
                "toDate": now.isoformat(),
                "userSearch": {"id": driver_id}
            }
        }
        exceptions = self._cached_call(f"driver_exceptions_{driver_id}_{days_back}", 3600, "Get", params)

        rule_map = self._build_rule_map()
        formatted = []
        for e in (exceptions or []):
            rule_ref = e.get("rule", {})
            rule_id = rule_ref.get("id", "") if isinstance(rule_ref, dict) else str(rule_ref)
            device_ref = e.get("device", {})
            device_id = device_ref.get("id", "") if isinstance(device_ref, dict) else str(device_ref)
            formatted.append({
                "id": e.get("id", ""),
                "rule_name": rule_map.get(rule_id, "Unknown"),
                "rule_id": rule_id,
                "active_from": str(e.get("activeFrom", "")),
                "active_to": str(e.get("activeTo", "")),
                "duration": str(e.get("duration", "")),
                "driver_id": driver_id,
                "device_id": device_id,
            })
        return formatted

    def get_all_drivers(self):
        """Get all drivers (User with isDriver=True). Falls back to all users in demo DBs."""
        # Try isDriver first
        users = self._cached_call("all_drivers", 600, "Get", {
            "typeName": "User",
            "search": {"isDriver": True}
        })

        # Demo databases often have no isDriver users — fall back to all Users
        if not users:
            logger.info("No isDriver users found. Falling back to all Users.")
            users = self._cached_call("all_users", 600, "Get", {
                "typeName": "User"
            })

        return [
            {
                "id": u.get("id", ""),
                "name": u.get("name", ""),
                "firstName": u.get("firstName", ""),
                "lastName": u.get("lastName", ""),
                "email": u.get("email", ""),
                "isDriver": u.get("isDriver", False),
            }
            for u in (users or [])
        ]

    def get_all_devices(self):
        """Get all devices/vehicles. Cached 10min."""
        devices = self._cached_call("all_devices", 600, "Get", {"typeName": "Device"})
        return [
            {
                "id": d.get("id", ""),
                "name": d.get("name", ""),
                "serialNumber": d.get("serialNumber", ""),
            }
            for d in (devices or [])
        ]

    # === Write-Back Methods ===

    def create_group(self, name, vehicle_ids=None, parent_id="GroupCompanyId"):
        """Create a group in Geotab and optionally assign vehicles."""
        group_id = self.call("Add", {
            "typeName": "Group",
            "entity": {
                "name": name,
                "parent": {"id": parent_id},
                "color": {"a": 255, "b": 100, "g": 100, "r": 255},
            }
        })
        logger.info(f"Created group '{name}' with ID: {group_id}")

        # Assign vehicles to the group if provided
        if vehicle_ids:
            for vid in vehicle_ids:
                try:
                    devices = self.call("Get", {
                        "typeName": "Device",
                        "search": {"id": vid}
                    })
                    if devices:
                        device = devices[0]
                        groups = device.get("groups", [])
                        groups.append({"id": group_id})
                        device["groups"] = groups
                        self.call("Set", {"typeName": "Device", "entity": device})
                except Exception as e:
                    logger.warning(f"Failed to assign vehicle {vid} to group: {e}")

        return group_id

    def create_rule(self, name, rule_type="harsh_braking", driver_id=None):
        """Create a coaching alert rule in Geotab."""
        # Define conditions based on rule type
        conditions = {
            "harsh_braking": {"conditionType": "HarshBraking"},
            "speeding": {"conditionType": "Speeding"},
            "idle": {"conditionType": "Idling"},
            "welfare": {"conditionType": "NoDriverActivity"},
        }

        condition = conditions.get(rule_type, conditions["harsh_braking"])

        entity = {
            "name": name,
            "baseType": "Custom",
            "condition": condition,
            "comment": f"GEOPulse coaching rule: {rule_type}",
        }

        if driver_id:
            entity["groups"] = [{"id": "GroupCompanyId"}]  # Apply to company

        try:
            rule_id = self.call("Add", {
                "typeName": "Rule",
                "entity": entity
            })
            logger.info(f"Created rule '{name}' with ID: {rule_id}")
            return rule_id
        except Exception as e:
            logger.warning(f"Rule creation failed: {e}")
            return None

    def get_kpi_data(self, entity="VehicleKpi_Daily", days_back=7):
        """Pull OData KPI data from Data Connector. Cached 1hr."""
        # Data Connector uses HTTP Basic Auth
        dc_servers = [
            "odata-connector-1.geotab.com",
            "odata-connector-2.geotab.com",
        ]

        auth_user = f"{self.database}/{self.username}"
        auth_pass = self.password

        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")

        # Check cache first
        if self.cache:
            cache_key = f"kpi_{entity}_{days_back}"
            params_hash = hashlib.sha256(f"{entity}:{from_date}".encode()).hexdigest()[:16]
            cached = self.cache.get_api_cache(cache_key, params_hash, 3600)
            if cached:
                return cached

        for dc_server in dc_servers:
            url = f"https://{dc_server}/odata/v4/svc/{entity}"
            params = {
                "$filter": f"Date ge {from_date}",
                "$top": 500,
            }
            try:
                response = requests.get(
                    url, params=params,
                    auth=(auth_user, auth_pass),
                    timeout=30
                )
                if response.status_code == 200:
                    data = response.json().get("value", [])
                    if self.cache:
                        self.cache.set_api_cache(f"kpi_{entity}_{days_back}", params_hash, data, 3600)
                    return data
                elif response.status_code == 401:
                    logger.warning(f"Data Connector auth failed on {dc_server}")
                    continue
            except requests.ConnectionError:
                continue
            except Exception as e:
                logger.warning(f"Data Connector error: {e}")
                continue

        logger.warning("Data Connector unavailable on all servers. Returning empty.")
        return []


# Quick test when run directly
if __name__ == "__main__":
    from core.duckdb_cache import DuckDBCache

    cache = DuckDBCache(db_path="geopulse.db")
    cache.initialize()

    client = GeotabClient(db_cache=cache)
    try:
        client.authenticate()
        devices = client.get_all_devices()
        drivers = client.get_all_drivers()
        positions = client.get_live_positions()

        print(f"✅ Geotab auth successful!")
        print(f"   📍 Vehicles: {len(devices)}")
        print(f"   👤 Drivers: {len(drivers)}")
        print(f"   🗺️  Live positions: {len(positions)}")

        if positions:
            p = positions[0]
            print(f"   Sample: {p['device_name']} at ({p['latitude']:.4f}, {p['longitude']:.4f})")

        if drivers:
            d = drivers[0]
            print(f"   First driver: {d.get('firstName', '')} {d.get('lastName', '')} (ID: {d['id']})")
            trips = client.get_driver_trips(d["id"], days_back=7)
            print(f"   Trips (7 days): {len(trips)}")

        # Test live events
        events = client.get_live_events()
        print(f"   📡 Events (24h): {len(events['events'])}")

    except Exception as e:
        print(f"❌ Geotab test failed: {e}")
    finally:
        cache.close()
