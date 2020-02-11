
import sys
import asyncio
import json
import time


class Signalcli:

    class SignalcliUsernameError(Exception):
        pass


    def error_out(self, msg):
        print( "Signalcli::ERROR: " + msg, file=sys.stderr)


    def debug_out(self, msg):
        if self.debug:
            print( "Signalcli::DEBUG: " + msg, file=sys.stderr)


    async def signalcli_api_ping( self):
        while True:
            await asyncio.sleep(2)
            await self.send_json({ "reqType": "alive"})


    async def send_json( self, data_object):
        json_str = json.dumps(data_object)
        if self.debug_io:
            print( "send_json: " + json_str, file=sys.stderr)
        json_str += "\n"
        self.signal_cli_proc.stdin.write(json_str.encode('utf8'))
        await self.signal_cli_proc.stdin.drain()


    async def incoming_json_queue_worker(self):
        while True:
            data_object = await self.incoming_json_queue.get()
            respType = data_object['respType']
            if respType == "alive":
                self.alive_timestamp = time.time()
            elif respType == "envelope":
                if data_object['envelope']['dataMessage']:
                    print( "***Message: " + data_object['envelope']['dataMessage']['message'])
            else:
                print( 'Signalcli::incoming_json_queue_worker: Unknown respType="{respType}"' % { "respType": respType })


    async def stdout_stream_reader( self):
        while True:
            data_bytes = await self.signal_cli_proc.stdout.readline()
            if len(data_bytes):
                data_string = data_bytes.decode('utf8')
                if self.debug_io:
                    print("stdout_stream_reader: " + data_string, end=None)
                try:
                    data_object = json.loads(data_string)
                except json.JSONDecodeError as e:
                    self.error_out( "Signalcli::stdout_stream_reader: JSONDecodeError: " + str(e))
                if data_object:
                    await self.incoming_json_queue.put(data_object)
            else:
                print("stdout_stream_reader: EOF", file=sys.stderr)
                break
        self.exit_program()


    def exit_program(self):
        print("exit_program", file=sys.stderr)
        self.signalcli_api_ping_task.cancel()
        if self.incoming_json_queue:
            self.incoming_json_queue.join()
        self.async_loop.stop()
        #self.async_loop.close()
        print("exit_program2", file=sys.stderr)


    async def stderr_stream_reader( self):
        while True:
            data_bytes = await self.signal_cli_proc.stderr.readline()
            if len(data_bytes):
                data_string = data_bytes.decode('utf8')
                print("signal-cli STDERR: " + data_string, end=None, file=sys.stderr)
            else:
                print("signal-cli STDERR: EOF", file=sys.stderr)
                break


    async def start_signal_cli_subprocess(self):
        self.signal_cli_proc = await asyncio.create_subprocess_exec(
            "/home/bingel/signal/signal-cli_NEW/build/install/signal-cli/bin/signal-cli",
            "-u", self.user_name, "jsonevtloop",
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            universal_newlines=False)
        self.async_loop.create_task(self.stdout_stream_reader())
        self.async_loop.create_task(self.stderr_stream_reader())
        if self.alive_check:
            self.signalcli_api_ping_task = self.async_loop.create_task(self.signalcli_api_ping())


    def get_event_loop(self):
        return self.async_loop


    def run(self):
        """ Starts the asyncio event loop with run_forever() """
        self.async_loop.run_forever()


    def __init__(self, debug=False, event_loop=None, bin_path="signal-cli", user_name=None, alive_check=False):
        if not event_loop:
            self.async_loop = asyncio.get_event_loop()
        else:
            self.async_loop = event_loop
        self.debug = debug
        if debug:
            self.debug_io = True
        if not user_name:
            raise SignalcliUsernameError('user_name not defined')
        self.alive_check = alive_check
        self.user_name = user_name
        self.bin_path = bin_path
        self.async_loop.run_until_complete(self.start_signal_cli_subprocess())
        self.incoming_json_queue = asyncio.Queue( loop=self.async_loop)
        self.async_loop.create_task(self.incoming_json_queue_worker())


