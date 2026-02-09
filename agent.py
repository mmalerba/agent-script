#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
from pathlib import Path

def run_command(cmd, cwd=None, capture_output=True, text=True):
    """Runs a shell command and returns the result."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            shell=True,
            capture_output=capture_output,
            text=text,
            check=False
        )
        return result
    except Exception as e:
        print(f"Error running command '{cmd}': {e}")
        sys.exit(1)

def get_git_root():
    """Returns the root directory of the current git repo."""
    res = run_command("git rev-parse --show-toplevel")
    if res.returncode != 0:
        print("Error: Not inside a git repository.")
        sys.exit(1)
    return Path(res.stdout.strip())

def get_current_branch():
    """Returns the current git branch."""
    res = run_command("git branch --show-current")
    if res.returncode != 0 or not res.stdout.strip():
        return None
    return res.stdout.strip()

def branch_exists(branch):
    """Checks if a branch exists locally."""
    res = run_command(f"git rev-parse --verify {branch}")
    return res.returncode == 0

def sanitize_name(name):
    """Sanitizes the branch name for use in paths and tmux session names."""
    # Replace slashes with hyphens, dots with underscores to be safe
    return name.replace("/", "-").replace(".", "_")

def get_repo_context():
    """Returns (repo_root_path, repo_name)."""
    root = get_git_root()
    return root, root.name

def get_worktree_base(repo_root, repo_name):
    """Returns the base directory for this repo's agent worktrees."""
    # Sibling directory to the repo root
    return repo_root.parent / f"{repo_name}_agent_worktrees"

def cmd_run(args):
    repo_root, repo_name = get_repo_context()
    
    # Check if new flag is set (either global or local)
    new_branch = args.new or getattr(args, 'new_global', False)
    branch = args.branch

    # Resolve branch name if implicit (only if not creating new)
    if not new_branch and not branch:
        branch = get_current_branch()
        if not branch:
            print("Error: Could not determine current branch and none specified.")
            sys.exit(1)

    if branch == "main":
        print("Error: Agents cannot run on 'main' branch.")
        sys.exit(1)

    if new_branch:
        if not branch:
            print("Error: Branch name required when using -n/--new.")
            sys.exit(1)
        
        if branch_exists(branch):
            print(f"Error: Branch '{branch}' already exists.")
            sys.exit(1)
            
        print(f"Creating branch '{branch}'...")
        res = run_command(f"git branch {branch}", cwd=repo_root)
        if res.returncode != 0:
            print(f"Error creating branch: {res.stderr.strip()}")
            sys.exit(1)

    else:
        if not branch_exists(branch):
            print(f"Error: Branch '{branch}' does not exist.")
            sys.exit(1)

        # If the target branch is currently checked out, we must switch away from it
        # so we can create a worktree for it.
        current_branch = get_current_branch()
        if current_branch == branch:
            print(f"Branch '{branch}' is currently checked out. Switching to 'main'...")
            res = run_command("git checkout main", cwd=repo_root)
            if res.returncode != 0:
                print(f"Error checking out main: {res.stderr.strip()}")
                sys.exit(1)

    safe_branch = sanitize_name(branch)
    worktree_base = get_worktree_base(repo_root, repo_name)
    worktree_path = worktree_base / safe_branch
    
    # Ensure base directory exists
    worktree_base.mkdir(parents=True, exist_ok=True)

    # 1. Handle Worktree
    if worktree_path.exists():
        print(f"Reusing existing worktree at {worktree_path}")
    else:
        print(f"Creating new worktree for '{branch}' at {worktree_path}...")
        # We need to run this from the repo root
        # Note: git worktree add will fail if branch is already checked out elsewhere
        cmd = f"git worktree add {worktree_path} {branch}"
        res = run_command(cmd, cwd=repo_root)
        if res.returncode != 0:
            print(f"Failed to create worktree: {res.stderr.strip()}")
            sys.exit(1)

    # 2. Handle Tmux
    session_name = f"agent-{repo_name}-{safe_branch}"
    res = run_command(f"tmux has-session -t {session_name}")
    
    if res.returncode == 0:
        print(f"Reusing existing tmux session '{session_name}'")
    else:
        print(f"Creating new tmux session '{session_name}'...")
        # Create detached session, start in the worktree directory
        cmd = f"tmux new-session -d -s {session_name} -c {worktree_path}"
        res = run_command(cmd)
        if res.returncode != 0:
            print(f"Failed to create tmux session: {res.stderr.strip()}")
            sys.exit(1)
        
        # Send the gemini command
        run_command(f"tmux send-keys -t {session_name} 'gemini --yolo' C-m")

    # 3. Attach
    # Check if we are inside tmux already
    if not sys.stdout.isatty():
        print(f"Not running in a terminal, skipping attach to '{session_name}'.")
        return

    in_tmux = os.environ.get("TMUX")
    if in_tmux:
        print(f"Switching to session '{session_name}'...")
        run_command(f"tmux switch-client -t {session_name}")
    else:
        print(f"Attaching to session '{session_name}'...")
        # We use os.execvp to replace the current process with tmux
        os.execvp("tmux", ["tmux", "attach-session", "-t", session_name])

