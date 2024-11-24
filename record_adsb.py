#!/usr/bin/env python3


import argparse
import pyModeS as pms
import subprocess
import sys
import signal
import time
from datetime import datetime

def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="runs rtl_adsb, Adds timestamps and handles splitting up logs")
    parser.add_argument("-c", "--comment", help="Comment to include in log file(s)", default="", type=str)
    parser.add_argument("--logfile_prefix", help="Logfile prefix", default="adsb_logfile_", type=str)
    parser.add_argument("--only_valid_adsb", help="Only recognized packages without CRC errors", action="store_true")
    args = parser.parse_args()

    while True:
        now = datetime.now()
        t0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        logfilename = args.logfile_prefix + now.isoformat().replace(':', '.')
        with open(logfilename, mode="wb", buffering=1024*1024) as logfile:
            print(f"Also saving to file '{logfilename}'", file=sys.stderr)

            def out(s):
                print(s)
                logfile.write(s.encode("utf-8") + b'\n')

            out(f"# {now.isoformat()}")

            t0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            old_seconds = -1

            with subprocess.Popen(["rtl_adsb"], 
                                bufsize=1, # Line buffered
                                stdin=None, stdout=subprocess.PIPE, text=True) as proc:
                while True:
                    try:
                        reading = proc.stdout.readline().removesuffix("\n")
                        now = datetime.now()
                        msg = reading.removeprefix("*").removesuffix(";").encode()

                        if args.only_valid_adsb:
                            df = pms.df(msg)

                            if len(msg) < 28:  # only process long messages
                                continue

                            if df not in [17, 18]:
                                continue

                            if pms.crc(msg) != 0:  # CRC fail (not sure if it's only for df==17)
                                continue

                        timestring = datetime.timestamp(now)

                        print(f"{reading}")
                        logfile.write(f"{timestring:.3f}\t{reading}".encode("utf-8") + b'\n')

                        d = now - t0
                        seconds = d.seconds + d.days*86400 + d.microseconds/1e6

                        if seconds > 86400:
                            print("New day - time for new log file - trying to terminate", file=sys.stderr)
                            proc.terminate()
                            if not proc.wait(timeout=5):
                                proc.kill()

                            time.sleep(2)
                            break  # jumping out to start new log file
                        
                        # Flush output stream once a second (nice when piping to other tools)
                        if d.seconds != old_seconds:
                            sys.stdout.flush()
                            old_seconds = d.seconds

                    except subprocess.TimeoutExpired as e:
                        print("Could not terminate, trying kill", file=sys.stderr)
                        proc.kill()
                        time.sleep(2)
                        break;

                    except Exception as e:
                        print(f"# Got exception processing line {repr(reading)}", file=sys.stderr)
                        logfile.write(f"{repr(e)}")
