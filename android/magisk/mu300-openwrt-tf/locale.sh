#!/system/bin/sh
# Use the active Android locale, not the shell's often-fixed C/English LANG.
mu300_install_lang() {
    locale=$(getprop persist.sys.locale 2>/dev/null || true)
    [ -n "$locale" ] || locale=$(getprop persist.sys.locales 2>/dev/null || true)
    [ -n "$locale" ] || locale=$(getprop persist.sys.language 2>/dev/null || true)
    [ -n "$locale" ] || locale=$(getprop ro.product.locale 2>/dev/null || true)
    [ -n "$locale" ] || locale=$(getprop ro.product.locale.language 2>/dev/null || true)
    locale=${locale%%,*}
    case $locale in zh|zh-*|zh_*) echo zh ;; *) echo en ;; esac
}
