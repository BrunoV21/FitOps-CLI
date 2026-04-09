#!/usr/bin/env bash
# FitOps CLI — Installer
#
# Installs the FitOps CLI and drops the agent skill into the right directory
# for whatever AI coding assistant you're running.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/brunov21/fitops-cli/main/install.sh | bash
#
# Or, to target a specific agent explicitly:
#   AGENT=cursor bash install.sh
#   AGENT=codex  bash install.sh
#   AGENT=claude bash install.sh

set -euo pipefail

REPO_OWNER="brunov21"
REPO_NAME="fitops-cli"
BRANCH="main"
RAW_BASE="https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/${BRANCH}"
SKILL_URL="${RAW_BASE}/.claude/commands/fitops.md"
DOCS_AUTH="https://${REPO_OWNER}.github.io/${REPO_NAME}/getting-started/authentication"
STRAVA_API="https://www.strava.com/settings/api"

# ── Colours ──────────────────────────────────────────────────────────────────
if [ -t 1 ] && command -v tput &>/dev/null && tput colors &>/dev/null; then
  BOLD=$(tput bold)
  DIM=$(tput dim)
  RED=$(tput setaf 1)
  GREEN=$(tput setaf 2)
  YELLOW=$(tput setaf 3)
  BLUE=$(tput setaf 4)
  CYAN=$(tput setaf 6)
  RESET=$(tput sgr0)
else
  BOLD="" DIM="" RED="" GREEN="" YELLOW="" BLUE="" CYAN="" RESET=""
fi

step()  { printf "\n%s==>%s %s%s%s\n"   "$BLUE"  "$RESET" "$BOLD" "$*" "$RESET"; }
ok()    { printf "%s  ✓%s  %s\n"        "$GREEN" "$RESET" "$*"; }
warn()  { printf "%s  !%s  %s\n"        "$YELLOW" "$RESET" "$*"; }
die()   { printf "\n%s  ✗  %s%s\n\n"   "$RED"   "$*" "$RESET" >&2; exit 1; }

# ── Header ────────────────────────────────────────────────────────────────────
printf "\n%sFitOps CLI%s — local fitness analytics for AI agents\n" "$BOLD" "$RESET"
printf "%shttps://github.com/%s/%s%s\n" "$DIM" "$REPO_OWNER" "$REPO_NAME" "$RESET"

# ─────────────────────────────────────────────────────────────────────────────
# 1. Install FitOps CLI
# ─────────────────────────────────────────────────────────────────────────────
step "Installing FitOps CLI"

FITOPS_CMD="fitops"

# Helper: try pip install then verify the command exists
_pip_install() {
  local python="$1"
  if "$python" -m pip install --quiet fitops-cli 2>/dev/null; then
    ok "fitops-cli installed via pip"
    return 0
  else
    return 1
  fi
}

# Helper: resolve python 3.11+ binary
_find_python() {
  local py
  for py in python3 python python3.11 python3.12 python3.13; do
    if command -v "$py" &>/dev/null; then
      if "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
        echo "$py"; return 0
      fi
    fi
  done
  return 1
}

# 1. If fitops is already installed as a command, use it directly
if command -v fitops &>/dev/null; then
  ok "fitops already installed ($(command -v fitops))"
  FITOPS_CMD="fitops"

# 2. Try uvx (isolated, no global install)
# Package is 'fitops-cli' on PyPI; the installed command is 'fitops'.
elif command -v uvx &>/dev/null; then
  ok "uv detected — trying uvx fitops-cli"
  if uvx --from fitops-cli fitops --help &>/dev/null 2>&1; then
    FITOPS_CMD="uvx --from fitops-cli fitops"
    ok "fitops CLI ready  (uvx --from fitops-cli fitops)"
  else
    # Fall through to pip (e.g. pre-release or network issue)
    warn "uvx could not resolve fitops-cli — falling back to pip"
    if PYTHON=$(_find_python 2>/dev/null); then
      _pip_install "$PYTHON" || die "pip install fitops-cli failed.\n  Try manually: pip install fitops-cli"
    else
      die "No Python 3.11+ found for pip fallback.\n  Clone the repo and run: pip install -e ."
    fi
  fi

# 3. Fall back to pip
elif PYTHON=$(_find_python 2>/dev/null); then
  PY_VER=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  ok "Python ${PY_VER} detected (${PYTHON})"
  _pip_install "$PYTHON" || die "pip install fitops-cli failed.\n  Try manually: pip install fitops-cli"

# 4. Nothing available
else
  printf "\n%sNeither uv/uvx nor Python 3.11+ was found on PATH.%s\n\n" "$RED" "$RESET"
  printf "  Install uv (recommended — manages Python automatically):\n"
  printf "    %scurl -LsSf https://astral.sh/uv/install.sh | sh%s\n\n" "$CYAN" "$RESET"
  printf "  Or install Python 3.11+ from:\n"
  printf "    %shttps://python.org/downloads%s\n\n" "$CYAN" "$RESET"
  exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# 2. Install the FitOps agent skill
#
# The skill file (.claude/commands/fitops.md) teaches any Claude-compatible
# agent the full FitOps command set, workflows, and error-recovery table.
# We copy it from the canonical GitHub source into every agent directory
# we can detect on this machine.
# ─────────────────────────────────────────────────────────────────────────────
step "Installing FitOps skill"

SKILL_INSTALLED=false

