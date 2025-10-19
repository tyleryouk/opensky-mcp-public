#!/home/kxdev/dev/mcp-servers/opensky-mcp/.venv/bin/python3
"""OpenSky MCP Server - Real-time aircraft tracking and flight data"""

import asyncio
import aiohttp
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
import mcp.types as types

# OpenSky Network API Configuration
OPENSKY_API_BASE = "https://opensky-network.org/api"

server = Server("opensky-mcp")

# Utility Functions

async def fetch_json(session: aiohttp.ClientSession, url: str, params: Dict = None) -> Dict:
    """Fetch JSON data from OpenSky API with error handling."""
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 200:
                return await response.json()
            else:
                return {"error": f"HTTP {response.status}: {response.reason}"}
    except asyncio.TimeoutError:
        return {"error": "Request timeout - OpenSky API took too long to respond"}
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

def format_aircraft_state(state: List) -> Dict:
    """Format raw OpenSky state vector into readable dict."""
    if not state or len(state) < 17:
        return {}

    return {
        "icao24": state[0],  # Unique ICAO 24-bit address
        "callsign": state[1].strip() if state[1] else "N/A",
        "origin_country": state[2],
        "time_position": state[3],
        "last_contact": state[4],
        "longitude": state[5],
        "latitude": state[6],
        "baro_altitude": state[7],  # meters
        "on_ground": state[8],
        "velocity": state[9],  # m/s
        "true_track": state[10],  # degrees
        "vertical_rate": state[11],  # m/s
        "sensors": state[12],
        "geo_altitude": state[13],  # meters
        "squawk": state[14],
        "spi": state[15],
        "position_source": state[16]
    }

def meters_to_feet(meters: float) -> float:
    """Convert meters to feet."""
    return meters * 3.28084 if meters else 0

def mps_to_knots(mps: float) -> float:
    """Convert m/s to knots."""
    return mps * 1.94384 if mps else 0

