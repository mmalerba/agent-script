# Agent Manager

A tool to manage AI agents working on separate git branches. Each agent runs in its own [git worktree](https://git-scm.com/docs/git-worktree) and [tmux](https://github.com/tmux/tmux) session, isolated from your main working directory.

## Prerequisites

- **Git**: For managing worktrees and branches.
- **Tmux**: For persistent terminal sessions.
- **Gemini CLI**: The agent itself (expects `gemini` to be in your PATH).

## Installation

You can use the `agent.py` script directly. For convenience, you might want to alias it or add it to your PATH:

```bash
chmod +x agent.py
ln -s $(pwd)/agent.py /usr/local/bin/agent
```

## Usage

### Run an Agent

Create or attach to an agent for a specific branch.

```bash
# Start an agent for the current branch
agent

# Start an agent for a specific branch
agent run my-feature

# Create a new branch and start an agent for it
agent run -n new-feature
```

When you run an agent:
1. A git worktree is created in `~/.agent/<repo-name>/<branch-name>` (if it doesn't exist).
2. A tmux session named `agent-<repo-name>-<branch-name>` is created (if it doesn't exist).
3. The command `gemini --yolo` is automatically started in the tmux session.
4. You are automatically attached to the tmux session.

### List Active Agents

Show all agents associated with the current repository, along with their worktree paths and tmux session status.

```bash
agent ls
```

### Kill an Agent

Stop an agent's tmux session and remove its git worktree.

```bash
agent kill my-feature

# Force removal if the worktree has uncommitted changes
agent kill -f my-feature
```

## How it Works

- **Worktrees**: All agents work in a dedicated base directory: `~/.agent/<repo-name>/`. This keeps your main repository clean and allows multiple agents to work in parallel on different branches.
- **Tmux Sessions**: Sessions are named to be easily identifiable. If you are already inside tmux, running `agent` will switch your current client to the agent's session. If you are outside tmux, it will attach to it.
- **Gemini CLI**: The script currently assumes the agent to run is `gemini --yolo`.