def cmd_ls(args):
    repo_root, repo_name = get_repo_context()
    worktree_base = get_worktree_base(repo_root, repo_name)
    
    # Gather potential agents from worktrees
    agents = set()
    worktrees = {}
    if worktree_base.exists():
        for child in worktree_base.iterdir():
            if child.is_dir():
                # We assume the dir name is the sanitized branch name
                # We can't easily reverse sanitize (lossy), but for display we can just show the dir name
                # or try to store metadata. For now, we use the dir name as the key.
                agents.add(child.name)
                worktrees[child.name] = str(child)

    # Gather potential agents from tmux sessions
    # Filter sessions starting with agent-{repo_name}-
    prefix = f"agent-{repo_name}-"
    res = run_command("tmux list-sessions -F '#{session_name}'")
    tmux_sessions = {}
    if res.returncode == 0:
        for line in res.stdout.splitlines():
            sname = line.strip()
            if sname.startswith(prefix):
                # extract safe branch name
                safe_branch = sname[len(prefix):]
                agents.add(safe_branch)
                tmux_sessions[safe_branch] = sname

    if not agents:
        print(f"No agents found for repo '{repo_name}'.")
        return

    print(f"{'Branch/ID':<30} {'Worktree':<60} {'Tmux':<30}")
    print("-" * 120)
    for agent in sorted(agents):
        wt_val = worktrees.get(agent, "NO")
        tm_val = tmux_sessions.get(agent, "NO")
        print(f"{agent:<30} {wt_val:<60} {tm_val:<30}")

def cmd_kill(args):
    repo_root, repo_name = get_repo_context()
    branch = args.branch
    safe_branch = sanitize_name(branch)
    force = args.force or getattr(args, 'force_global', False)
    
    # Clean up Tmux
    session_name = f"agent-{repo_name}-{safe_branch}"
    res = run_command(f"tmux has-session -t {session_name}")
    if res.returncode == 0:
        run_command(f"tmux kill-session -t {session_name}")
        print(f"Killed tmux session '{session_name}'.")
    else:
        print(f"No tmux session found for '{branch}'.")

    # Clean up Worktree
    worktree_base = get_worktree_base(repo_root, repo_name)
    worktree_path = worktree_base / safe_branch
    
    if worktree_path.exists():
        # Use git worktree remove
        cmd = f"git worktree remove {'--force ' if force else ''}{worktree_path}"
        res = run_command(cmd, cwd=repo_root)
        if res.returncode == 0:
            print(f"Removed worktree at {worktree_path}.")
        else:
            print(f"Failed to remove worktree (it might be dirty): {res.stderr.strip()}")
            print(f"You may need to manually run: git worktree remove --force {worktree_path}")
    else:
        print(f"No worktree found at {worktree_path}.")

def main():
    parser = argparse.ArgumentParser(description="Agent management script.")
    # Add global create flag
    parser.add_argument("-n", "--new", dest="new_global", action="store_true", help="Create new branch")
    # Add global force flag
    parser.add_argument("-f", "--force", dest="force_global", action="store_true", help="Force operation")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # RUN command
    p_run = subparsers.add_parser("run", help="Create or attach to an agent")
    p_run.add_argument("branch", nargs="?", help="Branch name (defaults to current)")
    p_run.add_argument("-n", "--new", dest="new", action="store_true", help="Create new branch")
    p_run.set_defaults(func=cmd_run)

    # LS command
    p_ls = subparsers.add_parser("ls", help="List active agents")
    p_ls.set_defaults(func=cmd_ls)

    # KILL command
    p_kill = subparsers.add_parser("kill", help="Kill an agent's session and worktree")
    p_kill.add_argument("branch", help="Branch name to kill")
    p_kill.add_argument("-f", "--force", dest="force", action="store_true", help="Force delete worktree")
    p_kill.set_defaults(func=cmd_kill)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
