read @AGENTS.md

如果你發現 skill 不在 `.claude/skills` 內，你可以先下該指令: `New-Item -ItemType Junction -Path ".claude/skills" -Value "$PWD\.agents\skills\"` 他會將 `.agents/skills` 內的 skill 連結到 `.claude/skills`