install_skill() {
  local dir="$1"
  local label="${2:-$1}"
  mkdir -p "$dir"
  if curl -fsSL "$SKILL_URL" -o "${dir}/fitops.md" 2>/dev/null; then
    ok "Skill → ${dir}/fitops.md  ${DIM}(${label})${RESET}"
    SKILL_INSTALLED=true
  else
    warn "Could not download skill to ${dir}/fitops.md"
  fi
}

# ── Explicit override ─────────────────────────────────────────────────────────
if [[ "${AGENT:-}" != "" ]]; then
  case "${AGENT,,}" in
    claude|claude-code)  install_skill ".claude/commands"    "Claude Code" ;;
    cursor)              install_skill ".cursor/rules"       "Cursor" ;;
    codex)               install_skill ".codex"              "Codex" ;;
    windsurf)            install_skill ".windsurf/rules"     "Windsurf" ;;
    cline)               install_skill ".cline/rules"        "Cline" ;;
    opencode|open-code)  install_skill ".opencode"           "OpenCode" ;;
    copilot)             install_skill ".github/copilot-instructions.d" "GitHub Copilot" ;;
    *)                   install_skill ".agents"             "${AGENT}" ;;
  esac

else
  # ── Auto-detect agent environment ──────────────────────────────────────────

  # Claude Code (project-level)
  if [[ -d ".claude" ]]; then
    install_skill ".claude/commands" "Claude Code — project"
  fi

  # Claude Code (global)
  if [[ -d "${HOME}/.claude" ]]; then
    install_skill "${HOME}/.claude/commands" "Claude Code — global"
  fi

  # Cursor
  if [[ -d ".cursor" ]]; then
    install_skill ".cursor/rules" "Cursor"
  fi

  # Codex (OpenAI)
  if [[ -d ".codex" ]] || [[ -n "${CODEX_HOME:-}" ]]; then
    install_skill "${CODEX_HOME:-.codex}" "Codex"
  fi

  # Windsurf / Codeium
  if [[ -d ".windsurf" ]]; then
    install_skill ".windsurf/rules" "Windsurf"
  fi

  # Cline (VS Code extension)
  if [[ -d ".cline" ]]; then
    install_skill ".cline/rules" "Cline"
  fi

  # OpenCode
  if [[ -d ".opencode" ]] || [[ -n "${OPENCODE_HOME:-}" ]]; then
    install_skill "${OPENCODE_HOME:-.opencode}" "OpenCode"
  fi

  # GitHub Copilot (custom instructions)
  if [[ -d ".github" ]]; then
    install_skill ".github/copilot-instructions.d" "GitHub Copilot"
  fi

  # Antigravity / generic .agents fallback
  if [[ "$SKILL_INSTALLED" == "false" ]]; then
    warn "No agent config directory detected — falling back to .agents/"
    install_skill ".agents" "generic fallback"
    printf "\n       %sTip:%s copy %s.agents/fitops.md%s to your agent's skill directory.\n" \
      "$YELLOW" "$RESET" "$CYAN" "$RESET"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# 3. Next steps — authentication
# ─────────────────────────────────────────────────────────────────────────────
printf "\n"
printf "%s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n" "$BOLD" "$RESET"
printf "%s  Next step: connect to Strava%s\n" "$BOLD" "$RESET"
printf "%s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n" "$BOLD" "$RESET"
printf "\n"
printf "  FitOps syncs your activities from Strava. You need a free\n"
printf "  Strava API application to get a %sClient ID%s and %sClient Secret%s.\n\n" \
  "$BOLD" "$RESET" "$BOLD" "$RESET"

printf "  %s1.%s Create your Strava API app:\n" "$BOLD" "$RESET"
printf "       %s%s%s\n\n" "$CYAN" "$STRAVA_API" "$RESET"
printf "     Use these exact settings:\n"
printf "       Application Name  →  %sSurge%s\n"                           "$BOLD" "$RESET"
printf "       Category          →  %sPerformance Analysis%s\n"             "$BOLD" "$RESET"
printf "       Website           →  %shttps://brunov21.github.io/Surge/%s\n" "$BOLD" "$RESET"
printf "       Callback Domain   →  %smclovinittt-kinetic-run-api.hf.space%s\n" "$BOLD" "$RESET"

printf "\n  %s2.%s Authenticate (enter your Client ID + Secret when prompted):\n\n" "$BOLD" "$RESET"
printf "       %s%s auth login%s\n\n" "$CYAN" "$FITOPS_CMD" "$RESET"

printf "  %s3.%s Sync your activities:\n\n" "$BOLD" "$RESET"
printf "       %s%s sync run%s\n\n" "$CYAN" "$FITOPS_CMD" "$RESET"

printf "  Full guide: %s%s%s\n" "$CYAN" "$DOCS_AUTH" "$RESET"

printf "\n%s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n" "$BOLD" "$RESET"
printf "\n  %sFitOps is installed.%s\n\n" "$GREEN$BOLD" "$RESET"

if [[ "$SKILL_INSTALLED" == "true" ]]; then
  printf "  In Claude Code, invoke the skill with:\n"
  printf "    %s/fitops <your training question>%s\n\n" "$CYAN" "$RESET"
fi

printf "  Start the dashboard:\n"
printf "    %s%s dashboard serve%s  →  http://localhost:8888\n\n" "$CYAN" "$FITOPS_CMD" "$RESET"
