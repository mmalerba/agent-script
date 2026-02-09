<!-- @format -->

agent script:

`agent run <branch>`

- check if branch exists
  - if no, exit with error
  - if no branch specified, assume current branch
- check if git worktree exists for branch
  - if not create
  - log whether we're reusing or making a new worktree
- check if tmux session exists for branch
  - if not create, then start gemini cli
  - if yes attach
  - log wether reusing or creating new

options:
-n/--new create a new branch

`agent ls`

- list current agents, for each show:
  - branch
  - if there is a worktree
  - if there is a tmux session

`agent kill <branch>`

- kills the tmux session and worktree associated with the given branch

`agent`

- shorthand for `agent run <current-branch>`
