# binizox-cli

Binizox command line client.

First-stage scope:

- remote management through `~/.binizox/config.toml`
- browser login
- API Key import through `--api-key`
- `whoami`, `status`, and `logout`
- server discovery and compatibility check for Binizox `>=0.7.1`
- `binizox chat` for a temporary local browser chat with streamed Agent output; `/state` reads thread state and `/approve` resumes a pending tool approval
- `binizox agent list` and `binizox agent show <slug>` for inspecting agents visible to the logged-in user
- `binizox kb upload` for knowledge base file uploads
- `binizox agent eval` for running existing Langfuse dataset experiments with a logged-in remote
