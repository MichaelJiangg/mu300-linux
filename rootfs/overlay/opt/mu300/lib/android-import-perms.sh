#!/bin/sh
# Adapted from dikeckaan/mu300-linux PR #199 (MIT). Source before vendor startup.
# Only imported trees, never dev/proc/sys bind mounts or symlink targets.
android_import_perms() {
    local root=$1 props=$2 owner=${3:-0:0} tree wrong= changed=0
    [ -d "$root" ] && [ ! -L "$root" ] || return 1
    for tree in apex system vendor linkerconfig "$props"; do
        tree="$root/$tree"
        [ -d "$tree" ] && [ ! -L "$tree" ] || continue
        wrong=$(find "$tree" -xdev ! -type l \( ! -user "${owner%:*}" -o ! -group "${owner#*:}" \
            -o -type d ! -perm 755 ! -perm 711 \
            -o -type f -path '*/bin/*' ! -perm 755 \
            -o -type f -path "$root/$props/*" ! -perm 444 \
            -o -type f ! -path '*/bin/*' ! -path "$root/$props/*" ! -perm 644 \) -print) || return 1
        [ -n "$wrong" ] || continue
        find "$tree" -xdev ! -type l \( ! -user "${owner%:*}" -o ! -group "${owner#*:}" \) -exec chown "$owner" {} + || return 1
        find "$tree" -xdev -type d ! -perm 755 ! -perm 711 -exec chmod 755 {} + || return 1
        find "$tree" -xdev -type f -path '*/bin/*' ! -perm 755 -exec chmod 755 {} + || return 1
        find "$tree" -xdev -type f -path "$root/$props/*" ! -perm 444 -exec chmod 444 {} + || return 1
        find "$tree" -xdev -type f ! -path '*/bin/*' ! -path "$root/$props/*" ! -perm 644 -exec chmod 644 {} + || return 1
        changed=1
    done
    [ "$changed" = 0 ] || echo 'Imported Android file permissions repaired' >&2
    return 0
}
