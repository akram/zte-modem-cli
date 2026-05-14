# zte-modem-cli

CLI tool for managing ZTE 5G/LTE modems and routers.

Reverse-engineered from the ZTE web UI. Tested with **ZTE ZLT X25 PRO** (Ooredoo Tunisia), should work with other ZTE CPE models using the same API.

## Install

```bash
pip install .
# or
pip install git+https://github.com/akram/zte-modem-cli.git
```

## Usage

```bash
# Full status overview
zte-cli -p YOUR_PASSWORD status

# Signal strength (basic info, no auth needed)
zte-cli signal

# Live signal monitoring (every 5 seconds)
zte-cli -p YOUR_PASSWORD monitor -i 5

# WiFi configuration
zte-cli -p YOUR_PASSWORD wifi

# Device info (model, IMEI, firmware, temperature, etc.)
zte-cli -p YOUR_PASSWORD info

# Firmware check
zte-cli firmware

# Reboot the modem
zte-cli -p YOUR_PASSWORD reboot

# Raw API call (for debugging/exploration)
zte-cli -p YOUR_PASSWORD raw <uuid> -m GET
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `192.168.100.1` | Modem IP address |
| `--scheme` | `https` | Protocol (http/https) |
| `-u`, `--user` | `admin` | Username |
| `-p`, `--password` | | Password (required for most commands) |

## Example Output

```
  Device
  ======
  Model          ZLT X25 PRO
  Real Device    ZLT X25 MAX Lite
  Firmware       1.21.3
  IMEI           866760060567288
  Uptime         1d 23h 15m
  Temperature    77C  Warm
  WAN IP         154.110.44.70

  Signal - LTE
  ============
  RSRP           -95 dBm  ||    Fair
  SINR           21.5 dB  Excellent
  Bands          3+1+20
  Bandwidth      20+20+10 MHz

  Signal - 5G NR
  ==============
  RSRP           -98 dBm  ||    Fair
  SINR           18 dB  Good
  Band           n78
  Bandwidth      80 MHz
```

## Compatibility

Tested with:
- ZTE ZLT X25 PRO (firmware 1.21.3)

Should work with other ZTE CPE models that use the UUID-based API on `/cgi-bin/http.cgi`, including:
- ZLT X25 MAX / MAX Lite
- Other Ooredoo-branded ZTE devices

## How it Works

The tool communicates with the modem's web API at `/cgi-bin/http.cgi`. Authentication uses `sha256(token + password)` where the token is obtained from a pre-login request. API commands are identified by UUIDs rather than human-readable names.

## License

MIT
