#!/bin/zsh
set -eu
MV_DIR=${0:A:h}
MV_APP=/Applications/cool-retro-term.app/Contents/MacOS/cool-retro-term
if [[ ! -x "$MV_APP" ]]; then
    print -u2 '找不到 /Applications/cool-retro-term.app。'
    exit 1
fi
if /usr/bin/pgrep -x cool-retro-term >/dev/null 2>&1; then
    print 'cool-retro-term 已打开。请在它的窗口中粘贴下面这行：'
    printf '/bin/zsh %q\n' "$MV_DIR/run.sh"
    print '也可以关闭 cool-retro-term 的所有窗口，再双击本文件。'
    read '?按回车关闭此提示。'
    exit 0
fi
exec "$MV_APP" --fullscreen --profile 'World Execute - Dense CRT' --workdir "$MV_DIR" -e /bin/zsh "$MV_DIR/run.sh" "$@"
