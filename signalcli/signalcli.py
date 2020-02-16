
import sys
import asyncio
import json
import time
import datetime

class Signalcli:


    class Message:
        """ Object that represents an incoming/sent message """

        class MessageParsingFailure(Exception):
            pass

        @staticmethod
        def epochms_to_iso8601(ms):
            #return datetime.datetime.fromtimestamp((ms / 1000.0), tz=datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f%z')
            return datetime.datetime.fromtimestamp((ms / 1000.0)).strftime('%Y-%m-%dT%H:%M:%S.%f')

        def __str__(self):
            if self.recipient_type == "group" and self.__group_list and self.recipient_identity in self.__group_list:
                additional_recipient_info = "   Group: " + str(self.__group_list[self.recipient_identity]) + "\n"
            elif self.recipient_type == "direct" and self.__contact_list and self.recipient_identity in self.__contact_list:
                additional_recipient_info = "   Contact: " + str(self.__contact_list[self.recipient_identity]) + "\n"              
            else:
                additional_recipient_info = ""
            return "Message (" + self.type +") From: " + self.sender_identity + "/" + str(self.sender_device) + " [" + self.timestamp_iso8601 + "]\n" +\
                "   Recipient: " + self.recipient_identity + " (" + self.recipient_type + ")\n" +\
                additional_recipient_info +\
                "   Message: " + self.message_body

        def __init__(self, envelope, group_list=None, contact_list=None):
            self.__group_list = group_list
            self.__contact_list = contact_list
            self.timestamp = envelope['timestamp']
            self.timestamp_iso8601 = Signalcli.Message.epochms_to_iso8601(self.timestamp)
            self.sender_identity = envelope['source']
            self.sender_device = envelope['sourceDevice']
            if envelope['dataMessage']:
                self.type = "incoming_message"
                self.message_body = envelope['dataMessage']['message']
                self.attachments = envelope['dataMessage']['attachments']
                if envelope['dataMessage']['groupInfo']:
                    self.recipient_type = "group"
                    self.recipient_identity = envelope['dataMessage']['groupInfo']['groupId']
                else:
                    self.recipient_type = "direct"
                    self.recipient_identity = "Me"
            elif envelope['syncMessage']:
                self.type = "sent_message"
                if envelope['syncMessage']['sentMessage']:
                    self.message_body = envelope['syncMessage']['sentMessage']['message']
                    self.attachments = envelope['syncMessage']['sentMessage']['attachments']
                    if envelope['syncMessage']['sentMessage']['groupInfo']:
                        self.recipient_type = "group"
                        self.recipient_identity = envelope['syncMessage']['sentMessage']['groupInfo']['groupId']
                    else:
                        self.recipient_type = "direct"
                        self.recipient_identity = envelope['syncMessage']['sentMessage']['destination']
                else:
                    raise Signalcli.Message.MessageParsingFailure()
            else:
                ## unsupported message-type
                raise Signalcli.Message.MessageParsingFailure()


    class Contact:
        """ Object that represents a Contact record """

        def __str__(self):
            return self.name + " (" + self.identity + ")"

        def __init__(self, contact_entry):
            if contact_entry:
                self.name = contact_entry['name']
                self.identity = contact_entry['number']
                self.color = contact_entry['color']
                self.profile_key = contact_entry['profileKey']
                self.blocked = contact_entry['blocked']
            else:
                self.name = "unknown"
                self.identity = "unknown"
                self.color = ""
                self.profile_key = None
                self.blocked = False


    class Group:
        """ Object that represents Group Chat """

        def __str__(self):
            self.__member_resolve_contacts()
            member_list = list(map( lambda c: str(c), self.members))
            return self.name + " [" + str(member_list) + "]"


        def __member_resolve_contacts(self):
            self.members.clear()
            for member_identity in self.members_id_list:
                if member_identity in self.__contact_list:
                    self.members.append(self.__contact_list[member_identity])
                else:
                    new_contact = Signalcli.Contact( None)
                    new_contact.identity = member_identity
                    new_contact.name = member_identity
                    self.members.append(new_contact)


        def __init__(self, group_entry, contact_list):
            self.__contact_list = contact_list
            if group_entry:
                self.name = group_entry['name']
                self.identity = group_entry['groupId']
                self.color = group_entry['color']
                self.blocked = group_entry['blocked']
                self.active = group_entry['active']
                self.members = []
                self.members_id_list = group_entry['members']


    class SignalcliUsernameError(Exception):
        pass


    class SignalcliSendError(Exception):
        pass


    def exit_program(self):
        """ Exit the program (nicely), may be called from the event listener callbacks """
        self.__debug_out("exit_program")
        self.signalcli_api_ping_task.cancel()
        if self.incoming_json_queue:
            self.incoming_json_queue.join()
        self.async_loop.stop()
        #self.async_loop.close()
        if self.signal_cli_proc:
            self.signal_cli_proc.terminate()
        self.__debug_out("exit_program2")


    def __error_exit(self, msg):
        print( "Signalcli::ERROR(exiting): " + msg, file=sys.stderr)
        if self.signal_cli_proc:
            self.signal_cli_proc.terminate()
        sys.exit(-1)


    def __error_out(self, msg):
        print( "Signalcli::ERROR: " + msg, file=sys.stderr)


    def __debug_out(self, msg):
        if self.debug:
            print( "Signalcli::DEBUG: " + msg, file=sys.stderr)


    def __process_group_list(self, new_group_list):
        for group_list_entry in new_group_list:
            self.group_list[group_list_entry['groupId']] = Signalcli.Group(group_list_entry, self.contact_list)


    def __process_contact_list(self, new_contact_list):
        for contact_list_entry in new_contact_list:
            self.contact_list[contact_list_entry['number']] = Signalcli.Contact(contact_list_entry)


    async def __signalcli_api_ping( self):
        while True:
            await asyncio.sleep(2)
            await self.__send_json({ "reqType": "alive"})


    def __get_reqID(self):
        self.reqID_counter += 1
        return self.reqID_counter


    def reply( self, original_message, message_body, attachments = [], reply_to_sent_messages=False):
        if original_message.type == "incoming_message" or (reply_to_sent_messages and original_message.type == "sent_message"):
            if original_message.recipient_type == "group":
                self.send_message( "group", original_message.recipient_identity, message_body, attachments=attachments)
            elif original_message.recipient_type == "direct":
                if original_message.type == "sent_message":
                    self.send_message( "direct", original_message.recipient_identity, message_body, attachments=attachments)
                else:
                    self.send_message( "direct", original_message.sender_identity, message_body, attachments=attachments)


    def send_message( self, recipient_type, recipient_identity, message_body, attachments = []):
        req = {
            "reqID": self.__get_reqID(),
            "reqType": "send_message",
            "messageBody": message_body
        }
        if recipient_type == "group":
            req['recipientGroupID'] = recipient_identity
        elif recipient_type == "direct":
            req['recipientNumber'] = recipient_identity
        else:
            raise Signalcli.SignalcliSendError('recipient_type must be either "group" or "direct"')
        #await self.__send_json(req)
        self.outgoing_json_queue.put_nowait(req)


    async def __send_json( self, data_object):
        json_str = json.dumps(data_object)
        if self.debug_io:
            print( "send_json: " + json_str, file=sys.stderr)
        json_str += "\n"
        self.signal_cli_proc.stdin.write(json_str.encode('utf8'))
        await self.signal_cli_proc.stdin.drain()


    async def __outgoing_json_queue_worker(self):
        while True:
            data_object = await self.outgoing_json_queue.get()
            await self.__send_json(data_object)


    async def __incoming_json_queue_worker(self):
        while True:
            data_object = await self.incoming_json_queue.get()
            if data_object['apiVer'] == 2:
                respType = data_object['respType']
                if respType == "alive":
                    self.alive_timestamp = time.time()
                elif respType == "envelope":
                    if data_object['envelope']['dataMessage'] or data_object['envelope']['syncMessage']:
                        try:
                            m = Signalcli.Message( data_object['envelope'], contact_list = self.contact_list, group_list = self.group_list)
                            self.__call_event_callback( 'message', m)
                        except Signalcli.Message.MessageParsingFailure:
                            pass
                elif respType == "group_list":
                    self.__process_group_list(data_object['data'])
                elif respType == "contact_list":
                    self.__process_contact_list(data_object['data'])
                elif respType == "send_message":
                    pass
                else:
                    self.__error_out( 'Signalcli::incoming_json_queue_worker: Unknown respType="{0}"'.format(respType))
            else:
                self.__error_out('Signalcli::__incoming_json_queue_worker: Unknown API version ' + str(data_object['apiVer']))


    async def __stdout_stream_reader(self):
        while True:
            data_bytes = await self.signal_cli_proc.stdout.readline()
            if len(data_bytes):
                data_string = data_bytes.decode('utf8')
                if self.debug_io:
                    print("stdout_stream_reader: " + data_string, end=None)
                try:
                    data_object = json.loads(data_string)
                except json.JSONDecodeError as e:
                    self.__error_out( "Signalcli::stdout_stream_reader: JSONDecodeError: " + str(e))
                if data_object:
                    await self.incoming_json_queue.put(data_object)
            else:
                self.__error_debug("stdout_stream_reader: EOF", file=sys.stderr)
                break
        self.exit_program()


    async def __stderr_stream_reader(self):
        while True:
            data_bytes = await self.signal_cli_proc.stderr.readline()
            if len(data_bytes):
                data_string = data_bytes.decode('utf8')
                self.__error_out("signal-cli STDERR: " + data_string)
            else:
                self.__error_out("signal-cli STDERR: EOF")
                break


    async def __request_groups_and_contacts(self):
        await self.__send_json({ "reqType": "list_contacts" })
        await self.__send_json({ "reqType": "list_groups" })


    async def __start_signal_cli_subprocess(self):
        self.signal_cli_proc = await asyncio.create_subprocess_exec(
            self.bin_path,
            "-u", self.user_name, "jsonevtloop",
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            universal_newlines=False)
        self.async_loop.create_task(self.__stdout_stream_reader())
        self.async_loop.create_task(self.__stderr_stream_reader())
        if self.alive_check:
            self.signalcli_api_ping_task = self.async_loop.create_task(self.__signalcli_api_ping())
        self.async_loop.create_task(self.__request_groups_and_contacts())


    def __call_event_callback( self, event_name, event_obj):
        if event_name in self.callbacks:
            for cb in self.callbacks[event_name]:
                if cb['callback']:
                    cb['callback']( self, event_name, event_obj, *(cb['callback_data']))


    def on( self, event_name, callback, *callback_data):
        """ Add event subscriber callback and optional callback_data arguments that will be passed to the called callback function
            Signature of the callback function should be:
                callback(sigcli_object, event_name, event_object[, <callback_data arguments,...>])
            Return: callback_record object that can later be used to remove the callback.
        """
        if event_name in ['message','error','sent']:
            if not event_name in self.callbacks:
                self.callbacks[event_name] = []
            new_callback_record = { 'callback': callback, 'callback_data': callback_data }
            self.callbacks[event_name].append(new_callback_record)
            return new_callback_record
        else:
            self.__error_exit("Tried to subscribe to unknown event '" + event_name + "'")
            return None


    def remove_callback( self, callback_record):
        """  Remove callback provided the callback_record as returned by the "on('event_name', cb)" call """
        for k_event_name,v_cb_list in self.callbacks.items():
            try:
                v_cb_list.remove(callback_record)
            except ValueError:
                pass


    def get_event_loop(self):
        """ Get the asyncio event loop object, for creating custom tasks etc """
        return self.async_loop


    def run(self):
        """ Starts the asyncio event loop with run_forever() """
        self.async_loop.run_forever()


    def __init__(self, debug=False, event_loop=None, bin_path="signal-cli", user_name=None, alive_check=False):
        """ Create new Signalcli object
            Parameters:
                debug=(True/False)
                event_loop=<evtloop>        Provide custom asyncio eventloop (otherwise will retrieve standard eventloop)
                bin_path=<path>             Full path to signal-cli executable
                user_name=<username>        (MANDATORY)Username to provide to signal-cli, usually phone number in international dialling format ('+XXYYYY..')
                alive_check=(True/False)    Whether we should regularly check if signal-cli is still running
        """
        if not event_loop:
            self.async_loop = asyncio.get_event_loop()
        else:
            self.async_loop = event_loop
        self.debug = debug
        if debug:
            self.debug_io = True
        if not user_name:
            raise Signalcli.SignalcliUsernameError('user_name not defined')
        self.reqID_counter = 0
        self.alive_check = alive_check
        self.user_name = user_name
        self.bin_path = bin_path
        self.contact_list = {}
        self.group_list = {}
        self.async_loop.run_until_complete(self.__start_signal_cli_subprocess())
        self.incoming_json_queue = asyncio.Queue( loop=self.async_loop)
        self.outgoing_json_queue = asyncio.Queue( loop=self.async_loop)
        self.async_loop.create_task(self.__incoming_json_queue_worker())
        self.async_loop.create_task(self.__outgoing_json_queue_worker())
        self.callbacks = {}


