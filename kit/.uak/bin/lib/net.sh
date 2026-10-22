# Network helpers shared by uak and the hooks; Bash 3.2+.
# One SSH connection for all the git round trips of a uak call and the next 3 min (OpenSSH ControlMaster).
# Measured on GitHub: 1.2 s per round trip cold, 0.4 s reused; a `uak next` makes 3-5 of them.
# Skipped on Windows (no Unix sockets in Git Bash's ssh), for https remotes, and when the user set their own ssh
# command. UAK_SSH_MUX=off disables it.
# No call may wait forever: without a terminal, git and ssh never prompt (passphrase, host key, https login) and
# a dead connection drops after ~30 s. Why (MLB hackathon): uak hung on one teammate's machine until 38
# processes piled up; the agent noted that every call fetched with no timeout.
UAK_SSH_SAFE="-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3"
net_guard() {
  [ -t 0 ] && return 0
  GIT_TERMINAL_PROMPT=0; GIT_HTTP_LOW_SPEED_LIMIT=${GIT_HTTP_LOW_SPEED_LIMIT:-1000}; GIT_HTTP_LOW_SPEED_TIME=${GIT_HTTP_LOW_SPEED_TIME:-30}
  export GIT_TERMINAL_PROMPT GIT_HTTP_LOW_SPEED_LIMIT GIT_HTTP_LOW_SPEED_TIME
  UAK_SSH_SAFE="-o BatchMode=yes $UAK_SSH_SAFE"
}
ssh_mux() {
  net_guard
  [ -z "${GIT_SSH_COMMAND:-}" ] && [ -z "${GIT_SSH:-}" ] || return 0
  git config --get core.sshCommand >/dev/null 2>&1 && return 0
  local url d
  url=$(git config --get "remote.${UAK_REMOTE:-origin}.url" 2>/dev/null) || return 0
  case "$url" in ssh://*) ;; *://*) return 0;; *@*:*) ;; *) return 0;; esac
  GIT_SSH_COMMAND="ssh $UAK_SSH_SAFE"; export GIT_SSH_COMMAND
  [ "${UAK_SSH_MUX:-on}" != off ] || return 0
  case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) return 0;; esac
  d="${HOME:-}/.ssh"
  case "$d" in /*) ;; *) return 0;; esac
  case "$d" in *[!A-Za-z0-9/._-]*) return 0;; esac
  { [ -d "$d" ] || mkdir -m 700 "$d"; } 2>/dev/null && [ -w "$d" ] || return 0
  GIT_SSH_COMMAND="ssh $UAK_SSH_SAFE -o ControlMaster=auto -o ControlPath=$d/uak-%C -o ControlPersist=180"
  export GIT_SSH_COMMAND
}
