# signal-cli-python-api
Python library to interact with signal-cli, a commanline client for Signal Messenger. The library supports programmatic sending/receiving of messages and attachments to direct recipients and group chats.

signal-cli is a java application implementing the official Signal Messenger java library, and can be found here:
https://github.com/AsamK/signal-cli

HOWEVER: This python library currently requires a forked version of this client that has the "jsonevtloop" function, and that is available here:
https://github.com/kbin76/signal-cli

## Typical usage

```python
import signalcli
 
test = signalcli.Signalcli(debug=True, user_name="+4670123456789")
test.run()
```

