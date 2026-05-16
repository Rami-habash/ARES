# NemoDemo
# quick setup. One skill. No subagents. One agent only so far.
AI agent running on NemoClaw + Nemotron 3 Nano (NVIDIA).

## Joining the team

SSH into the VM:
```bash
ssh user@<vm-ip>
```

Connect to the agent:
```bash
nemoclaw nemo-demo connect
```

Start chatting:
```bash
openclaw tui
```

## First time VM setup (one person only)

```bash
git clone <your-repo> NemoDemo && cd NemoDemo
export NVIDIA_API_KEY="nvapi-..."
bash setup.sh
```

## Useful commands

```bash
nemoclaw nemo-demo status        # health check
nemoclaw nemo-demo logs --follow # stream logs
nemoclaw nemo-demo skill install ./skills/my-skill  # add a skill
```
