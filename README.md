# Repository where I'll play around with ADSB (and rtl-sdr)

Reason: rtl_adsb prints way to many packages, as well as prints packages with CRC errors.
To limit amount of data saved, I made this tool to clean it (and attach a timestamp to the logged file as well).


Typical usage:
```
# Saves ads-b packages to a logfile in the current directory.
# The Recording is restarted each night to get separate log files (and loose at most one day of data if something ordinary breaks)
python3 record_adsb.py --only_valid_adsb

```
Another typical use:
```
# In addition to logging, we use the curses-based visualizer
# to see what we're currently capturing.
python3 record_adsb.py --only_valid_adsb | python3 replay_adsb_from_file.py --source /dev/stdin

```


# Installation
Create a virtual environment, and install pymodes
```
python3 -m venv .venv
. .venv/bin/activate
pip install pymodes
```

Install rtl-sdr
```
sudo apt update && sudo apt install rtl-sdr
```

# Optional live view changes:
I made these changes in the update() method of
.venv/lib/python3.10/site-packages/pyModeS/streamer/screen.py
to limit number of decimals (or I needed to increase column widths to about 20 chars)

```
                for c, cw in self.columns:
                    if c == "|":
                        val = "|"
                    elif c == "live":
                        val = str(ac[c] - int(time.time())) + "s"
                    elif ac[c] is None:
                        val = ""
                    else:
                        val = ac[c]
                    # Limit number of decimals for some fields
                    if c in ["lat", "lon"] and type(val) == float:
                        val_str = f"{val:4.5f}"
                    elif c in ["trk", "hdg"] and type(val) == float:
                        val_str = f"{val:4.2f}"
                    elif c in ["mach"] and type(val) == float:
                        val_str = f"{val:1.3f}"
                    else:
                        val_str = str(val)
                    line += (cw - len(val_str)) * " " + val_str
```

# License

README.md: MIT License, Copyright (c) 2024 Simon Gustafsson.
record_adsb.py: MIT License, Copyright (c) 2024 Simon Gustafsson.

replay_adsb_from_file.py : GNU General Public License v3.0 since it's based on modeslive.py from https://github.com/junzis/pyModeS/. The new FileSource class is written by me, but enough bilerplate around it is left for me top suspect I can't give it a MIT license. Right now it's not practical to let it live in a separate repository.
