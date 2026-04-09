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
SKILL_URL="${RAW_BASE}/.claude/skills/fitops/SKILL.md"
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
  if "$python" -m pip install --quiet fitops 2>/dev/null; then
    ok "fitops installed via pip"
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
# Package is 'fitops' on PyPI; the installed command is 'fitops'.
elif command -v uvx &>/dev/null; then
  ok "uv detected — trying uvx fitops"
  if uvx --from fitops fitops --help &>/dev/null 2>&1; then
    FITOPS_CMD="uvx --from fitops fitops"
    ok "fitops CLI ready  (uvx --from fitops fitops)"
  else
    # Fall through to pip (e.g. pre-release or network issue)
    warn "uvx could not resolve fitops — falling back to pip"
    if PYTHON=$(_find_python 2>/dev/null); then
      _pip_install "$PYTHON" || die "pip install fitops failed.\n  Try manually: pip install fitops"
    else
      die "No Python 3.11+ found for pip fallback.\n  Clone the repo and run: pip install -e ."
    fi
  fi

# 3. Fall back to pip
elif PYTHON=$(_find_python 2>/dev/null); then
  PY_VER=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  ok "Python ${PY_VER} detected (${PYTHON})"
  _pip_install "$PYTHON" || die "pip install fitops failed.\n  Try manually: pip install fitops"

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
# Follows the conventions from https://github.com/vercel-labs/skills :
#
#   Claude Code  →  .claude/commands/fitops.md   (slash command: /fitops)
#                   .claude/skills/fitops/SKILL.md
#   Windsurf     →  .windsurf/skills/fitops/SKILL.md
#   Augment      →  .augment/skills/fitops/SKILL.md
#   Goose        →  .goose/skills/fitops/SKILL.md
#   All others   →  .agents/skills/fitops/SKILL.md
#   (Cursor, Codex, Cline, OpenCode, Copilot, Gemini CLI, Warp, etc.)
# ─────────────────────────────────────────────────────────────────────────────
step "Installing FitOps skill"

SKILL_INSTALLED=false
AGENTS_SKILL_INSTALLED=false  # guard: only write .agents/skills/ once

# Install as a Vercel-convention skill: <base>/fitops/SKILL.md
_install_skill() {
  local base="$1"
  local label="$2"
  local target="${base}/fitops/SKILL.md"
  mkdir -p "${base}/fitops"
  if curl -fsSL "$SKILL_URL" -o "$target" 2>/dev/null; then
    ok "Skill → ${target}  ${DIM}(${label})${RESET}"
    SKILL_INSTALLED=true
    return 0
  else
    warn "Could not download skill to ${target}"
    return 1
  fi
}

# Install as a Claude Code slash command: <base>/fitops.md
_install_cmd() {
  local base="$1"
  local label="$2"
  local target="${base}/fitops.md"
  mkdir -p "$base"
  if curl -fsSL "$SKILL_URL" -o "$target" 2>/dev/null; then
    ok "CMD  → ${target}  ${DIM}(${label})${RESET}"
    SKILL_INSTALLED=true
    return 0
  else
    warn "Could not download command to ${target}"
    return 1
  fi
}

# Install to .agents/skills/ once even if multiple compatible agents are present
_install_agents_shared() {
  if [[ "$AGENTS_SKILL_INSTALLED" == "false" ]]; then
    _install_skill ".agents/skills" "$*"
    AGENTS_SKILL_INSTALLED=true
  else
    ok "Already installed to .agents/skills/  ${DIM}(also covers $*)${RESET}"
  fi
}

# ── Explicit override via AGENT= ──────────────────────────────────────────────
if [[ "${AGENT:-}" != "" ]]; then
  case "$(echo "$AGENT" | tr '[:upper:]' '[:lower:]')" in
    claude|claude-code)
      _install_cmd    ".claude/commands"       "Claude Code — /fitops command"
      _install_skill  ".claude/skills"         "Claude Code — skill"
      ;;
    windsurf)   _install_skill ".windsurf/skills"  "Windsurf" ;;
    augment)    _install_skill ".augment/skills"   "Augment" ;;
    goose)      _install_skill ".goose/skills"     "Goose" ;;
    cursor)     _install_agents_shared "Cursor" ;;
    codex)      _install_agents_shared "Codex" ;;
    cline)      _install_agents_shared "Cline" ;;
    opencode|open-code) _install_agents_shared "OpenCode" ;;
    copilot)    _install_agents_shared "GitHub Copilot" ;;
    *)          _install_skill ".agents/skills"   "${AGENT}" ;;
  esac

else
  # ── Auto-detect installed agents ─────────────────────────────────────────────

  # Claude Code (project-level): slash command + Vercel skill
  if [[ -d ".claude" ]]; then
    _install_cmd   ".claude/commands" "Claude Code — /fitops command"
    _install_skill ".claude/skills"   "Claude Code — skill"
  fi

  # Claude Code (global)
  if [[ -d "${HOME}/.claude" ]]; then
    _install_cmd   "${HOME}/.claude/commands" "Claude Code global — /fitops command"
    _install_skill "${HOME}/.claude/skills"   "Claude Code global — skill"
  fi

  # Windsurf (.windsurf/skills/ — its own namespace, not .agents/)
  if [[ -d ".windsurf" ]]; then
    _install_skill ".windsurf/skills" "Windsurf"
  fi

  # Augment (.augment/skills/)
  if [[ -d ".augment" ]]; then
    _install_skill ".augment/skills" "Augment"
  fi

  # Goose (.goose/skills/)
  if [[ -d ".goose" ]]; then
    _install_skill ".goose/skills" "Goose"
  fi

  # ── .agents/skills/ group — one install serves all of these ──────────────────
  # Cursor, Codex, Cline, OpenCode, GitHub Copilot, Warp, Gemini CLI, Replit…
  # all share .agents/skills/ as their project-level skills directory.

  if [[ -d ".cursor" ]]; then
    _install_agents_shared "Cursor"
  fi

  if [[ -d ".cline" ]]; then
    _install_agents_shared "Cline"
  fi

  if [[ -d ".codex" ]] || [[ -n "${CODEX_HOME:-}" ]]; then
    _install_agents_shared "Codex"
  fi

  if [[ -d ".opencode" ]] || [[ -n "${OPENCODE_HOME:-}" ]]; then
    _install_agents_shared "OpenCode"
  fi

  # GitHub Copilot — .github/ is too generic; only install if .github/copilot* exists
  if [[ -f ".github/copilot-instructions.md" ]] || [[ -d ".github/copilot-instructions.d" ]]; then
    _install_agents_shared "GitHub Copilot"
  fi

  # No agent detected anywhere
  if [[ "$SKILL_INSTALLED" == "false" ]]; then
    warn "No agent config directory detected — installing to .agents/skills/ (universal fallback)"
    _install_skill ".agents/skills" "universal fallback"
    printf "\n       %sTip:%s copy %s.agents/skills/fitops/SKILL.md%s to your agent's skills directory.\n" \
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
