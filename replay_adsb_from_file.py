#!/usr/bin/env python
#
# Info about pyModeS at
# https://github.com/junzis/pyModeS/blob/master/README.rst
#
# This is mainly the modeslive.py tool, from that repo, with an addition of a
# FileSource, which allows using files as source
# (which could be /dev/stdin with the output from rtl_adsb).
# This file is tainted by their GNU General Public License v3.0, see
# https://github.com/junzis/pyModeS/blob/master/LICENSE

import os
import sys
import time
import argparse
import curses
import signal
import traceback
import multiprocessing
from pyModeS.streamer.decode import Decode
from pyModeS.streamer.screen import Screen
from pyModeS.streamer.source import NetSource, RtlSdrSource  # , RtlSdrSource24
import pyModeS as pms



class FileSource:
    def __init__(self, filename):
        self.filename = filename
        self.reset_local_buffer()

    def reset_local_buffer(self):
        self.local_buffer_adsb_msg = []
        self.local_buffer_adsb_ts = []
        self.local_buffer_commb_msg = []
        self.local_buffer_commb_ts = []

    def handle_messages(self, messages):

        if self.stop_flag.value is True:
            self.stop()
            return

        for msg, t in messages:
            if len(msg) < 28:  # only process long messages
                continue

            df = pms.df(msg)

            if df == 17 or df == 18:
                if pms.crc(msg) !=0:  # CRC fail (not sure if it's only for df==17)
                    continue

                self.local_buffer_adsb_msg.append(msg)
                self.local_buffer_adsb_ts.append(t)
            elif df == 20 or df == 21:
                #if pms.crc(msg) !=0:  # CRC fail (not sure if it's only for df==17)
                #    continue

                self.local_buffer_commb_msg.append(msg)
                self.local_buffer_commb_ts.append(t)
            else:
                continue

        if len(self.local_buffer_adsb_msg) > 1:
            self.raw_pipe_in.send(
                {
                    "adsb_ts": self.local_buffer_adsb_ts,
                    "adsb_msg": self.local_buffer_adsb_msg,
                    "commb_ts": self.local_buffer_commb_ts,
                    "commb_msg": self.local_buffer_commb_msg,
                }
            )
            self.reset_local_buffer()

    def run(self, raw_pipe_in=None, stop_flag=None, exception_queue=None):
        self.raw_pipe_in = raw_pipe_in
        self.exception_queue = exception_queue
        self.stop_flag = stop_flag
        
        with open(self.filename, "r") as f:
            try:
                for r in f:
                    if r.startswith("#"):
                        continue
                    r = r.removeprefix("*").removesuffix(";\n")
                    ts = time.time()

                    messages=[[r, ts]]
                    self.handle_messages(messages)
                    #time.sleep(0.002)

            except Exception as e:
                tb = traceback.format_exc()
                print(tb)
                if self.exception_queue is not None:
                    self.exception_queue.put(tb)
                raise e
            
        print("run finished")


def main():

    support_rawtypes = ["raw", "beast", "skysense"]

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        help='Choose data source, "rtlsdr", "rtlsdr24" or "net"',
        required=True,
        default="net",
    )
    parser.add_argument(
        "--connect",
        help="Define server, port and data type. Supported data types are: {}".format(
            support_rawtypes
        ),
        nargs=3,
        metavar=("SERVER", "PORT", "DATATYPE"),
        default=None,
        required=False,
    )
    parser.add_argument(
        "--latlon",
        help="Receiver latitude and longitude, needed for the surface position, default none",
        nargs=2,
        metavar=("LAT", "LON"),
        default=None,
        required=False,
    )
    parser.add_argument(
        "--show-uncertainty",
        dest="uncertainty",
        help="Display uncertainty values, default off",
        action="store_true",
        required=False,
        default=False,
    )
    parser.add_argument(
        "--dumpto",
        help="Folder to dump decoded output, default none",
        required=False,
        default=None,
    )
    args = parser.parse_args()

    SOURCE = args.source
    LATLON = args.latlon
    UNCERTAINTY = args.uncertainty
    DUMPTO = args.dumpto


    if SOURCE in ["rtlsdr", "rtlsdr24"]:
        pass
    elif SOURCE == "net":
        if args.connect is None:
            print("Error: --connect argument must not be empty.")
        else:
            SERVER, PORT, DATATYPE = args.connect
            if DATATYPE not in support_rawtypes:
                print(
                    "Data type not supported, available ones are %s"
                    % support_rawtypes
                )
    elif os.path.exists(SOURCE):
        pass
    else:
        print('Source must be "rtlsdr" or "net".')
        sys.exit(1)

    if DUMPTO is not None:
        # append to current folder except root is given
        if DUMPTO[0] != "/":
            DUMPTO = os.getcwd() + "/" + DUMPTO

        if not os.path.isdir(DUMPTO):
            print("Error: dump folder (%s) does not exist" % DUMPTO)
            sys.exit(1)

    # redirect all stdout to null, avoiding messing up with the screen
    sys.stdout = open(os.devnull, "w")

    raw_pipe_in, raw_pipe_out = multiprocessing.Pipe()
    ac_pipe_in, ac_pipe_out = multiprocessing.Pipe()
    exception_queue = multiprocessing.Queue()
    stop_flag = multiprocessing.Value("b", False)

    if SOURCE == "net":
        source = NetSource(host=SERVER, port=PORT, rawtype=DATATYPE)
    elif SOURCE == "rtlsdr":
        source = RtlSdrSource()
    # elif SOURCE == "rtlsdr24":
    #     source = RtlSdrSource24()
    elif os.path.exists(SOURCE):
        source = FileSource(SOURCE)

    recv_process = multiprocessing.Process(
        target=source.run, args=(raw_pipe_in, stop_flag, exception_queue)
    )

    decode = Decode(latlon=LATLON, dumpto=DUMPTO)
    decode_process = multiprocessing.Process(
        target=decode.run, args=(raw_pipe_out, ac_pipe_in, exception_queue)
    )

    screen = Screen(uncertainty=UNCERTAINTY)
    screen_process = multiprocessing.Process(
        target=screen.run, args=(ac_pipe_out, exception_queue)
    )

    def shutdown():
        stop_flag.value = True
        curses.endwin()
        sys.stdout = sys.__stdout__
        recv_process.terminate()
        decode_process.terminate()
        screen_process.terminate()
        recv_process.join()
        decode_process.join()
        screen_process.join()

    def closeall(signal, frame):
        print("KeyboardInterrupt (ID: {}). Cleaning up...".format(signal))
        shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, closeall)

    recv_process.start()
    decode_process.start()
    screen_process.start()

    while True:
        if (
            (not recv_process.is_alive())
            or (not decode_process.is_alive())
            or (not screen_process.is_alive())
        ):
            shutdown()
            while not exception_queue.empty():
                trackback = exception_queue.get()
                print(trackback)

            sys.exit(1)

        time.sleep(0.01)

if __name__ == "__main__":
    main()