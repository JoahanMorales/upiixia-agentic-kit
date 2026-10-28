# Windows: uak-mcp hands a command's arguments over in the environment (UAK_ARGV0, UAK_ARGC, UAK_ARG_0…).
# Why: Git Bash re-parses a Windows command line: it strips single quotes and expands * and [ ] in words, so a
# lesson "df['count']" reached uak as "df[count]". The environment is passed as is.
set --
i=0
while [ "$i" -lt "${UAK_ARGC:-0}" ]; do
  v=UAK_ARG_$i; set -- "$@" "${!v}"; unset "$v"; i=$((i + 1))
done
unset UAK_ARGC
exec bash "$UAK_ARGV0" "$@"
