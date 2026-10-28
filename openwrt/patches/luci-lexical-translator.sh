#!/bin/sh
# luci-lexical-translator.sh LUCI_JS: give LuCI's own scope a translator `_` of its own (issue #376).
#
# LuCI compiles every view and class with a direct eval() inside luci.js's outer function, so the `_()` they call
# is looked up there first and, finding nothing, in the page's globals: cbi.js's `function _`. A browser extension
# that puts Lodash (or anything else) on window._ then breaks the pages: `_(...).format is not a function`, or a
# '[data-tab=""Actions""]' selector. A `const _` at the top of that outer function is found first, and is the same
# lookup as cbi.js's: the trimmed string (with its context and \u0001 before it), hashed with sfh(), in window.TR,
# else the string itself. window._ stays whatever the page or the extension made it.
#
# Idempotent; the build fails when luci.js no longer starts the way this expects (a LuCI update to check by hand).
set -eu
f=${1:?usage: luci-lexical-translator.sh LUCI_JS}
MARK='/*mu300: lexical translator, issue #376*/'
grep -qF "$MARK" "$f" && exit 0
HEAD="((window,document,undefined)=>{'use strict';"
[ "$(grep -cF "$HEAD" "$f")" = 1 ] || { echo "luci-lexical-translator: $f does not start as expected" >&2; exit 1; }
CODE="$MARK"'const _=(s,c)=>{if(!window.TR||typeof sfh!="function"||typeof trimws!="function")return s;const k=(c!=null?trimws(c)+"\u0001":"")+trimws(s);return window.TR[sfh(k)]||s;};'
HEAD=$HEAD CODE=$CODE awk '
    !done && (i = index($0, ENVIRON["HEAD"])) {
        j = i + length(ENVIRON["HEAD"])
        $0 = substr($0, 1, j - 1) ENVIRON["CODE"] substr($0, j); done = 1
    }
    { print }' "$f" > "$f.new"
grep -qF "$MARK" "$f.new" || { rm -f "$f.new"; echo "luci-lexical-translator: not applied" >&2; exit 1; }
cat "$f.new" > "$f" && rm -f "$f.new"
