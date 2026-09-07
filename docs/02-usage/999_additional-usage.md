# Additional Usage Pointers

## Prompting Strategies

We found that it is often a good idea to spend some time conceptualizing and planning a task
before actually implementing it, especially for non-trivial task. This helps both in achieving
better results and in increasing the feeling of control and staying in the loop. You can
make a detailed plan in one session, where Serena may read a lot of your code to build up the context,
and then continue with the implementation in another (potentially after creating suitable memories).

## Running Out of Context

For long and complicated tasks, or tasks where Serena has read a lot of content, you
may come close to the limits of context tokens. In that case, it is often a good idea to continue
in a new conversation. Serena has a dedicated tool to create a summary of the current state
of the progress and all relevant info for continuing it. You can request to create this summary and
write it to a memory. Then, in a new conversation, you can just ask Serena to read the memory and
continue with the task. In our experience, this worked really well. On the up-side, since in a
single session there is no summarization involved, Serena does not usually get lost (unlike some
other agents that summarize under the hood), and it is also instructed to occasionally check whether
it's on the right track.

Serena instructs the LLM to be economical in general, so the problem of running out of context
should not occur too often, unless the task is very large or complicated.

## Serena and Git Worktrees

[git-worktree](https://git-scm.com/docs/git-worktree) can be an excellent way to parallelize your work. More on this in [Anthropic: Run parallel Claude Code sessions with Git worktrees](https://docs.claude.com/en/docs/claude-code/common-workflows#run-parallel-claude-code-sessions-with-git-worktrees).

When it comes to serena AND git-worktree AND larger projects (that take longer to index), 
the recommended way is to COPY your `$ORIG_PROJECT/.serena/cache` to `$GIT_WORKTREE/.serena/cache`. 
Perform [pre-indexing of your project](indexing) to avoid having to re-index per each worktree you create. 

### Switching worktrees within a running session

Clients such as Claude Code can change their working directory during a session (e.g. via the `EnterWorktree`
tool) without restarting the MCP server. Serena follows such changes automatically: before each tool call, it
checks the working directory of the client process and, when it points into a different project, activates that
project (shutting down the previous project's language servers).

This is controlled by the `follow_client_cwd` option, which is **enabled by default**. Only *changes* of the
client's working directory are followed, so the directory the client happens to be in at startup never overrides
the project the server was started with. Directories that are neither a Serena project nor a git repository are
ignored, so changing into an unrelated directory does not switch the project.

To disable it, set `follow_client_cwd: false` in `serena_config.yml` or pass `--no-follow-client-cwd`:

```shell
serena start-mcp-server --context claude-code --project-from-cwd --no-follow-client-cwd
```

Note that switching restarts the language servers for the new project, so the first tool call after a switch is
slower; the symbol cache of each worktree is separate.