# MCP Tools

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List all available OpenSky tools."""
    return [
        types.Tool(
            name="get_aircraft_in_region",
            description="Get all aircraft currently in a geographic bounding box",
            inputSchema={
                "type": "object",
                "properties": {
                    "lat_min": {
                        "type": "number",
                        "description": "Minimum latitude (e.g., 38.8 for Northern Virginia)"
                    },
                    "lat_max": {
                        "type": "number",
                        "description": "Maximum latitude (e.g., 39.0)"
                    },
                    "lon_min": {
                        "type": "number",
                        "description": "Minimum longitude (e.g., -77.5 for DC area)"
                    },
                    "lon_max": {
                        "type": "number",
                        "description": "Maximum longitude (e.g., -77.0)"
                    }
                },
                "required": ["lat_min", "lat_max", "lon_min", "lon_max"]
            }
        ),
        types.Tool(
            name="get_aircraft_by_callsign",
            description="Track a specific aircraft by callsign (e.g., UAL123, AAL456)",
            inputSchema={
                "type": "object",
                "properties": {
                    "callsign": {
                        "type": "string",
                        "description": "Aircraft callsign (e.g., UAL123)"
                    }
                },
                "required": ["callsign"]
            }
        ),
        types.Tool(
            name="get_all_aircraft",
            description="Get all aircraft currently tracked by OpenSky Network (WARNING: Large dataset)",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "number",
                        "description": "Limit number of results (default: 50)"
                    }
                }
            }
        ),
        types.Tool(
            name="get_arrivals",
            description="Get flights arriving at an airport in a time window",
            inputSchema={
                "type": "object",
                "properties": {
                    "icao": {
                        "type": "string",
                        "description": "Airport ICAO code (e.g., KDCA for Reagan National)"
                    },
                    "begin": {
                        "type": "number",
                        "description": "Begin time as Unix timestamp (seconds since epoch)"
                    },
                    "end": {
                        "type": "number",
                        "description": "End time as Unix timestamp (seconds since epoch)"
                    }
                },
                "required": ["icao", "begin", "end"]
            }
        ),
        types.Tool(
            name="get_departures",
            description="Get flights departing from an airport in a time window",
            inputSchema={
                "type": "object",
                "properties": {
                    "icao": {
                        "type": "string",
                        "description": "Airport ICAO code (e.g., KIAD for Dulles)"
                    },
                    "begin": {
                        "type": "number",
                        "description": "Begin time as Unix timestamp (seconds since epoch)"
                    },
                    "end": {
                        "type": "number",
                        "description": "End time as Unix timestamp (seconds since epoch)"
                    }
                },
                "required": ["icao", "begin", "end"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution."""

    if name == "get_aircraft_in_region":
        lat_min = arguments.get("lat_min")
        lat_max = arguments.get("lat_max")
        lon_min = arguments.get("lon_min")
        lon_max = arguments.get("lon_max")

        async with aiohttp.ClientSession() as session:
            url = f"{OPENSKY_API_BASE}/states/all"
            params = {
                "lamin": lat_min,
                "lamax": lat_max,
                "lomin": lon_min,
                "lomax": lon_max
            }

            data = await fetch_json(session, url, params)

            if "error" in data:
                return [types.TextContent(type="text", text=f"Error: {data['error']}")]

            states = data.get("states", [])

            if not states:
                return [types.TextContent(
                    type="text",
                    text=f"No aircraft found in region:\n"
                         f"- Lat: {lat_min} to {lat_max}\n"
                         f"- Lon: {lon_min} to {lon_max}"
                )]

            result = f"**Aircraft in Region** (Found: {len(states)})\n\n"
            result += f"**Bounding Box:**\n"
            result += f"- Latitude: {lat_min} to {lat_max}\n"
            result += f"- Longitude: {lon_min} to {lon_max}\n\n"

            for state in states[:50]:  # Limit to 50 for readability
                aircraft = format_aircraft_state(state)

                result += f"**{aircraft['callsign']}** ({aircraft['origin_country']})\n"
                result += f"- ICAO24: {aircraft['icao24']}\n"

                if aircraft['latitude'] and aircraft['longitude']:
                    result += f"- Position: {aircraft['latitude']:.4f}, {aircraft['longitude']:.4f}\n"

                if aircraft['baro_altitude']:
                    result += f"- Altitude: {meters_to_feet(aircraft['baro_altitude']):,.0f} ft\n"

                if aircraft['velocity']:
                    result += f"- Speed: {mps_to_knots(aircraft['velocity']):.0f} knots\n"

                if aircraft['on_ground']:
                    result += f"- Status: On Ground\n"

                result += "\n"

            if len(states) > 50:
                result += f"*Showing 50 of {len(states)} aircraft. Refine your bounding box for fewer results.*\n"

            return [types.TextContent(type="text", text=result)]

    elif name == "get_aircraft_by_callsign":
        callsign = arguments.get("callsign", "").strip().upper()

        async with aiohttp.ClientSession() as session:
            url = f"{OPENSKY_API_BASE}/states/all"

            data = await fetch_json(session, url)

            if "error" in data:
                return [types.TextContent(type="text", text=f"Error: {data['error']}")]

            states = data.get("states", [])

            # Filter by callsign
            matching = [s for s in states if s[1] and s[1].strip().upper() == callsign]

            if not matching:
                return [types.TextContent(
                    type="text",
                    text=f"No aircraft found with callsign: {callsign}\n\n"
                         f"*Note: Callsign must be exact and aircraft must be airborne.*"
                )]

            aircraft = format_aircraft_state(matching[0])

            result = f"**Aircraft Tracking: {aircraft['callsign']}**\n\n"
            result += f"**Identification:**\n"
            result += f"- ICAO24: {aircraft['icao24']}\n"
            result += f"- Country: {aircraft['origin_country']}\n\n"

            if aircraft['latitude'] and aircraft['longitude']:
                result += f"**Position:**\n"
                result += f"- Latitude: {aircraft['latitude']:.4f}\n"
                result += f"- Longitude: {aircraft['longitude']:.4f}\n\n"

            result += f"**Altitude & Speed:**\n"
            if aircraft['baro_altitude']:
                result += f"- Barometric Altitude: {meters_to_feet(aircraft['baro_altitude']):,.0f} ft\n"
            if aircraft['geo_altitude']:
                result += f"- Geometric Altitude: {meters_to_feet(aircraft['geo_altitude']):,.0f} ft\n"
            if aircraft['velocity']:
                result += f"- Ground Speed: {mps_to_knots(aircraft['velocity']):.0f} knots\n"
            if aircraft['vertical_rate']:
                result += f"- Vertical Rate: {aircraft['vertical_rate'] * 196.85:.0f} ft/min\n"
            if aircraft['true_track']:
                result += f"- Heading: {aircraft['true_track']:.0f}°\n\n"

            result += f"**Status:**\n"
            result += f"- On Ground: {'Yes' if aircraft['on_ground'] else 'No'}\n"
            result += f"- Last Contact: {datetime.fromtimestamp(aircraft['last_contact']).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"

            if aircraft['squawk']:
                result += f"- Squawk: {aircraft['squawk']}\n"

            return [types.TextContent(type="text", text=result)]

    elif name == "get_all_aircraft":
        limit = arguments.get("limit", 50) if arguments else 50

        async with aiohttp.ClientSession() as session:
            url = f"{OPENSKY_API_BASE}/states/all"

            data = await fetch_json(session, url)

            if "error" in data:
                return [types.TextContent(type="text", text=f"Error: {data['error']}")]

            states = data.get("states", [])
            total = len(states)

            result = f"**All Aircraft** (Total: {total:,})\n\n"
            result += f"*Showing first {limit} aircraft*\n\n"

            for state in states[:limit]:
                aircraft = format_aircraft_state(state)

                result += f"**{aircraft['callsign']}** - {aircraft['origin_country']}\n"

                if aircraft['latitude'] and aircraft['longitude']:
                    result += f"  Position: {aircraft['latitude']:.2f}, {aircraft['longitude']:.2f}"

                if aircraft['baro_altitude']:
                    result += f" | Alt: {meters_to_feet(aircraft['baro_altitude']):,.0f} ft"

                result += "\n"

            result += f"\n*Total aircraft tracked worldwide: {total:,}*"

            return [types.TextContent(type="text", text=result)]

    elif name == "get_arrivals":
        icao = arguments.get("icao", "").upper()
        begin = arguments.get("begin")
        end = arguments.get("end")

        async with aiohttp.ClientSession() as session:
            url = f"{OPENSKY_API_BASE}/flights/arrival"
            params = {
                "airport": icao,
                "begin": int(begin),
                "end": int(end)
            }

            data = await fetch_json(session, url, params)

            if "error" in data:
                return [types.TextContent(type="text", text=f"Error: {data['error']}")]

            if isinstance(data, list):
                flights = data
            else:
                flights = []

            if not flights:
                return [types.TextContent(
                    type="text",
                    text=f"No arrivals found for {icao} in time window:\n"
                         f"- Begin: {datetime.fromtimestamp(begin).strftime('%Y-%m-%d %H:%M UTC')}\n"
                         f"- End: {datetime.fromtimestamp(end).strftime('%Y-%m-%d %H:%M UTC')}"
                )]

            result = f"**Arrivals: {icao}** (Found: {len(flights)})\n\n"
            result += f"**Time Window:**\n"
            result += f"- {datetime.fromtimestamp(begin).strftime('%Y-%m-%d %H:%M UTC')} to "
            result += f"{datetime.fromtimestamp(end).strftime('%H:%M UTC')}\n\n"

            for flight in flights[:30]:  # Limit to 30
                result += f"**{flight.get('callsign', 'N/A').strip()}**\n"
                result += f"- ICAO24: {flight.get('icao24', 'N/A')}\n"

                if flight.get('estDepartureAirport'):
                    result += f"- From: {flight['estDepartureAirport']}\n"

                if flight.get('firstSeen'):
                    result += f"- First Seen: {datetime.fromtimestamp(flight['firstSeen']).strftime('%H:%M UTC')}\n"

                if flight.get('lastSeen'):
                    result += f"- Last Seen: {datetime.fromtimestamp(flight['lastSeen']).strftime('%H:%M UTC')}\n"

                result += "\n"

            if len(flights) > 30:
                result += f"*Showing 30 of {len(flights)} flights*\n"

            return [types.TextContent(type="text", text=result)]

    elif name == "get_departures":
        icao = arguments.get("icao", "").upper()
        begin = arguments.get("begin")
        end = arguments.get("end")

        async with aiohttp.ClientSession() as session:
            url = f"{OPENSKY_API_BASE}/flights/departure"
            params = {
                "airport": icao,
                "begin": int(begin),
                "end": int(end)
            }

            data = await fetch_json(session, url, params)

            if "error" in data:
                return [types.TextContent(type="text", text=f"Error: {data['error']}")]

            if isinstance(data, list):
                flights = data
            else:
                flights = []

            if not flights:
                return [types.TextContent(
                    type="text",
                    text=f"No departures found for {icao} in time window:\n"
                         f"- Begin: {datetime.fromtimestamp(begin).strftime('%Y-%m-%d %H:%M UTC')}\n"
                         f"- End: {datetime.fromtimestamp(end).strftime('%Y-%m-%d %H:%M UTC')}"
                )]

            result = f"**Departures: {icao}** (Found: {len(flights)})\n\n"
            result += f"**Time Window:**\n"
            result += f"- {datetime.fromtimestamp(begin).strftime('%Y-%m-%d %H:%M UTC')} to "
            result += f"{datetime.fromtimestamp(end).strftime('%H:%M UTC')}\n\n"

            for flight in flights[:30]:  # Limit to 30
                result += f"**{flight.get('callsign', 'N/A').strip()}**\n"
                result += f"- ICAO24: {flight.get('icao24', 'N/A')}\n"

                if flight.get('estArrivalAirport'):
                    result += f"- To: {flight['estArrivalAirport']}\n"

                if flight.get('firstSeen'):
                    result += f"- First Seen: {datetime.fromtimestamp(flight['firstSeen']).strftime('%H:%M UTC')}\n"

                if flight.get('lastSeen'):
                    result += f"- Last Seen: {datetime.fromtimestamp(flight['lastSeen']).strftime('%H:%M UTC')}\n"

                result += "\n"

            if len(flights) > 30:
                result += f"*Showing 30 of {len(flights)} flights*\n"

            return [types.TextContent(type="text", text=result)]

    else:
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="opensky-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
