# signal-cli-python-api
Python library to interact with signal-cli, a commanline client for Signal Messenger. The library supports programmatic sending/receiving of messages and attachments to direct recipients and group chats. Suitable for making Signal Messenger bots.

signal-cli is a java application implementing the official Signal Messenger java library, and can be found here:
https://github.com/AsamK/signal-cli

HOWEVER: This python library currently requires a forked version of this client that has the "jsonevtloop" function, and that is available here:
https://github.com/kbin76/signal-cli

For the example to work, you must first use the signal-cli command line client to either register a new identity or link it to an already existing identity.

The example below is not complete, and it does not actually do any logging although it says it does in it's replies.

## EXAMPLE

```python

import signalcli
import re


my_name = "sigbot"
my_state = {
	"logging": False
}

def on_message( sigcli_obj, event_name, msg, state):
	print(str(msg))
	re_m = re.match('/(\w+)', msg.message_body)
	if re_m:
		command = re_m.group(1)
		if command == "log":
			if state['logging']:
				sigcli_obj.reply( msg, my_name + ": Logging is OFF", reply_to_sent_messages=True)
				state['logging'] = False
			else:
				sigcli_obj.reply( msg, my_name + ": Logging is ON", reply_to_sent_messages=True)
				state['logging'] = True				
		else:
			sigcli_obj.reply( msg, my_name + ": Unknown command '" + command + "'", reply_to_sent_messages=True)

## create new signal-cli object (will automatically start signal-cli in the background)
sig = signalcli.Signalcli(debug=True, user_name="+46123456789")

## register event callbacks that are triggered whenever something happens
k = sig.on('message', on_message, my_state)

## start the asyncio event loop
sig.run()


```

