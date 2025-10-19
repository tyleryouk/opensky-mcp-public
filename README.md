# opensky-mcp

MCP server for real-time aircraft tracking using OpenSky Network API.

## What It Does

Provides AI assistants (Claude Code) with tools to query live flight data:
- Aircraft in a geographic region
- Track specific flights by callsign
- Airport arrivals/departures
- Real-time position, altitude, speed

## Tools

### 1. `get_aircraft_in_region`
Query all aircraft in a bounding box.

**Example:**
```
Get aircraft over Northern Virginia:
- lat_min: 38.8
- lat_max: 39.0
- lon_min: -77.5
- lon_max: -77.0
```

### 2. `get_aircraft_by_callsign`
Track a specific flight.

**Example:**
```
Track United flight 123:
- callsign: UAL123
```

### 3. `get_all_aircraft`
Get all aircraft tracked worldwide (limit results).

### 4. `get_arrivals`
Flights arriving at an airport in a time window.

**Example:**
```
Reagan National arrivals in last hour:
- icao: KDCA
- begin: <unix_timestamp>
- end: <unix_timestamp>
```

### 5. `get_departures`
Flights departing from an airport in a time window.

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/tyleryouk/opensky-mcp-public.git
cd opensky-mcp-public
```

### 2. Create virtual environment and install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Test the server
```bash
# Make executable (Unix/Linux/Mac)
chmod +x server.py

# Test run (should start without errors)
python3 server.py
# Press Ctrl+C to stop
```

## Configuration

### For Claude Code

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "opensky-mcp": {
      "command": "/path/to/opensky-mcp-public/.venv/bin/python",
      "args": ["/path/to/opensky-mcp-public/server.py"]
    }
  }
}
```

**Important:** Use the full path to your virtual environment's Python interpreter.

Then restart Claude Code.

### Usage in Claude Code

Once configured, use via natural language:
```
"Show me all aircraft over Washington DC"
→ Calls get_aircraft_in_region with DC bounding box

"Track United 456"
→ Calls get_aircraft_by_callsign
```

## Technical Details

**API:** OpenSky Network REST API (https://opensky-network.org)
- Anonymous access (no auth required)
- Rate limits: ~100 requests/day for anonymous users

**Stack:**
- Python 3.11+
- aiohttp for async HTTP requests
- MCP SDK (Anthropic)

**Features:**
- Async API calls with timeout handling (10 seconds)
- Error handling for network failures
- Data transformation (raw state vectors → readable format)
- Unit conversions (meters → feet, m/s → knots)

## Data Format

OpenSky returns "state vectors" with aircraft telemetry:
- Position (lat/lon)
- Altitude (barometric + geometric)
- Velocity (ground speed)
- Heading (true track)
- Vertical rate (climb/descent)
- Transponder data (ICAO24, squawk, callsign)

## Common Airport ICAO Codes

**DMV Area:**
- KDCA - Reagan National
- KIAD - Dulles International
- KBWI - Baltimore/Washington

**Major US:**
- KJFK - JFK New York
- KLAX - LAX Los Angeles
- KORD - O'Hare Chicago
- KATL - Atlanta
- KDFW - Dallas/Fort Worth

## Limitations

- Anonymous API access = limited rate (avoid high-frequency polling)
- Historical data requires authenticated access (not implemented)
- Large bounding boxes return lots of data (use smaller regions)
- Some aircraft don't broadcast callsigns (military, private)

## Example Queries

**Northern Virginia (DC area):**
```json
{
  "lat_min": 38.8,
  "lat_max": 39.0,
  "lon_min": -77.5,
  "lon_max": -77.0
}
```

**Dulles area:**
```json
{
  "lat_min": 38.9,
  "lat_max": 39.0,
  "lon_min": -77.5,
  "lon_max": -77.4
}
```

## Troubleshooting

**Server won't start:**
- Check Python version: `python3 --version` (need 3.11+)
- Install dependencies: `pip install -r requirements.txt`

**No tools showing in Claude Code:**
- Check MCP config path is correct
- Use full absolute paths in config
- Restart Claude Code completely

**API errors:**
- OpenSky has rate limits for anonymous users
- Wait a few minutes between requests
- Large bounding boxes = slower responses

## License

MIT License - See LICENSE file for details

## Author

Tyler Youk - [GitHub](https://github.com/tyleryouk)
