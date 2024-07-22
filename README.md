# QuestAPI

A ~~API~~ websocket server to securely perform actions on the UWaterloo Quest system.

## Installation

### Using Docker Compose (Recommended)
```dockerfile
services:
  questAPI:
    build: .
    container_name: questAPI
    image: ghcr.io/vincentjguo/questapi:latest
    ports:
      - '4444:4444'
    restart: "unless-stopped"
```

### Running Locally
Requires Python 3.12
```bash
$ git clone
$ cd questAPI
$ python -m api.main
```

## Authentication
Requires a UWaterloo account with access to Quest.

### Logging in
Connect to the websocket at `wss://{host}/login` and send the following messages:
```text
{username}
{password}
{remember me? (true/false)}
```
If a 2FA code is required, the server will send a message to the client:
```json
{"status": 2, "payload": "{2FA_code}"}
```
Upon 2FA completion, the server will send a message to the client:
```json
{"status": 1, "payload": "{token}"}
```
This token can be used in the reconnect flow.

### Reconnecting
Reconnect to the websocket at `wss://{host}/reconnect` and send the following message:
```text
{token}
```
The token should be retrieved from the login flow from above.
Upon successful reconnection, the server will send a message to the client:
```json
{"status": 1, "payload": "{token}"}
```
The token will be the same as the received token.

Any failures in the authentication flow will have a negative status code and result in an immediate disconnect.

## Usage
All further actions assume the user is already connected and authenticated to the websocket.
### Search
Send the following messages to the open websocket.
```text
SEARCH
{term}
{subject}
{class number}
```
The term should be the 4 number code see [here](https://uwaterloo.ca/engineering/undergraduate-students/academic-support/term-information).

On a successful search, the server will send a message to the client:
```json
{"status": 1, "payload": 
      {"{section_type}": ["{location}", "{professor}"], ... }}
```

A failed search will have a negative status code but the connection will continue.

