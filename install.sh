#!/usr/bin/env bash
# FORGEX One-Line Installer
# Installs FORGEX into an isolated environment and makes `forgex` available
# globally in your PATH without ever needing to manually activate a virtual environment.

set -e

BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

echo -e "${BOLD}${CYAN}"
echo "  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗██╗  ██╗"
echo "  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝╚██╗██╔╝"
echo "  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗   ╚███╔╝ "
echo "  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝   ██╔██╗ "
echo "  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗██╔╝ ██╗"
echo "  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝"
echo -e "${RESET}"
echo -e "${BOLD}Installing FORGEX — Persistent Adaptive Multi-Model Software Engineering CLI${RESET}\n"

# 1. Locate compatible Python (>= 3.12)
PYTHON_BIN=""
for cmd in python3.14 python3.13 python3.12 python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        VERSION=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
        MAJOR=$(echo "$VERSION" | cut -d. -f1)
        MINOR=$(echo "$VERSION" | cut -d. -f2)
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 12 ]; then
            PYTHON_BIN="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}✗ Error: Python 3.12 or newer is required but was not found on your system.${RESET}"
    echo "Please install Python 3.12+ (e.g. sudo apt install python3.12 python3.12-venv) and retry."
    exit 1
fi

echo -e "Using Python: ${GREEN}$($PYTHON_BIN --version)${RESET} (${PYTHON_BIN})"

# 2. Determine installation directories
FORGEX_HOME="${HOME}/.forgex"
FORGEX_ENV="${FORGEX_HOME}/env"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "$FORGEX_HOME"
mkdir -p "$BIN_DIR"

# 3. Create isolated virtual environment if missing
if [ ! -d "$FORGEX_ENV" ] || [ ! -f "$FORGEX_ENV/bin/python" ]; then
    echo -e "Setting up isolated runtime in ${CYAN}${FORGEX_ENV}${RESET}..."
    rm -rf "$FORGEX_ENV"
    "$PYTHON_BIN" -m venv "$FORGEX_ENV"
fi

# 4. Install / upgrade FORGEX
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    echo "Installing from local source: $SCRIPT_DIR..."
    "$FORGEX_ENV/bin/pip" install --upgrade pip -q
    "$FORGEX_ENV/bin/pip" install -e "$SCRIPT_DIR" -q
else
    echo "Installing latest version from GitHub repository..."
    "$FORGEX_ENV/bin/pip" install --upgrade pip -q
    "$FORGEX_ENV/bin/pip" install --upgrade "git+https://github.com/B-max12/Forgex.git" -q
fi

# 5. Create launcher wrapper in ~/.local/bin/forgex
WRAPPER="${BIN_DIR}/forgex"
cat << 'EOF' > "$WRAPPER"
#!/usr/bin/env bash
# FORGEX Launcher — runs directly using its isolated runtime
exec "$HOME/.forgex/env/bin/forgex" "$@"
EOF
chmod +x "$WRAPPER"

echo -e "${GREEN}✓ Installed forgex launcher to ${WRAPPER}${RESET}"

# 6. Ensure ~/.local/bin is in PATH
SHELL_CONFIG=""
case "$SHELL" in
    */zsh)  SHELL_CONFIG="${HOME}/.zshrc" ;;
    */bash) SHELL_CONFIG="${HOME}/.bashrc" ;;
    *)      SHELL_CONFIG="${HOME}/.profile" ;;
esac

PATH_UPDATED=false
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    if [ -f "$SHELL_CONFIG" ]; then
        if ! grep -q 'PATH.*\.local/bin' "$SHELL_CONFIG"; then
            echo '' >> "$SHELL_CONFIG"
            echo '# Added by FORGEX installer' >> "$SHELL_CONFIG"
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_CONFIG"
            PATH_UPDATED=true
        fi
    fi
fi

echo -e "\n${BOLD}${GREEN}====================================================${RESET}"
echo -e "${BOLD}${GREEN}  FORGEX installation complete!${RESET}"
echo -e "${BOLD}${GREEN}====================================================${RESET}\n"

if [ "$PATH_UPDATED" = true ]; then
    echo -e "${YELLOW}Notice: ${BIN_DIR} was added to ${SHELL_CONFIG}.${RESET}"
    echo -e "To start using FORGEX immediately in this terminal, run:"
    echo -e "    ${BOLD}source ${SHELL_CONFIG}${RESET}"
    echo -e "or open a new terminal tab.\n"
fi

echo -e "To start FORGEX, simply run:"
echo -e "    ${BOLD}${CYAN}forgex${RESET}\n"
echo -e "${DIM}No virtual environment activation needed — ever.${RESET}"
